from pathlib import Path
from PySide6.QtWidgets import QFileDialog, QInputDialog


class OpenImageDialog:
    def choose_edited_images(self, parent, workspace):
        path = QFileDialog.getExistingDirectory(parent, 'Abrir imágenes editadas (carpeta con imagenes.json)', str(workspace.layout.project_root))
        return Path(path) if path else None

    def choose_delta_target(self, parent, image):
        path, _ = QFileDialog.getOpenFileName(parent, 'Elegir la ISO traducida para el parche', str(image.path.parent), 'Imagen (*.iso);;Todos los archivos (*)')
        return Path(path) if path else None

    def choose_delta_output(self, parent, target):
        path, _ = QFileDialog.getSaveFileName(parent, 'Guardar parche BPS', str(target.with_suffix('.bps')), 'Parche BPS (*.bps)', options=QFileDialog.Option.DontConfirmOverwrite)
        return Path(path) if path else None

    def choose_images_directory(self, parent, workspace):
        path = QFileDialog.getExistingDirectory(parent, "Guardar imágenes extraídas", str(workspace.layout.project_root))
        return Path(path) if path else None

    def choose_translation(self, parent, workspace):
        path = QFileDialog.getExistingDirectory(parent, "Abrir proyecto traducido (carpeta con project.toml)",
                                                str(workspace.layout.project_root))
        return Path(path) if path else None

    def choose_output_iso(self, parent, image):
        suggested = image.path.with_name(image.path.stem + "-traducida.iso")
        path, _ = QFileDialog.getSaveFileName(parent, "Guardar ISO traducida con un nombre nuevo", str(suggested),
                                             "Imagen PSP (*.iso)", options=QFileDialog.Option.DontConfirmOverwrite)
        return Path(path) if path else None

    def choose_file(self, parent):
        path, _ = QFileDialog.getOpenFileName(parent, "Abrir ROM/ISO", "", "Imágenes (*.iso *.rom *.bin *.img *.cso);;Todos los archivos (*)")
        return Path(path) if path else None

    def choose_platform(self, parent, inspection, registry):
        if inspection.image.detected_platform is not None:
            return inspection.image.detected_platform
        backends = registry.available()
        labels = [backend.display_name for backend in backends]
        if not labels:
            return None
        selected, accepted = QInputDialog.getItem(parent, "Seleccionar plataforma", "La detección no es concluyente. Selecciona la plataforma:", labels, 0, False)
        return backends[labels.index(selected)].id if accepted else None

    def choose_workspace(self, parent, image):
        path = QFileDialog.getExistingDirectory(parent, "Seleccionar carpeta de trabajo", str(image.path.parent))
        return Path(path) if path else None

    def choose_project(self, parent, workspace):
        path = QFileDialog.getExistingDirectory(parent, "Crear proyecto de traducción en esta carpeta", str(workspace.layout.project_root))
        if not path:
            return None
        source, accepted = QInputDialog.getText(parent, "Idioma original", "Idioma del texto original:", text="ja")
        if not accepted:
            return None
        target, accepted = QInputDialog.getText(parent, "Idioma de traducción", "Idioma de destino:", text="es-ES")
        return (Path(path), source, target) if accepted else None
