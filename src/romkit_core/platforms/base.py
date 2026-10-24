"""Platform contracts only: implementations are registered by application setup."""

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Protocol, runtime_checkable

from romkit_core.errors import ValidationError
from romkit_core.models import InputImage, ResourceEntry, ValidationIssue
from romkit_core.models import common as v


@dataclass(frozen=True)
class ProbeResult:
    compatible: bool
    confidence: float = 0.0
    evidence: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.compatible) is not bool:
            raise ValidationError("compatible must be a bool")
        if type(self.confidence) not in (int, float) or not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValidationError("confidence must be a finite number between 0 and 1")
        object.__setattr__(self, "evidence", v.strings(self.evidence, "evidence"))


@dataclass(frozen=True)
class PlatformImage:
    backend_id: str
    source: InputImage

    def __post_init__(self):
        v.platform(self.backend_id)
        if not isinstance(self.source, InputImage):
            raise ValidationError("source must be InputImage")


@dataclass(frozen=True)
class ExtractionResult:
    destination: Path
    resources: tuple[ResourceEntry, ...] = ()
    issues: tuple[ValidationIssue, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "destination", v.path(self.destination))
        for name, kind in (("resources", ResourceEntry), ("issues", ValidationIssue)):
            values = getattr(self, name)
            if not isinstance(values, (tuple, list)) or not all(isinstance(item, kind) for item in values):
                raise ValidationError(f"{name} must contain {kind.__name__} objects")
            object.__setattr__(self, name, tuple(values))


@runtime_checkable
class PlatformBackend(Protocol):
    id: str
    display_name: str

    def probe(self, path: Path) -> ProbeResult:
        """Inspect without modifying the input; provide evidence for compatibility."""
        ...

    def open_image(self, path: Path) -> PlatformImage: ...

    def list_resources(self, image: PlatformImage) -> list[ResourceEntry]: ...

    def extract(self, image: PlatformImage, destination: Path) -> ExtractionResult:
        """Write only to destination and preserve the original image."""
        ...
