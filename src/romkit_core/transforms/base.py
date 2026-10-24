from dataclasses import dataclass, field
import json
from typing import Protocol, runtime_checkable

from romkit_core.errors import ValidationError
from romkit_core.models import common as v
from romkit_core.platforms.base import ProbeResult


def json_parameters(parameters: dict) -> dict:
    """Take a JSON snapshot. Persist only public reconstruction parameters, no keys."""
    if not isinstance(parameters, dict) or not all(isinstance(key, str) for key in parameters):
        raise ValidationError("Transform parameters must be a JSON object with string keys")
    try:
        return json.loads(json.dumps(parameters, allow_nan=False))
    except (ValueError, TypeError) as exc:
        raise ValidationError("Transform parameters must be JSON serializable") from exc


@dataclass(frozen=True)
class Detection:
    matched: bool
    confidence: float = 0.0
    evidence: tuple[str, ...] = ()

    def __post_init__(self):
        result = ProbeResult(self.matched, self.confidence, self.evidence)
        object.__setattr__(self, "evidence", result.evidence)


@dataclass(frozen=True)
class TransformContext:
    parameters: dict = field(default_factory=dict)
    resource_id: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "parameters", json_parameters(self.parameters))
        if self.resource_id is not None:
            v.text(self.resource_id, "resource_id")


@runtime_checkable
class TransformHandler(Protocol):
    id: str

    def detect(self, data: bytes | memoryview) -> Detection: ...

    def decode(self, data: bytes | memoryview, context: TransformContext) -> bytes: ...

    def encode(self, data: bytes | memoryview, context: TransformContext) -> bytes: ...


class IdentityTransform:
    id = "identity"

    def detect(self, data: bytes | memoryview) -> Detection:
        return Detection(True, 1.0, ("Explicit no-op transformation",))

    def decode(self, data: bytes | memoryview, context: TransformContext) -> bytes:
        return bytes(data)

    def encode(self, data: bytes | memoryview, context: TransformContext) -> bytes:
        return bytes(data)
