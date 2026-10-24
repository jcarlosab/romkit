from dataclasses import dataclass, field

from romkit_core.errors import ValidationError
from . import common as v


@dataclass(frozen=True)
class TextConstraints(v.JsonModel):
    max_bytes: int | None = None
    max_chars: int | None = None
    max_lines: int | None = None

    def __post_init__(self):
        for name in ("max_bytes", "max_chars", "max_lines"):
            if (value := getattr(self, name)) is not None:
                v.integer(value, name)

    def to_dict(self) -> dict:
        return {name: getattr(self, name) for name in ("max_bytes", "max_chars", "max_lines") if getattr(self, name) is not None}

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**v.fields(data, {"max_bytes", "max_chars", "max_lines"}, set()))


@dataclass(frozen=True)
class TranslationUnit(v.JsonModel):
    id: str
    source: str
    target: str = ""
    status: v.TranslationStatus = v.TranslationStatus.UNTRANSLATED
    context: str = ""
    encoding: str | None = None
    constraints: TextConstraints = field(default_factory=TextConstraints)
    tokens: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self):
        v.text(self.id, "id")
        v.text(self.source, "source")
        v.text(self.target, "target", empty=True)
        v.text(self.context, "context", empty=True)
        v.text(self.notes, "notes", empty=True)
        if self.encoding is not None:
            v.text(self.encoding, "encoding")
        if not isinstance(self.constraints, TextConstraints):
            raise ValidationError("constraints must be TextConstraints")
        object.__setattr__(self, "status", v.enum_value(v.TranslationStatus, self.status, "status"))
        object.__setattr__(self, "tokens", v.strings(self.tokens, "tokens"))

    def to_dict(self) -> dict:
        return {"id": self.id, "source": self.source, "target": self.target,
                "status": self.status.value, "context": self.context, "encoding": self.encoding,
                "constraints": self.constraints.to_dict(), "tokens": list(self.tokens), "notes": self.notes}

    @classmethod
    def from_dict(cls, data: dict):
        values = dict(v.fields(data, {"id", "source", "target", "status", "context", "encoding", "constraints", "tokens", "notes"}, {"id", "source"}))
        if "constraints" in values:
            values["constraints"] = TextConstraints.from_dict(values["constraints"])
        return cls(**values)


@dataclass(frozen=True)
class ValidationIssue(v.JsonModel):
    severity: v.Severity
    code: str
    message: str
    resource_id: str | None = None
    translation_unit_id: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "severity", v.enum_value(v.Severity, self.severity, "severity"))
        for name in ("code", "message"):
            v.text(getattr(self, name), name)
        for name in ("resource_id", "translation_unit_id"):
            if getattr(self, name) is not None:
                v.text(getattr(self, name), name)

    def to_dict(self) -> dict:
        return {"severity": self.severity.value, "code": self.code, "message": self.message,
                "resource_id": self.resource_id, "translation_unit_id": self.translation_unit_id}

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**v.fields(data, {"severity", "code", "message", "resource_id", "translation_unit_id"}, {"severity", "code", "message"}))
