from dataclasses import dataclass, field
import codecs
import math

from romkit_core.errors import ValidationError
from romkit_core.transforms import TransformChain
from . import common as v


@dataclass(frozen=True)
class TextCandidate(v.JsonModel):
    resource_id: str
    logical_path: str
    offset: int
    encoding: str
    length_bytes: int
    text: str
    terminator: bytes = b""
    confidence: float = 0.0
    evidence: tuple[str, ...] = ()
    transforms: TransformChain = field(default_factory=TransformChain)

    def __post_init__(self):
        v.text(self.resource_id, "resource_id")
        v.safe_logical_path(self.logical_path)
        v.integer(self.offset, "offset")
        v.integer(self.length_bytes, "length_bytes", minimum=1)
        v.text(self.text, "text")
        v.text(self.encoding, "encoding")
        try:
            codecs.lookup(self.encoding)
        except LookupError as exc:
            raise ValidationError("Unknown candidate encoding") from exc
        if not isinstance(self.terminator, bytes):
            raise ValidationError("terminator must be bytes")
        if type(self.confidence) not in (int, float) or not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValidationError("Invalid candidate confidence")
        object.__setattr__(self, "evidence", v.strings(self.evidence, "evidence"))
        if not isinstance(self.transforms, TransformChain):
            raise ValidationError("transforms must be TransformChain")

    def to_dict(self):
        return {"resource_id": self.resource_id, "logical_path": self.logical_path, "offset": self.offset,
                "encoding": self.encoding, "length_bytes": self.length_bytes, "text": self.text,
                "terminator": self.terminator.hex(), "confidence": self.confidence,
                "evidence": list(self.evidence), "transforms": self.transforms.to_dict()}

    @classmethod
    def from_dict(cls, data):
        values = dict(v.fields(data, {"resource_id", "logical_path", "offset", "encoding", "length_bytes", "text", "terminator", "confidence", "evidence", "transforms"},
                               {"resource_id", "logical_path", "offset", "encoding", "length_bytes", "text"}))
        try:
            values["terminator"] = bytes.fromhex(values.get("terminator", ""))
        except (ValueError, TypeError) as exc:
            raise ValidationError("Invalid terminator hex") from exc
        if "transforms" in values:
            values["transforms"] = TransformChain.from_dict(values["transforms"])
        return cls(**values)
