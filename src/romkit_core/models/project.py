from dataclasses import dataclass
import json
import tomllib

from romkit_core.errors import SerializationError, ValidationError
from . import common as v


@dataclass(frozen=True)
class ProjectConfig(v.JsonModel):
    platform: str
    source_sha256: str
    source_language: str
    target_language: str
    schema_version: int = 1

    def __post_init__(self):
        v.platform(self.platform)
        v.sha256(self.source_sha256)
        v.text(self.source_language, "source_language")
        v.text(self.target_language, "target_language")
        v.integer(self.schema_version, "schema_version", minimum=1)
        if self.schema_version != 1:
            raise ValidationError(f"Unsupported project schema: {self.schema_version}")

    def to_dict(self) -> dict:
        return {"schema_version": self.schema_version, "platform": self.platform,
                "source_sha256": self.source_sha256, "source_language": self.source_language,
                "target_language": self.target_language}

    @classmethod
    def from_dict(cls, data: dict):
        names = {"schema_version", "platform", "source_sha256", "source_language", "target_language"}
        return cls(**v.fields(data, names, names - {"schema_version"}))

    def to_toml(self) -> str:
        # Preserve Unicode: JSON surrogate-pair escapes are not valid TOML.
        return "\n".join(f"{key} = {json.dumps(value, ensure_ascii=False)}" for key, value in self.to_dict().items()) + "\n"

    @classmethod
    def from_toml(cls, content: str):
        try:
            data = tomllib.loads(content)
        except (ValueError, TypeError) as exc:
            raise SerializationError("Invalid TOML document") from exc
        return cls.from_dict(data)
