from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from romkit_core.errors import ValidationError
from romkit_core.models import InputImage, ResourceEntry
from romkit_core.models.text_candidate import TextCandidate


@dataclass(frozen=True)
class SessionState:
    image: InputImage | None = None
    workspace: Path | None = None
    resources: tuple[ResourceEntry, ...] = ()
    candidates: tuple[TextCandidate, ...] = ()
    busy: bool = False

    @property
    def has_image(self) -> bool:
        return self.image is not None


class SessionModel(QObject):
    changed = Signal(object)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._state = SessionState()

    @property
    def state(self) -> SessionState:
        return self._state

    def set_image(self, image: InputImage | None) -> None:
        if image is not None and not isinstance(image, InputImage):
            raise ValidationError("Session image must be InputImage or None")
        state = SessionState(image, busy=self._state.busy)
        if state != self._state:
            self._state = state
            self.changed.emit(state)

    def _replace(self, **changes):
        state = replace(self._state, **changes)
        if state != self._state:
            self._state = state
            self.changed.emit(state)

    def open_image(self, image, workspace, resources=()):
        self._state = SessionState(image, Path(workspace), tuple(resources), busy=self._state.busy)
        self.changed.emit(self._state)

    def set_resources(self, resources):
        self._replace(resources=tuple(resources), candidates=())

    def set_analysis(self, resources, candidates):
        # A completed new analysis also restores candidates hidden from the UI.
        self._state = replace(self._state, resources=tuple(resources), candidates=tuple(candidate for candidate in candidates))
        self.changed.emit(self._state)

    def set_busy(self, busy):
        self._replace(busy=bool(busy))

    def clear(self) -> None:
        self.set_image(None)
