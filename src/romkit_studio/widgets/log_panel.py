from PySide6.QtWidgets import QPlainTextEdit, QWidget

from romkit_core.models import ValidationIssue


class LogPanel(QPlainTextEdit):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("logPanel")
        self.setReadOnly(True)
        self.setMaximumBlockCount(1000)
        self.setPlaceholderText("La actividad y los avisos aparecerán aquí.")

    def add_message(self, message: str) -> None:
        self.appendPlainText(message)

    def add_issue(self, issue: ValidationIssue) -> None:
        labels = {"info": "Información", "warning": "Aviso", "error": "Error"}
        related = issue.translation_unit_id or issue.resource_id
        suffix = f" ({related})" if related else ""
        self.add_message(f"{labels[issue.severity.value]} · {issue.message}{suffix}")
