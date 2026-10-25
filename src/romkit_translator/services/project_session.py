from dataclasses import dataclass, replace
from pathlib import Path

from romkit_core.errors import SerializationError, ValidationError
from romkit_core.models import TranslationStatus
from romkit_core.project import read_config, read_jsonl, write_jsonl


@dataclass(frozen=True)
class TranslationRecord:
    path: Path
    line: int
    unit: object


class ProjectSession:
    def __init__(self):
        self.root = None
        self.config = None
        self.records = []
        self._original_bytes = {}
        self._saved = {}

    def load(self, root: str | Path) -> None:
        root = Path(root).resolve(strict=True)
        config = read_config(root / "project.toml")
        text_root = root / "text"
        if not text_root.is_dir() or text_root.is_symlink():
            raise SerializationError("El proyecto necesita una carpeta text con archivos JSONL")
        records, original, saved, seen = [], {}, {}, set()
        files = sorted(text_root.glob("*.jsonl"))
        if not files:
            raise SerializationError("No hay archivos text/*.jsonl en el proyecto")
        for path in files:
            if path.is_symlink() or not path.resolve().is_relative_to(text_root):
                raise SerializationError("Un archivo de texto sale de la carpeta del proyecto")
            original[path] = path.read_bytes()
            units = read_jsonl(path)
            saved[path] = tuple(units)
            for line, unit in enumerate(units, 1):
                if unit.id in seen:
                    raise SerializationError(f"{path.name}, línea {line}: ID duplicado en el proyecto: {unit.id}")
                seen.add(unit.id)
                records.append(TranslationRecord(path, line, unit))
        # Commit only after all files validate; a bad project preserves the session.
        self.root, self.config = root, config
        self.records, self._original_bytes, self._saved = records, original, saved

    @property
    def progress(self):
        return sum(record.unit.status != TranslationStatus.UNTRANSLATED for record in self.records), len(self.records)

    def _grouped(self):
        grouped = {path: [] for path in self._saved}
        for record in self.records:
            grouped[record.path].append(record.unit)
        return grouped

    @property
    def dirty(self):
        return any(tuple(units) != self._saved[path] for path, units in self._grouped().items())

    def update(self, row: int, *, target: str, status: str, notes: str):
        record = self.records[row]
        unit = replace(record.unit, target=target, status=status, notes=notes)
        self.records[row] = replace(record, unit=unit)
        return unit

    def save(self):
        grouped = self._grouped()
        changed = {path: units for path, units in grouped.items() if tuple(units) != self._saved[path]}
        for path in changed:
            if path.is_symlink() or path.read_bytes() != self._original_bytes[path]:
                raise ValidationError(f"{path.name} cambió fuera de Translator; vuelve a abrir el proyecto antes de guardar")
        for path, units in changed.items():
            write_jsonl(path, units)
            # Track each successful atomic replacement, even if a later file fails.
            self._original_bytes[path] = path.read_bytes()
            self._saved[path] = tuple(units)

    def apply_character_plan(self, plan, *, undo=False):
        for change in plan.changes:
            expected=change.after if undo else change.before
            if not 0<=change.row<len(self.records) or self.records[change.row].unit!=expected:
                raise ValidationError('Los textos han cambiado desde la previsualización; vuelve a calcularla')
        for change in plan.changes:
            record=self.records[change.row]
            self.records[change.row]=replace(record,unit=change.before if undo else change.after)
