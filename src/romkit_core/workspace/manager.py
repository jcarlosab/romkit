from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from romkit_core.errors import SerializationError, WorkspaceError
from romkit_core.models import InputImage
from romkit_core.models import common as v
from .layout import WorkspaceArea, WorkspaceLayout


@dataclass(frozen=True)
class SourceMetadata(v.JsonModel):
    path: Path
    sha256: str
    size_bytes: int
    platform: str | None

    def __post_init__(self):
        object.__setattr__(self, "path", v.path(self.path))
        v.sha256(self.sha256)
        v.integer(self.size_bytes, "size_bytes")
        v.platform(self.platform, optional=True)

    def to_dict(self):
        return {"path": str(self.path), "sha256": self.sha256, "size_bytes": self.size_bytes, "platform": self.platform}

    @classmethod
    def from_dict(cls, data):
        keys = {"path", "sha256", "size_bytes", "platform"}
        return cls(**v.fields(data, keys, keys))


class WorkspaceManager:
    """Own local technical files; never copy an image implicitly."""

    def __init__(self, project_root: str | Path):
        self.layout = WorkspaceLayout(Path(project_root))

    def open(self):
        self.layout.root.mkdir(parents=True, exist_ok=True)
        return self

    def source_metadata_path(self) -> Path:
        return self.layout.path(WorkspaceArea.METADATA, "source.json")

    def load_source_metadata(self) -> SourceMetadata:
        return SourceMetadata.from_json(self.source_metadata_path().read_text(encoding="utf-8"))

    @staticmethod
    def _same_file(left: Path, right: Path) -> bool:
        return left.resolve() == right.resolve() or (left.exists() and right.exists() and os.path.samefile(left, right))

    def _protect_source(self, destination: Path, source: Path | None = None) -> None:
        if source is None and self.source_metadata_path().exists():
            source = self.load_source_metadata().path
        if source is not None and self._same_file(source, destination):
            raise WorkspaceError("Cannot overwrite the original image")

    def register_source(self, image: InputImage) -> SourceMetadata:
        source = image.path.resolve(strict=True)
        if not source.is_file():
            raise WorkspaceError("Source image must be a file")
        # Keeping source files out of technical areas protects them from all
        # future workspace operations, including cleanup and regeneration.
        if source.is_relative_to(self.layout.root):
            raise WorkspaceError("Original image must be outside .romkit")
        metadata = SourceMetadata(source, image.sha256, image.size_bytes, image.selected_platform or image.detected_platform)
        destination = self.source_metadata_path()
        self._protect_source(destination, source)
        if destination.exists():
            if self.load_source_metadata() != metadata:
                raise WorkspaceError("Workspace already belongs to a different source image")
            return metadata
        self._write_metadata("source.json", metadata.to_dict(), source=source)
        return metadata

    def write_metadata(self, relative: str | Path, data: dict) -> Path:
        if self.layout.path(WorkspaceArea.METADATA, relative) == self.source_metadata_path():
            raise WorkspaceError("Source metadata is reserved; use register_source")
        return self._write_metadata(relative, data)

    def _write_metadata(self, relative: str | Path, data: dict, *, source: Path | None = None) -> Path:
        destination = self.layout.path(WorkspaceArea.METADATA, relative)
        self._protect_source(destination, source)
        try:
            content = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise SerializationError("Metadata must be JSON serializable") from exc
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content + "\n")
            os.replace(temporary, destination)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        return destination

    def read_metadata(self, relative: str | Path) -> dict:
        try:
            data = json.loads(self.layout.path(WorkspaceArea.METADATA, relative).read_text(encoding="utf-8"))
        except ValueError as exc:
            raise SerializationError("Invalid workspace metadata JSON") from exc
        if not isinstance(data, dict):
            raise SerializationError("Workspace metadata must be an object")
        return data

    def copy_source(self, relative: str | Path) -> Path:
        """Explicitly copy the registered source into the source area, never replace."""
        metadata = self.load_source_metadata()
        destination = self.layout.path(WorkspaceArea.SOURCE, relative)
        self._protect_source(destination, metadata.path)
        # Read and verify before creating an output, so a changed source is not
        # silently copied under an obsolete identity.
        with metadata.path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != metadata.sha256 or metadata.path.stat().st_size != metadata.size_bytes:
                raise WorkspaceError("Original image has changed since registration")
            stream.seek(0)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as output:
                shutil.copyfileobj(stream, output)
        return destination
