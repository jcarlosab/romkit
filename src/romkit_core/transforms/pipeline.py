from collections.abc import Sequence
from dataclasses import dataclass, field

from romkit_core.errors import TransformError, ValidationError
from romkit_core.models import common as v
from .base import TransformContext, json_parameters
from .registry import TransformRegistry


@dataclass(frozen=True)
class TransformStep:
    handler_id: str
    parameters: dict = field(default_factory=dict)

    def __post_init__(self):
        v.platform(self.handler_id)
        object.__setattr__(self, "parameters", json_parameters(self.parameters))

    def to_dict(self):
        return {"handler_id": self.handler_id, "parameters": json_parameters(self.parameters)}

    @classmethod
    def from_dict(cls, data):
        return cls(**v.fields(data, {"handler_id", "parameters"}, {"handler_id"}))


@dataclass(frozen=True)
class TransformChain(v.JsonModel):
    steps: tuple[TransformStep, ...] = ()
    schema_version: int = 1

    def __post_init__(self):
        v.integer(self.schema_version, "schema_version", minimum=1)
        if self.schema_version != 1:
            raise ValidationError(f"Unsupported transform schema: {self.schema_version}")
        if not isinstance(self.steps, (tuple, list)) or not all(isinstance(step, TransformStep) for step in self.steps):
            raise ValidationError("steps must contain TransformStep objects")
        object.__setattr__(self, "steps", tuple(TransformStep.from_dict(step.to_dict()) for step in self.steps))

    def to_dict(self):
        return {"schema_version": self.schema_version, "steps": [step.to_dict() for step in self.steps]}

    @classmethod
    def from_dict(cls, data):
        values = v.fields(data, {"schema_version", "steps"}, {"schema_version", "steps"})
        if not isinstance(values["steps"], list):
            raise ValidationError("steps must be a list")
        return cls(tuple(TransformStep.from_dict(step) for step in values["steps"]), values["schema_version"])


@dataclass(frozen=True)
class TransformResult:
    data: bytes
    chain: TransformChain


class TransformPipeline:
    def __init__(self, registry: TransformRegistry | None = None):
        self.registry = registry if registry is not None else TransformRegistry()

    def _apply(self, data: bytes | memoryview, chain: TransformChain, operation: str, resource_id: str | None) -> bytes:
        if not isinstance(data, (bytes, memoryview)):
            raise TransformError("Transform input must be bytes or memoryview")
        # Resolve the complete chain first: an unknown handler never starts a
        # partial operation. Encoding reverses decoding order.
        steps = [(step, self.registry.resolve(step.handler_id)) for step in chain.steps]
        if operation == "encode":
            steps.reverse()
        result = bytes(data)
        for step, handler in steps:
            context = TransformContext(step.parameters, resource_id)
            try:
                result = getattr(handler, operation)(result, context)
            except Exception as exc:
                raise TransformError(f"{operation} failed for transform {step.handler_id}") from exc
            if not isinstance(result, bytes):
                raise TransformError(f"Transform {step.handler_id} did not return bytes")
        return result

    def decode(self, data: bytes | memoryview, steps: Sequence[TransformStep], *, resource_id: str | None = None) -> TransformResult:
        chain = TransformChain(tuple(steps))
        return TransformResult(self._apply(data, chain, "decode", resource_id), chain)

    def encode(self, data: bytes | memoryview, chain: TransformChain, *, resource_id: str | None = None) -> bytes:
        return self._apply(data, chain, "encode", resource_id)
