import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt, QItemSelectionModel, qInstallMessageHandler
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit
import pytest

from romkit_core.models import InputImage, ValidationIssue
from romkit_core.models.text_candidate import TextCandidate
from romkit_studio.models.session import SessionModel
from romkit_studio.services import StudioServices
from romkit_studio.windows.main_window import MainWindow

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def app(qapp):
    return qapp


@pytest.fixture
def window(app):
    window = MainWindow()
    window.show()
    app.processEvents()
    yield window
    window.close()
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_initial_panels_and_disabled_actions(window):
    assert window.pages.currentWidget() is window.start_page
    assert window.resources_dock.isVisible()
    assert window.activity_dock.isVisible()
    assert window.open_action.isEnabled()
    assert not window.analyze_action.isEnabled()
    assert not window.create_project_action.isEnabled()
    assert not window.close_image_action.isEnabled()
    assert not window.windowIcon().isNull()
    assert not window.windowIcon().pixmap(32, 32).isNull()


def prepare_texts(window):
    window.session.set_image(InputImage("game.iso", 42, "ab" * 32))
    candidates = [TextCandidate("r", "first.fmg", 10, "cp932", 5, "Apple", b"\0", 1),
                  TextCandidate("r", "second.fmg", 20, "cp932", 6, "Banana", b"\0", 1),
                  TextCandidate("r", "first.fmg", 30, "cp932", 11, "Green apple", b"\0", 1)]
    window.session.set_analysis([], candidates)
    return candidates


def test_search_marks_correct_source_rows_and_keeps_hidden_marks(window, app):
    candidates = prepare_texts(window)
    window.search_input.setText("BANANA")
    QTest.qWait(220)
    assert window.candidate_proxy.rowCount() == 1
    window.select_texts_button.click()
    assert window.candidate_model.confirmed() == [candidates[1]]
    window.search_input.setText("first.fmg")
    window.search_input.returnPressed.emit()
    assert window.candidate_proxy.rowCount() == 2
    window.select_texts_button.click()
    assert window.candidate_model.confirmed() == candidates
    window.search_input.setText("no matches")
    window.search_input.returnPressed.emit()
    assert window.candidate_proxy.rowCount() == 0
    assert not window.select_texts_button.isEnabled()
    assert window.export_texts_button.isEnabled()
    assert "3 marcados" in window.selection_count.text()
    window.clear_texts_button.click()
    assert not window.export_texts_button.isEnabled()


def test_row_selection_copy_mark_and_information_popup(window, app):
    candidates = prepare_texts(window)
    app.processEvents()
    assert not window.image_details.isVisible()
    rect = window.candidate_table.visualRect(window.candidate_proxy.index(1, 1))
    QTest.mouseClick(window.candidate_table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    assert window._selected_source_rows() == [1]
    assert window.mark_selection_button.isEnabled()
    window.mark_selection_button.click()
    assert window.candidate_model.confirmed() == [candidates[1]]
    window.copy_action.trigger()
    assert app.clipboard().text() == "Banana"
    # Shift/Ctrl style multi-row selection remains independent of export marks.
    window.candidate_table.selectionModel().select(window.candidate_proxy.index(2, 1),
        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    window.mark_selection_button.click()
    assert window.candidate_model.confirmed() == candidates[1:]
    window.info_button.click()
    app.processEvents()
    dialog = window.information_dialog
    assert dialog.isVisible()
    details = dialog.findChild(QPlainTextEdit).toPlainText()
    assert "SHA-256" in details and "Banana" in details and "cp932" in details
    dialog.close()


def test_checkbox_click_and_selection_stay_correct_with_search(window, app):
    candidates = prepare_texts(window)
    window.search_input.setText("Banana")
    window._apply_search()
    app.processEvents()
    cell = window.candidate_table.visualRect(window.candidate_proxy.index(0, 0))
    from PySide6.QtCore import QPoint
    QTest.mouseClick(window.candidate_table.viewport(), Qt.MouseButton.LeftButton,
                     pos=QPoint(cell.left() + 10, cell.center().y()))
    assert window.candidate_model.confirmed() == [candidates[1]]
    window.session.set_busy(True)
    assert not window.export_texts_button.isEnabled()
    assert not window.mark_selection_button.isEnabled()
    assert not window.search_input.isEnabled()


def test_unmark_remove_restore_filtered_rows_and_reanalysis(window, app):
    candidates = prepare_texts(window)
    window.select_texts_button.click()
    window.search_input.setText("Banana")
    window._apply_search()
    window.candidate_table.setCurrentIndex(window.candidate_proxy.index(0, 1))
    window.unmark_selection_button.click()
    assert window.candidate_model.confirmed() == [candidates[0], candidates[2]]
    window.mark_selection_button.click()
    window.remove_selection_button.click()
    assert window.candidate_model.candidates == (candidates[0], candidates[2])
    assert window.candidate_proxy.rowCount() == 0
    assert window.restore_action.isEnabled()
    window.restore_action.trigger()
    assert window.candidate_proxy.rowCount() == 1
    assert window.candidate_model.confirmed() == candidates
    window.candidate_table.setCurrentIndex(window.candidate_proxy.index(0, 1))
    window.remove_selection_button.click()
    # Busy transitions do not restore excluded rows, but a new analysis does.
    window.session.set_busy(True)
    window.session.set_busy(False)
    assert len(window.candidate_model.candidates) == 2
    window.session.set_analysis([], tuple(candidates))
    assert window.candidate_model.candidates == tuple(candidates)
    assert not window.restore_action.isEnabled()


def test_space_toggles_once_and_export_button_keeps_its_text_width(window, app):
    candidates = prepare_texts(window)
    window.candidate_table.setCurrentIndex(window.candidate_proxy.index(1, 1))
    window.candidate_table.setFocus()
    app.processEvents()
    QTest.keyClick(window.candidate_table, Qt.Key.Key_Space)
    assert window.candidate_model.confirmed() == [candidates[1]]
    assert window.export_texts_button.width() >= window.export_texts_button.minimumWidth()
    QTest.keyClick(window.candidate_table, Qt.Key.Key_Space)
    assert window.candidate_model.confirmed() == []
    assert window.mark_action.shortcut().isEmpty()
    QTest.keyClick(window.candidate_table, Qt.Key.Key_Delete)
    assert window.candidate_model.candidates == (candidates[0], candidates[2])
    QTest.keyClick(window.candidate_table, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert window.candidate_model.candidates == tuple(candidates)


def test_actions_follow_session_and_reset(window):
    image = InputImage("game.iso", 42, "ab" * 32, selected_platform="psp")
    window.session.set_image(image)
    assert window.pages.currentWidget() is window.image_page
    assert not window.analyze_action.isEnabled()
    assert not window.create_project_action.isEnabled()
    assert window.close_image_action.isEnabled()
    assert window.image_name.text() == "game.iso"
    window.close_image_action.trigger()
    assert not window.session.state.has_image
    assert not window.analyze_action.isEnabled()
    assert window.pages.currentWidget() is window.start_page


def test_open_button_and_actions_emit_requests(window):
    opening = QSignalSpy(window.open_image_requested)
    QTest.mouseClick(window.start_page.open_button, Qt.MouseButton.LeftButton)
    assert opening.count() == 1
    analyzing = QSignalSpy(window.analyze_requested)
    creating = QSignalSpy(window.create_project_requested)
    window.session.set_image(InputImage("game.iso", 42, "ab" * 32))
    assert not window.analyze_action.isEnabled()
    assert not window.create_project_action.isEnabled()


def test_services_and_session_can_be_injected(app):
    services = StudioServices()
    session = SessionModel()
    image = InputImage("game.iso", 42, "ab" * 32)
    session.set_image(image)
    window = MainWindow(session=session, services=services)
    try:
        assert window.services is services
        assert window.session is session
        assert not window.analyze_action.isEnabled()
        assert services.platforms.available() == ()
    finally:
        window.close()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    # The former window must not be called after its destruction.
    session.clear()


def test_issues_are_displayed_as_plain_text(window):
    window.log_panel.add_issue(ValidationIssue("error", "invalid", "<bad> input", resource_id="r1"))
    assert "Error · <bad> input (r1)" in window.log_panel.toPlainText()


def test_repeated_open_close_without_qt_warnings(app):
    messages = []
    previous = qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    try:
        for _ in range(5):
            window = MainWindow()
            window.show()
            app.processEvents()
            window.close()
            window.deleteLater()
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
    finally:
        qInstallMessageHandler(previous)
    assert messages == []


def test_light_panels_keep_readable_text_with_dark_system_palette(app):
    original_palette = QPalette(app.palette())
    dark_palette = QPalette(original_palette)
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        dark_palette.setColor(role, QColor("#ffffff"))
    for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button):
        dark_palette.setColor(role, QColor("#202020"))
    app.setPalette(dark_palette)
    window = MainWindow()
    try:
        window.show()
        app.processEvents()
        for widget, role in (
            (window.log_panel, QPalette.ColorRole.Text),
            (window.resources_dock, QPalette.ColorRole.WindowText),
            (window.image_details, QPalette.ColorRole.WindowText),
            (window.menuBar(), QPalette.ColorRole.WindowText),
        ):
            foreground = widget.palette().color(role)
            assert foreground.lightnessF() < 0.5, widget.objectName()
        assert window.log_panel.palette().color(QPalette.ColorRole.Base).lightnessF() > 0.9
        window._show_information()
        app.processEvents()
        dialog = window.information_dialog
        details = dialog.findChild(QPlainTextEdit)
        assert dialog.palette().color(QPalette.ColorRole.Window).lightnessF() > 0.9
        assert details.palette().color(QPalette.ColorRole.Base).lightnessF() > 0.9
        assert details.palette().color(QPalette.ColorRole.Text).lightnessF() < 0.5
        dialog.close()
    finally:
        window.close()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.setPalette(original_palette)


def test_original_and_target_language_popups_use_light_background(window, app, monkeypatch, tmp_path):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QFileDialog, QInputDialog, QLineEdit
    from romkit_core.workspace import WorkspaceManager
    from romkit_studio.dialogs.open_image_dialog import OpenImageDialog
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path))
    original_get_text = QInputDialog.getText
    observed = []
    def get_text(*args, **kwargs):
        def inspect_dialog():
            dialog = app.activeModalWidget()
            dialog.ensurePolished()
            edit = dialog.findChild(QLineEdit)
            observed.append((dialog.palette().color(QPalette.ColorRole.Window).lightnessF(),
                             edit.palette().color(QPalette.ColorRole.Base).lightnessF(),
                             edit.palette().color(QPalette.ColorRole.Text).lightnessF()))
            dialog.accept()
        QTimer.singleShot(0, inspect_dialog)
        return original_get_text(*args, **kwargs)
    monkeypatch.setattr(QInputDialog, "getText", get_text)
    result = OpenImageDialog().choose_project(window, WorkspaceManager(tmp_path))
    assert result is not None and len(observed) == 2
    assert all(background > .9 and base > .9 and text < .5 for background, base, text in observed)
