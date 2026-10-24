from collections.abc import Iterable
import json
from pathlib import Path

from romkit_core.errors import SerializationError, ValidationError
from romkit_core.models import TranslationUnit
from romkit_core.models import common as v
from .io import atomic_write
from .schema import JSONL_FIELDS


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Campo duplicado: {key}")
        result[key] = value
    return result


def read_jsonl(path: str | Path) -> list[TranslationUnit]:
    path = Path(path)
    units, seen = [], set()
    with path.open("rb") as stream:
        for number, raw in enumerate(stream, 1):
            try:
                line = raw.decode("utf-8", errors="strict")
                if not line.strip():
                    raise ValueError("Línea vacía")
                data = json.loads(line, object_pairs_hook=_object)
                v.fields(data, JSONL_FIELDS | {"notes"}, JSONL_FIELDS)
                unit = TranslationUnit.from_dict(data)
                if unit.id in seen:
                    raise ValueError(f"ID duplicado: {unit.id}")
                seen.add(unit.id)
                units.append(unit)
            except (ValueError, TypeError, ValidationError) as exc:
                raise SerializationError(f"{path.name}, línea {number}: {exc}") from exc
    return units


def jsonl_content(units: Iterable[TranslationUnit]) -> str:
    units = list(units)
    if len({unit.id for unit in units}) != len(units):
        raise SerializationError("IDs de traducción duplicados")
    return "".join(json.dumps(unit.to_dict(), ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n" for unit in units)


def write_jsonl(path: str | Path, units: Iterable[TranslationUnit]) -> None:
    atomic_write(Path(path), jsonl_content(units))
