from dataclasses import dataclass
from pathlib import Path

from romkit_core.errors import PlatformError
from romkit_core.models import common as v
from .base import PlatformBackend, ProbeResult


@dataclass(frozen=True)
class PlatformCandidate:
    backend_id: str
    display_name: str
    probe: ProbeResult


class PlatformRegistry:
    def __init__(self):
        self._backends: dict[str, PlatformBackend] = {}

    def register(self, backend: PlatformBackend) -> None:
        if not isinstance(backend, PlatformBackend):
            raise PlatformError("Backend does not implement PlatformBackend")
        v.platform(backend.id)
        v.text(backend.display_name, "display_name")
        if backend.id in self._backends:
            raise PlatformError(f"Platform already registered: {backend.id}")
        self._backends[backend.id] = backend

    def resolve(self, backend_id: str) -> PlatformBackend:
        """Manual selection is always allowed, independent of detection evidence."""
        try:
            return self._backends[backend_id]
        except KeyError as exc:
            raise PlatformError(f"Unknown platform: {backend_id}") from exc

    def available(self) -> tuple[PlatformBackend, ...]:
        return tuple(self._backends.values())

    def detect(self, path: str | Path) -> list[PlatformCandidate]:
        path = Path(path)
        candidates = []
        for backend_id, backend in self._backends.items():
            try:
                result = backend.probe(path)
            except Exception as exc:
                raise PlatformError(f"Platform probe failed: {backend_id}") from exc
            if not isinstance(result, ProbeResult):
                raise PlatformError(f"Invalid probe result: {backend_id}")
            if result.compatible and result.confidence > 0 and result.evidence:
                candidates.append(PlatformCandidate(backend_id, backend.display_name, result))
        return sorted(candidates, key=lambda candidate: (-candidate.probe.confidence, candidate.backend_id))
