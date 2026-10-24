from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from romkit_core.errors import WorkspaceError


class WorkspaceArea(StrEnum):
    SOURCE = "source"
    EXTRACTED = "extracted"
    ANALYSIS = "analysis"
    METADATA = "metadata"
    BUILD = "build"
    CACHE = "cache"


@dataclass(frozen=True)
class WorkspaceLayout:
    project_root: Path

    def __post_init__(self):
        object.__setattr__(self, "project_root", Path(self.project_root).resolve())

    @property
    def root(self) -> Path:
        root = self.project_root / ".romkit"
        if root.resolve() != root:
            raise WorkspaceError(".romkit must not redirect to another directory")
        return root

    def ensure_inside(self, path: Path) -> Path:
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(self.root):
            raise WorkspaceError(f"Path is outside workspace: {path}")
        return resolved

    def area(self, area: WorkspaceArea | str, *, create: bool = False) -> Path:
        try:
            area = WorkspaceArea(area)
        except ValueError as exc:
            raise WorkspaceError(f"Unknown workspace area: {area}") from exc
        path = self.ensure_inside(self.root / area.value)
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def path(self, area: WorkspaceArea | str, relative: str | Path, *, create_parent: bool = False) -> Path:
        relative = Path(relative)
        if relative.is_absolute() or relative.drive or ".." in relative.parts or relative == Path("."):
            raise WorkspaceError("Expected a relative file path without traversal")
        area_path = self.area(area)
        path = self.ensure_inside(area_path / relative)
        if not path.is_relative_to(area_path):
            raise WorkspaceError("Path is outside requested workspace area")
        if create_parent:
            path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def ensure(self):
        for area in WorkspaceArea:
            self.area(area, create=True)
        return self
