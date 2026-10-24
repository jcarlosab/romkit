from enum import StrEnum
from pathlib import Path
from typing import Any
import json
import re

from romkit_core.errors import SerializationError, ValidationError


class Platform(StrEnum):
    PSP = "psp"
    PS1 = "ps1"
    SATURN = "saturn"


class AnalysisStatus(StrEnum):
    UNKNOWN = "unknown"
    PENDING = "pending"
    ANALYZED = "analyzed"
    FAILED = "failed"


class TranslationStatus(StrEnum):
    UNTRANSLATED = "untranslated"
    TRANSLATED = "translated"
    REVIEWED = "reviewed"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def text(value: Any, field: str, *, empty: bool = False) -> None:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ValidationError(f"{field} must be a {'string' if empty else 'non-empty string'}")


def integer(value: Any, field: str, *, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValidationError(f"{field} must be an integer >= {minimum}")


def sha256(value: Any) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValidationError("sha256 must contain 64 lowercase hexadecimal digits")


def platform(value: Any, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    # Backend IDs remain extensible beyond the built-in Platform enum.
    if not isinstance(value, str) or re.fullmatch(r"[a-z][a-z0-9_-]*", value) is None:
        raise ValidationError("platform must be a non-empty lowercase backend ID")


def strings(value: Any, field: str, *, required: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or (required and not value):
        raise ValidationError(f"{field} must be {'a non-empty' if required else 'a'} list or tuple")
    for item in value:
        text(item, field)
    return tuple(value)


def enum_value(kind, value, field):
    try:
        return kind(value)
    except (ValueError, TypeError) as exc:
        raise ValidationError(f"Invalid {field}: {value!r}") from exc


def fields(data: Any, allowed: set[str], required: set[str]) -> dict:
    if not isinstance(data, dict):
        raise ValidationError("Expected an object")
    if missing := required - data.keys():
        raise ValidationError(f"Missing fields: {sorted(missing)}")
    if unknown := data.keys() - allowed:
        raise ValidationError(f"Unknown fields: {sorted(unknown)}")
    return data


def safe_logical_path(value: Any) -> None:
    text(value, "logical_path")
    if "\\" in value or ":" in value or value.startswith("/") or any(part in ("", ".", "..") for part in value.split("/")):
        raise ValidationError("logical_path must be a relative POSIX path without traversal")


def path(value: Any) -> Path:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise ValidationError("path must be a non-empty path")
    return Path(value)


class JsonModel:
    """JSON transport delegates to each model's explicit field mapping."""

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, allow_nan=False)

    @classmethod
    def from_json(cls, content: str):
        try:
            data = json.loads(content)
        except (ValueError, TypeError) as exc:
            raise SerializationError("Invalid JSON document") from exc
        return cls.from_dict(data)
