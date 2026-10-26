from PySide6.QtCore import QSortFilterProxyModel


class TranslationFilter(QSortFilterProxyModel):
    """Literal, case-insensitive search over editorial fields only."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.query = ""
        self.setDynamicSortFilter(False)

    def set_query(self, text):
        self.query = text.casefold().strip()
        self.invalidate()

    def filterAcceptsRow(self, row, parent):
        if not self.query:
            return True
        unit = self.sourceModel().session.records[row].unit
        return any(self.query in value.casefold() for value in (unit.id, unit.source, unit.target))
