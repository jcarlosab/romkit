from dataclasses import replace

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QCheckBox, QLabel, QPlainTextEdit, QVBoxLayout, QWidget, QPushButton, QHBoxLayout

from romkit_core.validation import validate_translation
from romkit_core.icons import application_icon


class TranslationEditor(QWidget):
    unit_changed = Signal(object)
    suggestion_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._unit = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        self.unit_label = QLabel("Selecciona una entrada")
        self.unit_label.setTextFormat(Qt.TextFormat.PlainText)
        self.unit_label.setWordWrap(True)
        layout.addWidget(self.unit_label)
        layout.addWidget(QLabel("Original"))
        self.source = QPlainTextEdit()
        self.source.setReadOnly(True)
        layout.addWidget(self.source)
        translation_heading = QHBoxLayout()
        translation_heading.addWidget(QLabel("Traducción"))
        translation_heading.addStretch()
        self.suggest_button = QPushButton("Sugerir traducción")
        self.suggest_button.setIcon(application_icon("suggest"))
        self.suggest_button.setToolTip("Consultar MyMemory online con el texto original seleccionado")
        self.suggest_button.clicked.connect(self.suggestion_requested.emit)
        translation_heading.addWidget(self.suggest_button)
        layout.addLayout(translation_heading)
        self.target = QPlainTextEdit()
        layout.addWidget(self.target)
        self.suggestion_feedback = QLabel("Sugerencias online: MyMemory. Se envía solo el texto original seleccionado.")
        self.suggestion_feedback.setWordWrap(True)
        self.suggestion_feedback.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.suggestion_feedback)
        self.suggestion = QPlainTextEdit()
        self.suggestion.setReadOnly(True)
        self.suggestion.setMaximumHeight(100)
        self.suggestion.hide()
        layout.addWidget(self.suggestion)
        self.use_suggestion_button = QPushButton("Usar sugerencia")
        self.use_suggestion_button.setIcon(application_icon("apply"))
        self.use_suggestion_button.setObjectName("primaryButton")
        self.use_suggestion_button.clicked.connect(self._use_suggestion)
        self.use_suggestion_button.hide()
        layout.addWidget(self.use_suggestion_button)
        self.reviewed = QCheckBox("Revisada")
        self.reviewed.setObjectName("reviewedCheckBox")
        layout.addWidget(self.reviewed)
        layout.addWidget(QLabel("Notas"))
        self.notes = QPlainTextEdit()
        self.notes.setMaximumHeight(100)
        layout.addWidget(self.notes)
        self.validation = QLabel()
        self.validation.setWordWrap(True)
        self.validation.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.validation)
        self.target.textChanged.connect(self._target_changed)
        self.reviewed.toggled.connect(self._changed)
        self.notes.textChanged.connect(self._changed)
        self.setEnabled(False)

    def load_unit(self, unit):
        self._unit = unit
        blockers = [QSignalBlocker(widget) for widget in (self.target, self.notes, self.reviewed)]
        self.source.setPlainText(unit.source if unit else "")
        self.target.setPlainText(unit.target if unit else "")
        self.notes.setPlainText(unit.notes if unit else "")
        self.reviewed.setChecked(unit is not None and unit.status.value == "reviewed")
        self.suggestion.clear()
        self.suggestion.hide()
        self.use_suggestion_button.hide()
        self.suggest_button.setEnabled(unit is not None)
        self.suggestion_feedback.setText("Sugerencias online: MyMemory. Se envía solo el texto original seleccionado.")
        self.unit_label.setText(unit.id if unit else "Selecciona una entrada")
        self.setEnabled(unit is not None)
        self._validate()
        del blockers

    def _changed(self):
        if self._unit is None:
            return
        status = "reviewed" if self.reviewed.isChecked() else (
            "translated" if self.target.toPlainText() or self._unit.status.value == "translated" else "untranslated")
        self._unit = replace(self._unit, target=self.target.toPlainText(), status=status, notes=self.notes.toPlainText())
        self._validate()
        self.unit_changed.emit(self._unit)

    def _target_changed(self):
        if self._unit is None:
            return
        blocker = QSignalBlocker(self.reviewed)
        self.reviewed.setChecked(False)
        del blocker
        self._unit = replace(self._unit, status="translated" if self.target.toPlainText() else "untranslated")
        self._changed()

    def set_suggestion_busy(self, busy):
        self.suggest_button.setEnabled(self._unit is not None and not busy)
        if busy:
            self.suggestion_feedback.setText("Consultando MyMemory…")

    def show_suggestion(self, text):
        self.set_suggestion_busy(False)
        self.suggestion.setPlainText(text)
        self.suggestion.show()
        self.use_suggestion_button.show()
        validation = validate_translation(replace(self._unit, target=text))
        message = "Propuesta de MyMemory. Revísala antes de usarla."
        if not validation.valid:
            message += "\n" + "\n".join(issue.message for issue in validation.issues)
        self.suggestion_feedback.setText(message)

    def _use_suggestion(self):
        self.target.setPlainText(self.suggestion.toPlainText())
        self.suggestion.hide()
        self.use_suggestion_button.hide()

    def _validate(self):
        if self._unit is None:
            self.validation.clear()
            return
        result = validate_translation(self._unit)
        usage = "Tamaño desconocido" if result.encoded_bytes is None else f"{result.encoded_bytes} bytes usados"
        if result.max_bytes is not None:
            usage += f" · Límite: {result.max_bytes} bytes"
        details = [usage]
        if self._unit.encoding:
            details.append(f"Codificación: {self._unit.encoding}")
        if self._unit.tokens:
            details.append("Controles protegidos: " + ", ".join(self._unit.tokens))
        details.extend(issue.message for issue in result.issues)
        self.validation.setText("\n".join(details))
        self.validation.setStyleSheet("color: #b42318;" if not result.valid else "color: #52657d;")
