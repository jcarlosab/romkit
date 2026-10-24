from dataclasses import replace
import hashlib
from pathlib import Path
import shutil
import time

from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QApplication
import pytest

from iso_builder import make_iso
from romkit_core.models import InputImage, TextConstraints, TranslationUnit
from romkit_core.project import read_jsonl, write_config, write_jsonl
from romkit_core.models import ProjectConfig
from romkit_core.platforms.psp import PspBackend
from romkit_studio.services.controller import StudioController
from romkit_studio.windows.main_window import MainWindow as StudioWindow
from romkit_translator.services.project_session import ProjectSession
from romkit_translator.windows.main_window import MainWindow as TranslatorWindow

pytestmark = pytest.mark.integration


def wait_idle(controller, timeout=10000):
    deadline = time.monotonic() + timeout / 1000
    while controller.runner.busy and time.monotonic() < deadline:
        QApplication.processEvents()
        # Explicitly release Python's GIL while background Python jobs run.
        time.sleep(0.005)
    assert not controller.runner.busy


class Choices:
    def __init__(self, image, workspace, project):
        self.image, self.workspace, self.project = image, workspace, project
        self.manual_count = 0
        self.cancel_platform = False
        self.cancel_workspace = False
        self.modal_delay = False

    def choose_file(self, parent):
        return self.image

    def choose_platform(self, parent, inspection, registry):
        if self.modal_delay:
            QTest.qWait(100)  # Simulate native dialog processing finished events.
        self.manual_count += inspection.image.detected_platform is None
        return None if self.cancel_platform else (inspection.image.detected_platform or "psp")

    def choose_workspace(self, parent, image):
        return None if self.cancel_workspace else self.workspace

    def choose_project(self, parent, workspace):
        return self.project, "en", "es-ES"


def dispose(window, qapp):
    window.close()
    window.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def test_studio_to_portable_translator_edit_save_reopen(tmp_path, qapp):
    source = tmp_path / "synthetic.iso"
    make_iso(source)
    before = source.read_bytes(), source.stat().st_mtime_ns
    choices = Choices(source, tmp_path / "workspace", tmp_path / "editorial")
    choices.modal_delay = True
    studio = StudioWindow()
    controller = StudioController(studio, dialogs=choices)
    studio.controller = controller
    errors = QSignalSpy(controller.runner.error)
    studio.show()
    studio.workflow_buttons[studio.open_action].click()
    wait_idle(controller)
    assert studio.session.state.image.sha256 == hashlib.sha256(before[0]).hexdigest()
    assert studio.session.state.workspace == choices.workspace
    assert studio.session.state.image.sha256 in studio.image_details.text()
    assert studio.extract_action.isEnabled()
    studio.workflow_buttons[studio.extract_action].click()
    wait_idle(controller)
    resources = studio.session.state.resources
    assert len(resources) == 5
    assert all(resource.sha256 for resource in resources)
    assert PspBackend().list_resources(PspBackend().open_image(source)) == list(resources)
    assert studio.session.state.resources == tuple(resources)
    assert studio.analyze_action.isEnabled()
    studio.workflow_buttons[studio.analyze_action].click()
    wait_idle(controller)
    assert len(studio.session.state.candidates) >= 3
    assert not studio.create_project_action.isEnabled()
    assert studio.select_texts_button.isEnabled()
    assert not studio.export_texts_button.isEnabled()
    studio.select_texts_button.click()
    assert studio.candidate_model.confirmed()
    studio.clear_texts_button.click()
    assert not studio.export_texts_button.isEnabled()
    studio.select_texts_button.click()
    assert studio.create_project_action.isEnabled()
    assert studio.export_texts_button.isEnabled()
    studio.export_texts_button.click()
    wait_idle(controller)
    assert errors.count() == 0
    assert (choices.project / "text/main.jsonl").is_file()
    assert not (choices.project / ".romkit").exists()
    assert (choices.workspace / ".romkit/metadata/reinsert.json").exists()
    # Translator receives only editorial files, without the source ROM or metadata.
    portable = tmp_path / "portable"
    shutil.copytree(choices.project, portable)
    translator = TranslatorWindow()
    translator.show()
    assert translator.open_project(portable)
    assert translator.model.rowCount() >= 3
    translator.table.sortByColumn(2, Qt.SortOrder.DescendingOrder)
    translator.table.setCurrentIndex(translator.proxy.index(0, 0))
    row = translator.current_row
    unit = translator.session.records[row].unit
    translator.editor.target.setPlainText("Hola")
    translator.editor.notes.setPlainText("Revisar contexto")
    assert translator.session.records[row].unit.id == unit.id
    assert translator.session.records[row].unit.source == unit.source
    assert translator.session.progress[0] == 1
    assert translator.save_project()
    stored_order = [record.unit.id for record in translator.session.records]
    assert [unit.id for unit in read_jsonl(portable / "text/main.jsonl")] == stored_order
    reopened = ProjectSession()
    reopened.load(portable)
    changed = next(record.unit for record in reopened.records if record.unit.id == unit.id)
    assert changed.target == "Hola" and changed.notes == "Revisar contexto"
    assert changed.status.value == "translated"
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before
    dispose(translator, qapp)
    dispose(studio, qapp)


def test_open_cancellation_and_manual_selection_preserve_old_session(tmp_path, qapp):
    path = tmp_path / "generic.iso"
    make_iso(path, psp=False)
    choices = Choices(path, tmp_path / "workspace", tmp_path / "project")
    studio = StudioWindow()
    controller = StudioController(studio, dialogs=choices)
    studio.controller = controller
    original = InputImage(path, path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())
    studio.session.set_image(original)
    previous = studio.session.state
    choices.image = None
    controller.open_image()
    assert studio.session.state == previous
    choices.image = path
    choices.cancel_platform = True
    controller.open_image()
    wait_idle(controller)
    assert studio.session.state == previous and not choices.workspace.exists()
    choices.cancel_platform = False
    choices.cancel_workspace = True
    controller.open_image()
    wait_idle(controller)
    assert studio.session.state == previous and not choices.workspace.exists()
    choices.cancel_workspace = False
    controller.open_image()
    wait_idle(controller)
    assert studio.session.state.image.selected_platform == "psp"
    assert choices.manual_count >= 1
    dispose(studio, qapp)


def editorial_project(root, units):
    write_config(root / "project.toml", ProjectConfig("psp", "ab" * 32, "en", "es-ES"))
    write_jsonl(root / "text/main.jsonl", units)


def test_translator_progress_counts_reviewed_empty_once(tmp_path, qapp):
    root = tmp_path / 'progress-project'
    editorial_project(root, [TranslationUnit('a','One'),TranslationUnit('b','Two'),TranslationUnit('c','Three')])
    window = TranslatorWindow()
    assert window.open_project(root)
    assert window.translation_progress.value() == 0
    window.editor.reviewed.setChecked(True)
    assert window.session.progress == (1,3)
    assert window.translation_progress.value() == 1
    assert '33.333%' in window.translation_progress.format()
    window.editor.target.setPlainText('Uno')
    assert window.translation_progress.value() == 1  # Editing does not count the same entry twice.
    window.editor.target.setPlainText('')
    assert window.translation_progress.value() == 0
    window.editor.reviewed.setChecked(True)
    assert window.translation_progress.value() == 1
    assert window.save_project()
    dispose(window,qapp)


def test_translator_validation_empty_status_and_failed_save(tmp_path, qapp, monkeypatch):
    root = tmp_path / "project"
    editorial_project(root, [TranslationUnit("u", "Hello {name}", encoding="ascii", constraints=TextConstraints(max_bytes=10), tokens=("{name}",))])
    window = TranslatorWindow()
    assert window.open_project(root)
    window.editor.target.setPlainText("abcdefghijklmnop {name}")
    assert "bytes usados" in window.editor.validation.text()
    assert "límite" in window.editor.validation.text()
    window.editor.target.setPlainText("¡Hola! {name}")
    assert "no representables" in window.editor.validation.text()
    before = (root / "text/main.jsonl").read_bytes()
    import romkit_core.project.io as io
    with monkeypatch.context() as patch:
        patch.setattr(io.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("Falló el reemplazo")))
        assert not window.save_project()
        assert (root / "text/main.jsonl").read_bytes() == before
        assert window.session.dirty
    window.editor.target.setPlainText("")
    window.editor.reviewed.setChecked(True)  # Explicitly approve an intentional empty translation.
    assert window.session.progress == (1, 1)
    assert window.save_project()
    assert read_jsonl(root / "text/main.jsonl")[0].target == ""
    dispose(window, qapp)


def test_bad_projects_leave_translator_open_and_previous_state_intact(tmp_path, qapp):
    good, bad = tmp_path / "good", tmp_path / "bad"
    editorial_project(good, [TranslationUnit("u", "Hello")])
    editorial_project(bad, [TranslationUnit("b", "Bad")])
    with (bad / "text/main.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("{broken}\n")
    window = TranslatorWindow()
    window.show()
    assert window.open_project(good)
    assert not window.open_project(bad)
    assert "main.jsonl, línea 2" in window.feedback.text()
    assert window.session.root == good
    assert window.isVisible()
    (bad / "project.toml").write_text('schema_version = 999\nplatform = "psp"\nsource_sha256 = "' + "ab" * 32 + '"\nsource_language = "en"\ntarget_language = "es"\n', encoding="utf-8")
    assert not window.open_project(bad)
    assert "Unsupported project schema" in window.feedback.text()
    dispose(window, qapp)


def test_thousands_of_rows_and_multi_file_persistent_order(tmp_path, qapp):
    root = tmp_path / "large"
    units = [TranslationUnit(f"u{i:05}", f"Source {i}") for i in range(5000)]
    editorial_project(root, units[:2500])
    write_jsonl(root / "text/other.jsonl", units[2500:])
    window = TranslatorWindow()
    assert window.open_project(root)
    assert window.model.rowCount() == 5000
    window.table.sortByColumn(1, Qt.SortOrder.DescendingOrder)
    window.table.setCurrentIndex(window.proxy.index(0, 0))
    window.editor.target.setPlainText("Edited")
    assert window.save_project()
    assert [unit.id for unit in read_jsonl(root / "text/main.jsonl")] == [unit.id for unit in units[:2500]]
    assert [unit.id for unit in read_jsonl(root / "text/other.jsonl")] == [unit.id for unit in units[2500:]]
    dispose(window, qapp)
