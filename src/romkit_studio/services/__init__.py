from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from romkit_core.platforms import PlatformRegistry
from romkit_core.transforms import TransformRegistry
from romkit_core.workspace import WorkspaceManager


@dataclass
class StudioServices:
    platforms: PlatformRegistry = field(default_factory=PlatformRegistry)
    transforms: TransformRegistry = field(default_factory=TransformRegistry)
    workspace_factory: Callable[[Path], WorkspaceManager] = WorkspaceManager
