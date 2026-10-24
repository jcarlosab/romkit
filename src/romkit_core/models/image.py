from dataclasses import dataclass
from pathlib import Path

from . import common as v


@dataclass(frozen=True)
class InputImage(v.JsonModel):
    path: Path
    size_bytes: int
    sha256: str
    detected_platform: str | None = None
    selected_platform: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "path", v.path(self.path))
        v.integer(self.size_bytes, "size_bytes")
        v.sha256(self.sha256)
        v.platform(self.detected_platform, optional=True)
        v.platform(self.selected_platform, optional=True)

    def to_dict(self) -> dict:
        return {"path": str(self.path), "size_bytes": self.size_bytes, "sha256": self.sha256,
                "detected_platform": self.detected_platform, "selected_platform": self.selected_platform}

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**v.fields(data, {"path", "size_bytes", "sha256", "detected_platform", "selected_platform"}, {"path", "size_bytes", "sha256"}))
