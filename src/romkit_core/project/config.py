from pathlib import Path

from romkit_core.errors import SerializationError, ValidationError
from romkit_core.models import ProjectConfig
from .io import atomic_write


def read_config(path: str | Path) -> ProjectConfig:
    path = Path(path)
    try:
        return ProjectConfig.from_toml(path.read_text(encoding="utf-8"))
    except (SerializationError, ValidationError, UnicodeError) as exc:
        raise SerializationError(f"{path.name}: {exc}") from exc


def write_config(path: str | Path, config: ProjectConfig) -> None:
    atomic_write(Path(path), config.to_toml())
