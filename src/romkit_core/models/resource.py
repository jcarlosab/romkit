from dataclasses import dataclass

from . import common as v


@dataclass(frozen=True)
class ResourceEntry(v.JsonModel):
    resource_id: str
    logical_path: str
    size_bytes: int
    sha256: str
    detected_type: str = "unknown"
    analysis_status: v.AnalysisStatus = v.AnalysisStatus.UNKNOWN
    type_status: str = "unknown"
    extension: str = ""

    def __post_init__(self):
        v.text(self.resource_id, "resource_id")
        v.safe_logical_path(self.logical_path)
        v.integer(self.size_bytes, "size_bytes")
        v.sha256(self.sha256)
        v.text(self.detected_type, "detected_type")
        object.__setattr__(self, "analysis_status", v.enum_value(v.AnalysisStatus, self.analysis_status, "analysis_status"))
        if self.type_status not in {"known", "candidate", "unknown"}:
            from romkit_core.errors import ValidationError
            raise ValidationError("Invalid type_status")
        v.text(self.extension, "extension", empty=True)

    def to_dict(self) -> dict:
        return {"resource_id": self.resource_id, "logical_path": self.logical_path,
                "size_bytes": self.size_bytes, "sha256": self.sha256,
                "detected_type": self.detected_type, "analysis_status": self.analysis_status.value,
                "type_status": self.type_status, "extension": self.extension}

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**v.fields(data, {"resource_id", "logical_path", "size_bytes", "sha256", "detected_type", "analysis_status", "type_status", "extension"}, {"resource_id", "logical_path", "size_bytes", "sha256"}))
