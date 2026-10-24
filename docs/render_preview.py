"""Generate UI previews from controlled test data, then discard the temporary project."""
import os
from pathlib import Path
import sys
import tempfile
from dataclasses import replace

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests/fixtures"))

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from iso_builder import make_iso
from romkit_core.analysis.text_scanner import TextScanner
from romkit_core.image import ImageService
from romkit_core.models import AnalysisStatus
from romkit_core.platforms import PlatformImage, PlatformRegistry
from romkit_core.platforms.psp import PspBackend
from romkit_core.project.generator import ProjectGenerator
from romkit_core.workspace import WorkspaceManager
from romkit_studio.windows.main_window import MainWindow as Studio
from romkit_translator.windows.main_window import MainWindow as Translator


def main():
    app = QApplication([])
    for filename in ("segoeui.ttf", "segoeuib.ttf"):
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + filename)
    app.setFont(QFont("Segoe UI", 10))
    output = Path(__file__).parent
    with tempfile.TemporaryDirectory(dir=output) as temporary:
        root = Path(temporary)
        source = root / "PSP-DEMO.iso"
        make_iso(source)
        backend = PspBackend()
        registry = PlatformRegistry()
        registry.register(backend)
        service = ImageService(registry)
        image = service.select_platform(service.inspect(source), "psp")
        workspace = WorkspaceManager(root / "workspace")
        workspace.register_source(image)
        extracted = workspace.layout.area("extracted")
        resources = backend.extract(PlatformImage("psp", image), extracted).resources
        candidates = []
        for resource in resources:
            candidates.extend(TextScanner().scan_file(extracted / resource.logical_path, resource))
        resources = tuple(replace(resource, analysis_status=AnalysisStatus.ANALYZED) for resource in resources)
        project = ProjectGenerator().generate(root / "Demo español", image, "psp", candidates, workspace=workspace, source_language="en")
        studio = Studio()
        studio.session.open_image(image, workspace.layout.project_root, resources)
        studio.session.set_analysis(resources, candidates)
        for row in range(studio.candidate_model.rowCount()):
            studio.candidate_model.setData(studio.candidate_model.index(row, 0), Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
        studio.log_panel.add_message(f"{len(resources)} recursos extraídos · {len(candidates)} candidatos encontrados")
        studio.show()
        app.processEvents()
        assert studio.grab().save(str(output / "studio.png"))
        studio.info_button.click()
        app.processEvents()
        assert studio.information_dialog.grab().save(str(output / "studio-info.png"))
        studio.information_dialog.close()
        translator = Translator()
        translator.open_project(project.root)
        translator.show()
        translator.editor.target.setPlainText("Hola, viajero!")
        translator.editor.notes.setPlainText("Saludo al inicio de la aventura.")
        app.processEvents()
        assert translator.grab().save(str(output / "translator.png"))
        translator.save_project()
        translator.close()
        studio.close()


if __name__ == "__main__":
    main()
