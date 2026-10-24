from collections import Counter
from dataclasses import dataclass

from romkit_core.models import TranslationUnit, ValidationIssue


@dataclass(frozen=True)
class TranslationValidation:
    encoded_bytes: int | None
    max_bytes: int | None
    issues: tuple[ValidationIssue, ...]

    @property
    def valid(self):
        return not any(issue.severity.value == "error" for issue in self.issues)


def validate_translation(unit: TranslationUnit) -> TranslationValidation:
    issues, used = [], None
    def error(code, message):
        issues.append(ValidationIssue("error", code, message, translation_unit_id=unit.id))
    if unit.encoding:
        try:
            used = len(unit.target.encode(unit.encoding, errors="strict"))
        except UnicodeEncodeError:
            error("unencodable", f"La traducción contiene caracteres no representables en {unit.encoding}")
        except LookupError:
            error("unknown_encoding", f"Codificación no disponible: {unit.encoding}")
    if used is not None and unit.constraints.max_bytes is not None and used > unit.constraints.max_bytes:
        error("max_bytes", f"La traducción usa {used} bytes; el límite es {unit.constraints.max_bytes}")
    if unit.constraints.max_chars is not None and len(unit.target) > unit.constraints.max_chars:
        error("max_chars", f"La traducción supera {unit.constraints.max_chars} caracteres")
    if unit.constraints.max_lines is not None and len(unit.target.splitlines() or [""]) > unit.constraints.max_lines:
        error("max_lines", f"La traducción supera {unit.constraints.max_lines} líneas")
    # Check occurrence counts too: keeping one copy cannot hide losing another.
    for token in Counter(unit.tokens):
        if unit.source.count(token) != unit.target.count(token):
            error("token", f"Debe conservarse el control protegido {token!r} y su número de apariciones")
    return TranslationValidation(used, unit.constraints.max_bytes, tuple(issues))
