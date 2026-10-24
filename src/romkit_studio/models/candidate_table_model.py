from bisect import bisect_left

from PySide6.QtCore import QAbstractTableModel, QSortFilterProxyModel, Qt, Signal


class CandidateTableModel(QAbstractTableModel):
    confirmation_changed = Signal()
    HEADERS = ("Exportar", "Texto", "Archivo de origen", "Codificación", "Confianza")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.candidates = ()
        self.checked = set()
        self._removal_history = []

    def set_candidates(self, candidates):
        self.beginResetModel()
        self.candidates = tuple(candidates)
        self.checked.clear()
        self._removal_history.clear()
        self.endResetModel()
        self.confirmation_changed.emit()

    def confirmed(self):
        return [candidate for row, candidate in enumerate(self.candidates) if row in self.checked]

    def select_compatible(self, rows=None, *, add=False):
        """Select one interpretation of each byte range, including its terminator."""
        selected = set(self.checked) if add else set()
        intervals = {}
        for row in sorted(selected, key=lambda row: self.candidates[row].offset):
            candidate = self.candidates[row]
            intervals.setdefault(candidate.logical_path, []).append((candidate.offset,
                candidate.offset + candidate.length_bytes + len(candidate.terminator)))
        rows = range(len(self.candidates)) if rows is None else rows
        ordered = sorted(((row, self.candidates[row]) for row in rows), key=lambda item: (
            item[1].logical_path, item[1].offset, -item[1].confidence,
            -item[1].length_bytes, item[1].encoding))
        for row, candidate in ordered:
            if row in selected:
                continue
            ranges = intervals.setdefault(candidate.logical_path, [])
            start, end = candidate.offset, candidate.offset + candidate.length_bytes + len(candidate.terminator)
            position = bisect_left(ranges, (start,))
            if position and ranges[position - 1][1] > start:
                continue
            if position < len(ranges) and ranges[position][0] < end:
                continue
            selected.add(row)
            ranges.insert(position, (start, end))
        self._set_checked(selected)

    def clear_confirmation(self):
        self._set_checked(set())

    def uncheck_rows(self, rows):
        self._set_checked(self.checked.difference(rows))

    @property
    def can_restore_removal(self):
        return bool(self._removal_history)

    def remove_rows(self, rows):
        removed = {row for row in rows if 0 <= row < len(self.candidates)}
        if not removed:
            return
        self._removal_history.append((self.candidates, set(self.checked), removed))
        self._removal_history = self._removal_history[-10:]
        survivors = [(row, candidate) for row, candidate in enumerate(self.candidates) if row not in removed]
        self.beginResetModel()
        self.candidates = tuple(candidate for row, candidate in survivors)
        self.checked = {new_row for new_row, (old_row, candidate) in enumerate(survivors) if old_row in self.checked}
        self.endResetModel()
        self.confirmation_changed.emit()

    def restore_removal(self):
        if not self._removal_history:
            return
        candidates, previous_checks, removed = self._removal_history.pop()
        checked, surviving_row = set(), 0
        for old_row in range(len(candidates)):
            if old_row in removed:
                if old_row in previous_checks:
                    checked.add(old_row)
            else:
                if surviving_row in self.checked:
                    checked.add(old_row)
                surviving_row += 1
        self.beginResetModel()
        self.candidates, self.checked = candidates, checked
        self.endResetModel()
        self.confirmation_changed.emit()

    def _set_checked(self, selected):
        self.checked = selected
        if self.candidates:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.candidates) - 1, 0),
                                  [Qt.ItemDataRole.CheckStateRole])
        self.confirmation_changed.emit()

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.candidates)

    def columnCount(self, parent=None):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]

    def flags(self, index):
        flags = super().flags(index)
        return flags | Qt.ItemFlag.ItemIsUserCheckable if index.column() == 0 else flags

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        candidate = self.candidates[index.row()]
        if index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole:
            return Qt.CheckState.Checked if index.row() in self.checked else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.DisplayRole:
            return ("", candidate.text, candidate.logical_path, candidate.encoding, f"{candidate.confidence:.0%}")[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"Offset: {candidate.offset} · {candidate.length_bytes} bytes\n" + "\n".join(candidate.evidence)
        if role == Qt.ItemDataRole.UserRole:
            return f"{candidate.text}\n{candidate.logical_path}\n{candidate.encoding}"

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if index.isValid() and index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole:
            if value in (Qt.CheckState.Checked, Qt.CheckState.Checked.value):
                self.checked.add(index.row())
            else:
                self.checked.discard(index.row())
            self.dataChanged.emit(index, index, [role])
            self.confirmation_changed.emit()
            return True
        return False


class CandidateFilterModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterRole(Qt.ItemDataRole.UserRole)
        self.setFilterKeyColumn(1)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setDynamicSortFilter(False)
