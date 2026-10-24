from PySide6.QtCore import QSortFilterProxyModel, Qt, QSize
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QLabel, QMainWindow, QMessageBox, QSplitter, QToolBar, QVBoxLayout, QWidget, QStyle, QProgressBar

from romkit_translator.dialogs.open_project_dialog import choose_project
from romkit_translator.models.translation_table_model import TranslationTableModel
from romkit_translator.services.project_session import ProjectSession
from romkit_translator.widgets.translation_editor import TranslationEditor
from romkit_translator.widgets.translation_table import TranslationTable
from romkit_core.icons import application_icon
from romkit_core import __version__
from romkit_core.ui_styles import BUTTON_STYLES, review_checkbox_style
from romkit_translator.services.suggestions import OnlineSuggestions


class MainWindow(QMainWindow):
    def __init__(self, *, session=None, suggestions=None):
        super().__init__()
        self.setWindowTitle("ROMKit Translator · v" + __version__)
        self.setWindowIcon(application_icon("translator"))
        self.setFixedSize(1280, 800)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.session = session if session is not None else ProjectSession()
        self.current_row = None
        self.suggestions = suggestions if suggestions is not None else OnlineSuggestions(self)
        self._suggestion_context = None
        self.suggestions.ready.connect(self._suggestion_ready)
        self.suggestions.failed.connect(self._suggestion_failed)
        self.open_action = QAction("Abrir proyecto…", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self._choose_project)
        self.save_action = QAction("Guardar", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.save_project)
        self.validate_action = QAction("Validar traducciones", self)
        self.validate_action.triggered.connect(self.validate_project)
        toolbar = QToolBar("Proyecto", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.open_action.setIcon(application_icon("open-project"))
        self.save_action.setIcon(application_icon("save"))
        self.validate_action.setIcon(application_icon("validate"))
        toolbar.setIconSize(QSize(24, 24))
        toolbar.addActions([self.open_action, self.save_action, self.validate_action])
        toolbar.setFloatable(False)
        self.addToolBar(toolbar)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 12, 16, 12)
        self.project_label = QLabel("Abre una carpeta con project.toml para comenzar.")
        self.project_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.project_label)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        self.feedback.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.feedback)
        splitter = QSplitter()
        self.table = TranslationTable()
        self.model = TranslationTableModel(self.session, self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setDynamicSortFilter(False)
        self.proxy.setSourceModel(self.model)
        self.table.setModel(self.proxy)
        self.table.setColumnWidth(0, 90)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 170)
        self.table.setColumnWidth(3, 170)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.editor = TranslationEditor()
        splitter.addWidget(self.table)
        splitter.addWidget(self.editor)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)
        self.setCentralWidget(central)
        self.table.selectionModel().currentChanged.connect(self._selected)
        self.editor.unit_changed.connect(self._edited)
        self.editor.suggestion_requested.connect(self._request_suggestion)
        self.setStyleSheet("""
            QWidget { background: #f5f7fa; color: #172b4d; }
            QWidget:disabled { color: #617087; }
            QToolBar, QMenuBar, QMenu { background: #ffffff; padding: 6px; }
            QToolBar { spacing: 8px; padding: 8px; border-bottom: 1px solid #dce2ea; }
            QMenuBar::item:selected, QMenu::item:selected { background: #2563eb; color: #ffffff; }
            QTableView, QPlainTextEdit, QComboBox { background: #ffffff; color: #172b4d; border: 1px solid #dce2ea; }
            QTableView { alternate-background-color: #eef3f8; selection-background-color: #2563eb; selection-color: white; }
            QHeaderView::section { background: #eaf0f6; color: #172b4d; padding: 6px; border: none; }
            QStatusBar { background: #ffffff; color: #52657d; }
        """ + BUTTON_STYLES + review_checkbox_style())
        self.translation_progress = QProgressBar()
        self.translation_progress.setObjectName('translationProgress')
        self.translation_progress.setRange(0, 1)
        self.translation_progress.setFixedWidth(260)
        self.translation_progress.setAccessibleName('Avance estimado de traducción')
        self.translation_progress.setToolTip('Cada entrada traducida o revisada cuenta una vez, aunque una revisada tenga traducción vacía. No mide la calidad ni la longitud del texto.')
        self.statusBar().addPermanentWidget(self.translation_progress)
        self.model.refresh()
        self._refresh_state()

    def _choose_project(self):
        root = choose_project(self)
        if root is not None:
            self.open_project(root)

    def open_project(self, root):
        if not self._confirm_dirty():
            return False
        try:
            self.session.load(root)
        except Exception as exc:
            self.feedback.setText(f"No se pudo abrir el proyecto: {exc}")
            return False
        self.current_row = None
        self.editor.load_unit(None)
        self.model.refresh()
        self.project_label.setText(f"{self.session.root.name} · {self.session.config.source_language} → {self.session.config.target_language}")
        self.feedback.clear()
        self._refresh_state()
        if self.model.rowCount():
            self.table.setCurrentIndex(self.proxy.index(0, 0))
        return True

    def _selected(self, current, previous):
        self.suggestions.cancel()
        self._suggestion_context = None
        source = self.proxy.mapToSource(current)
        self.current_row = source.row() if source.isValid() else None
        self.editor.load_unit(self.session.records[self.current_row].unit if self.current_row is not None else None)

    def _request_suggestion(self):
        if self.current_row is None or self.session.config is None:
            return
        unit = self.session.records[self.current_row].unit
        self._suggestion_context = object()
        self.editor.set_suggestion_busy(True)
        self.suggestions.request(self._suggestion_context, unit.source,
                                 self.session.config.source_language, self.session.config.target_language)

    def _suggestion_ready(self, context, text):
        if context is self._suggestion_context and self.current_row is not None:
            self.editor.show_suggestion(text)

    def _suggestion_failed(self, context, message):
        if context is self._suggestion_context:
            self.editor.set_suggestion_busy(False)
            self.editor.suggestion_feedback.setText(message)

    def _edited(self, unit):
        if self.current_row is None:
            return
        self.session.update(self.current_row, target=unit.target, status=unit.status.value, notes=unit.notes)
        self.model.update_row(self.current_row)
        self._refresh_state()

    def _refresh_state(self):
        translated, total = self.session.progress
        percentage = translated * 100 / total if total else 0
        self.translation_progress.setRange(0, max(total, 1))
        self.translation_progress.setValue(translated)
        self.translation_progress.setFormat(f'{percentage:.3f}% completado')
        self.statusBar().showMessage(f"{translated} / {total} traducidas o revisadas" + (" · Cambios sin guardar" if self.session.dirty else ""))
        self.save_action.setEnabled(self.session.dirty)
        self.validate_action.setEnabled(self.session.root is not None)
        self.setWindowTitle("ROMKit Translator · v" + __version__ + (" *" if self.session.dirty else ""))

    def save_project(self):
        try:
            self.session.save()
        except Exception as exc:
            self.feedback.setText(f"No se pudo guardar: {exc}")
            self._refresh_state()
            return False
        self.feedback.setText("Traducciones guardadas.")
        self._refresh_state()
        return True

    def validate_project(self):
        for row in range(len(self.session.records)):
            self.model.update_row(row)
        errors = sum(not value.valid for row, value in enumerate(self.model.validations)
                     if self.session.records[row].unit.status.value != "untranslated")
        self.feedback.setText(f"Validación terminada · {errors} entradas con errores.")

    def _confirm_dirty(self):
        if not self.session.dirty:
            return True
        choice = QMessageBox.question(self, "Cambios sin guardar", "¿Quieres guardar los cambios antes de continuar?",
                                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                      QMessageBox.StandardButton.Cancel)
        if choice == QMessageBox.StandardButton.Save:
            return self.save_project()
        return choice == QMessageBox.StandardButton.Discard

    def closeEvent(self, event):
        if self._confirm_dirty():
            self.suggestions.cancel()
            event.accept()
        else:
            event.ignore()
