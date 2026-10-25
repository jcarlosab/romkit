from dataclasses import replace
import logging
from pathlib import Path
import tempfile

from PySide6.QtCore import QObject, Slot, Qt

from romkit_core.analysis.inventory import inventory
from romkit_core.analysis.text_scanner import TextScanner
from romkit_core.adapters.registry import enabled_adapters
from romkit_core.analysis.images import export_images
from romkit_core.errors import PlatformError
from romkit_core.image import ImageService
from romkit_core.models import AnalysisStatus
from romkit_core.platforms import PlatformImage
from romkit_core.platforms.psp import PspBackend
from romkit_core.project.generator import ProjectGenerator
from romkit_core.project.rebuild import rebuild_project
from romkit_core.tasks import report
from romkit_studio.dialogs.open_image_dialog import OpenImageDialog
from .task_runner import TaskRunner


class StudioController(QObject):
    def __init__(self, window, *, dialogs=None):
        super().__init__(window)
        self.window = window
        self.dialogs = dialogs if dialogs is not None else OpenImageDialog()
        self.services = window.services
        if not any(backend.id == "psp" for backend in self.services.platforms.available()):
            self.services.platforms.register(PspBackend())
        self.images = ImageService(self.services.platforms)
        self.runner = TaskRunner(self)
        self._callbacks = {}
        self._closing = False
        window.open_image_requested.connect(self.open_image)
        window.extract_requested.connect(self.extract)
        window.analyze_requested.connect(self.analyze)
        window.create_project_requested.connect(self.create_project)
        window.import_translation_requested.connect(self.import_translation)
        window.create_delta_requested.connect(self.create_delta)
        window.export_images_requested.connect(self.export_images)
        window.import_images_requested.connect(self.import_images)
        self.runner.result.connect(self._result)
        self.runner.error.connect(self._error)
        self.runner.progress.connect(self._progress)
        self.runner.finished.connect(self._finished)

    def _submit(self, function, callback, *args, **kwargs):
        if self.runner.busy:
            return
        self.window.session.set_busy(True)
        self.window.progress_bar.setRange(0, 0)
        task = self.runner.submit(function, *args, with_progress=True, **kwargs)
        self._callbacks[task] = callback

    @Slot(str, object)
    def _result(self, task, result):
        callback = self._callbacks.get(task)
        if callback is not None and not self._closing:
            try:
                callback(result)
            except Exception as exc:
                self.window.log_panel.add_message(f"Error · {exc}")
                logging.exception("Studio result callback failed")

    @Slot(str, object)
    def _error(self, task, error):
        self.window.log_panel.add_message(f"Error · {error.message}")
        logging.getLogger(__name__).error("%s\n%s", error.message, error.traceback)

    @Slot(str, object)
    def _progress(self, task, progress):
        self.window.progress_bar.setRange(0, 100)
        self.window.progress_bar.setValue(int(progress.completed * 100 / progress.total) if progress.total else 0)
        self.window.statusBar().showMessage(progress.message)

    @Slot(str)
    def _finished(self, task):
        self._callbacks.pop(task, None)
        if not self.runner.busy:
            self.window.progress_bar.setRange(0, 100)
            self.window.progress_bar.setValue(100)
            self.window.session.set_busy(False)
            if self._closing:
                self.window.close()
            else:
                self._continue_open()

    def _continue_open(self):
        if not self.runner.busy and not self._closing and hasattr(self, "_next_open"):
            image, directory = self._next_open
            del self._next_open
            self._submit(self._prepare_workspace, self._opened, image, directory)

    def request_close(self):
        if not self.runner.busy:
            return True
        self._closing = True
        self.runner.cancel_all()
        self.window.statusBar().showMessage("Terminando la operación antes de cerrar…")
        return False

    @Slot()
    def open_image(self):
        if self.runner.busy:
            return
        path = self.dialogs.choose_file(self.window)
        if path is not None:
            self._submit(self.images.inspect, self._inspected, path)

    def _inspected(self, inspection):
        backend_id = self.dialogs.choose_platform(self.window, inspection, self.services.platforms)
        if backend_id is None:
            return
        image = self.images.select_platform(inspection, backend_id)
        directory = self.dialogs.choose_workspace(self.window, image)
        if directory is not None:
            self._next_open = image, directory
            # Native/modal dialogs run a nested event loop: finished may already
            # have arrived while the user was selecting the workspace.
            self._continue_open()

    def _prepare_workspace(self, image, directory, *, progress):
        report(progress, 0, 1, "Preparando carpeta de trabajo")
        workspace = self.services.workspace_factory(directory)
        workspace.register_source(image)
        root = workspace.layout.area("extracted")
        resources = inventory(root, progress=progress) if root.exists() else []
        report(progress, 1, 1, "Imagen lista")
        return image, workspace, resources

    def _opened(self, value):
        image, workspace, resources = value
        self.window.session.open_image(image, workspace.layout.project_root, resources)
        self.window.log_panel.add_message(f"Imagen abierta · {image.path.name} · {image.sha256}")

    def _workspace(self):
        return self.services.workspace_factory(self.window.session.state.workspace)

    @Slot()
    def extract(self):
        state = self.window.session.state
        if not state.has_image or state.workspace is None:
            return
        self._submit(self._extract, self.window.session.set_resources, state.image, self._workspace())

    def _extract(self, image, workspace, *, progress):
        backend = self.services.platforms.resolve(image.selected_platform)
        if not backend.probe(image.path).compatible:
            raise PlatformError("La imagen no contiene una estructura compatible con la plataforma seleccionada")
        destination = workspace.layout.area("extracted")
        if destination.exists() and any(destination.iterdir()):
            return inventory(destination, progress=progress)
        cache = workspace.layout.area("cache", create=True)
        with tempfile.TemporaryDirectory(prefix="extract-", dir=cache) as temporary:
            staging = Path(temporary) / "tree"
            result = backend.extract(PlatformImage(backend.id, image), staging, progress=progress)
            report(progress, 1, 1, "Guardando recursos extraídos")
            if destination.exists():
                destination.rmdir()
            staging.replace(destination)
        workspace.write_metadata("resources.json", {"resources": [r.to_dict() for r in result.resources]})
        return result.resources

    @Slot()
    def analyze(self):
        state = self.window.session.state
        if not state.resources or state.workspace is None:
            return
        self._submit(self._analyze, lambda value: self.window.session.set_analysis(*value), state.resources, self._workspace())

    def _analyze(self, resources, workspace, *, progress):
        scanner, candidates = TextScanner(), []
        paths = {resource.logical_path for resource in resources}
        origins, indexed_archives = [], []
        for adapter in enabled_adapters():
            for logical in adapter.matches(paths):
                found, archive_origins = adapter.scan(workspace, logical, progress)
                candidates.extend(found)
                origins.extend(archive_origins)
                indexed_archives.append(logical)
        archive_files = set(indexed_archives)
        for index, resource in enumerate(resources):
            if resource.logical_path in archive_files:
                continue
            # Once a game has a verified table reader, binary-wide guesses only
            # add noise from movies, installed data, fonts and duplicate archives.
            if indexed_archives and Path(resource.logical_path).suffix.lower() not in {".txt", ".csv", ".xml", ".json", ".ini"}:
                continue
            report(progress, index, len(resources), f"Buscando texto · {resource.logical_path}")
            path = workspace.layout.path("extracted", resource.logical_path)
            def scanning(value):
                report(progress, index * 100 + (value.completed * 100 // value.total if value.total else 0), len(resources) * 100, resource.logical_path)
            candidates.extend(scanner.scan_file(path, resource, progress=scanning))
        analyzed = [replace(resource, analysis_status=AnalysisStatus.ANALYZED) for resource in resources]
        workspace.write_metadata("archive_resources.json", {"schema_version": 1, "resources": origins})
        workspace.write_metadata("text_candidates.json", {"candidates": [candidate.to_dict() for candidate in candidates]})
        workspace.write_metadata("resources.json", {"resources": [resource.to_dict() for resource in analyzed]})
        workspace.write_metadata("text_detection.json", {"mode": "indexed_tables_and_text_files" if indexed_archives else "conservative_strings",
                                                         "candidates": len(candidates), "indexed_tables": len(origins)})
        report(progress, 1, 1, f"{len(candidates)} candidatos encontrados")
        return analyzed, candidates

    @Slot()
    def create_project(self):
        state = self.window.session.state
        candidates = self.window.candidate_model.confirmed()
        if not candidates or state.workspace is None:
            return
        workspace = self._workspace()
        choice = self.dialogs.choose_project(self.window, workspace)
        if choice is not None:
            destination, source, target = choice
            self._submit(ProjectGenerator().generate, self._generated, destination, state.image, state.image.selected_platform,
                         candidates, source_language=source, target_language=target, workspace=workspace)

    def _generated(self, project):
        self.window.log_panel.add_message(f"Proyecto creado · {project.root} · {len(project.units)} unidades")

    @Slot()
    def import_translation(self):
        state = self.window.session.state
        if self.runner.busy or not state.has_image or state.workspace is None:
            return
        workspace = self._workspace()
        project = self.dialogs.choose_translation(self.window, workspace)
        if project is None:
            return
        destination = self.dialogs.choose_output_iso(self.window, state.image)
        if destination is None:
            return
        from functools import partial
        operation = partial(rebuild_project, experimental=True) if self.window.experimental_reinsert.isChecked() else rebuild_project
        self._submit(operation, self._rebuilt, project, workspace, state.image, destination)

    def _rebuilt(self, result):
        if result.experimental:
            self.window.log_panel.add_message('ISO creada en modo experimental: comprobar diálogos, saltos de línea y fuentes en emulador.')
        self.window.log_panel.add_message(f"ISO traducida creada · {result.path}\n"
                                         f"{result.translated} textos insertados · {result.tables} tablas · "
                                         f"{result.skipped} textos pendientes conservados")
        # A modeless result stays visible after the runner resets its status.
        from PySide6.QtWidgets import QMessageBox
        dialog = QMessageBox(self.window)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowTitle("ISO traducida creada")
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setText(f"{result.translated} textos insertados en {result.tables} tablas.")
        dialog.setInformativeText(f"{result.path}\n\nLa imagen original no se ha modificado. Prueba la nueva ISO en PPSSPP.")
        self._build_dialog = dialog
        dialog.open()

    @Slot()
    def create_delta(self):
        from functools import partial
        from romkit_core.project.delta import create_bps
        state = self.window.session.state
        if self.runner.busy or not state.has_image:
            return
        target = self.dialogs.choose_delta_target(self.window, state.image)
        if target is None:
            return
        destination = self.dialogs.choose_delta_output(self.window, target)
        if destination is not None:
            operation = partial(create_bps, expected_source_sha256=state.image.sha256)
            self._submit(operation, self._delta_created, state.image.path, target, destination)

    def _delta_created(self, result):
        self.window.log_panel.add_message(f'Parche BPS verificado · {result.path}\n{result.size:,} bytes · SHA-256 del original: {result.source_sha256}\nSHA-256 del destino: {result.target_sha256}')
        from PySide6.QtWidgets import QMessageBox
        dialog = QMessageBox(self.window)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowTitle('Parche BPS creado')
        dialog.setText(f'{result.path}\n{result.size:,} bytes')
        dialog.setInformativeText('Verificado contra la imagen traducida. Para aplicarlo se necesita exactamente la ROM original usada como base; sus CRC se incluyen en el parche. Si partiste de un parche inglés, esa es la base requerida.')
        self._delta_dialog = dialog
        dialog.open()

    @Slot()
    def export_images(self):
        state = self.window.session.state
        if self.runner.busy or not state.resources or state.workspace is None:
            return
        workspace = self._workspace()
        destination = self.dialogs.choose_images_directory(self.window, workspace)
        if destination is not None:
            self._submit(export_images, self._images_exported, state.resources, workspace, destination)

    @Slot()
    def import_images(self):
        from romkit_core.project.image_rebuild import rebuild_images
        state = self.window.session.state
        if self.runner.busy or not state.has_image or state.workspace is None:
            return
        workspace = self._workspace()
        project = self.dialogs.choose_edited_images(self.window, workspace)
        if project is None:
            return
        destination = self.dialogs.choose_output_iso(self.window, state.image)
        if destination is not None:
            self._submit(rebuild_images, self._images_rebuilt, project, workspace, state.image, destination)

    def _images_rebuilt(self, result):
        from PySide6.QtWidgets import QMessageBox
        self.window.log_panel.add_message(f'ISO con imágenes creada · {result.path}\n{result.images} apariciones modificadas · {result.resources} recursos. Verificación estructural realizada; pendiente probar en emulador.')
        dialog = QMessageBox(self.window)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowTitle('Imágenes reinsertadas')
        dialog.setText(f'{result.path}\n{result.images} apariciones en {result.resources} recursos.')
        dialog.setInformativeText('La ISO original se conserva. Prueba la nueva ISO en PPSSPP. Una imagen deduplicada se aplica a todas sus apariciones del manifiesto.')
        self._images_build_dialog = dialog
        dialog.open()

    def _images_exported(self, result):
        from PySide6.QtWidgets import QMessageBox
        message = (f"{result.count} imágenes guardadas en:\n{result.path}" if result.count else
                   "No se han encontrado imágenes en los formatos compatibles.")
        if not result.count and result.warnings:
            message += f"\nInforme de formatos y errores: {result.path / 'imagenes.json'}"
        self.window.log_panel.add_message(message)
        dialog = QMessageBox(self.window)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowTitle("Extracción de imágenes")
        dialog.setText(message)
        dialog.setInformativeText(f"{result.containers} contenedores abiertos · {result.duplicates} imágenes repetidas omitidas · "
                                  f"{result.warnings} avisos.\nPNG/JPEG/GIF/BMP/WebP y texturas PSP GIM convertidas a PNG. "
                                  "Consulta imagenes.json para ver el origen y los formatos no compatibles.")
        self._images_dialog = dialog
        dialog.open()
