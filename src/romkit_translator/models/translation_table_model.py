from PySide6.QtCore import QAbstractTableModel, Qt
from PySide6.QtGui import QColor

from romkit_core.validation import validate_translation

STATUS_LABELS = {"untranslated": "Pendiente", "translated": "Traducida", "reviewed": "Revisada"}


class TranslationTableModel(QAbstractTableModel):
    HEADERS = ("Estado", "ID", "Original", "Traducción", "Validación")

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.validations = []

    def refresh(self):
        self.beginResetModel()
        self.validations = [validate_translation(record.unit) for record in self.session.records]
        self.endResetModel()

    def update_row(self, row):
        self.validations[row] = validate_translation(self.session.records[row].unit)
        self.dataChanged.emit(self.index(row, 0), self.index(row, len(self.HEADERS) - 1))

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.session.records)

    def columnCount(self, parent=None):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        unit = self.session.records[index.row()].unit
        validation = self.validations[index.row()]
        if role == Qt.ItemDataRole.ForegroundRole and unit.status.value != "untranslated" and not validation.valid:
            return QColor("#b42318")
        if role == Qt.ItemDataRole.ToolTipRole:
            if index.column() in (1, 2, 3):
                return (unit.id, unit.source, unit.target)[index.column() - 1]
            return "\n".join(issue.message for issue in validation.issues)
        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 4:
                if unit.status.value == "untranslated":
                    return "Pendiente"
                if not validation.valid:
                    return " · ".join(issue.message for issue in validation.issues)
                if validation.encoded_bytes is not None:
                    maximum = f" / {validation.max_bytes}" if validation.max_bytes is not None else ""
                    return f"{validation.encoded_bytes}{maximum} bytes"
                return "Correcta"
            return (STATUS_LABELS[unit.status.value], unit.id, unit.source, unit.target)[index.column()]
