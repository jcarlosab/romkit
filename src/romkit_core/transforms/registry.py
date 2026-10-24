from romkit_core.errors import TransformError
from romkit_core.models import common as v
from .base import IdentityTransform, TransformHandler


class TransformRegistry:
    def __init__(self):
        self._handlers: dict[str, TransformHandler] = {}
        self.register(IdentityTransform())

    def register(self, handler: TransformHandler) -> None:
        if not isinstance(handler, TransformHandler):
            raise TransformError("Handler does not implement TransformHandler")
        v.platform(handler.id)
        if handler.id in self._handlers:
            raise TransformError(f"Transform already registered: {handler.id}")
        self._handlers[handler.id] = handler

    def resolve(self, handler_id: str) -> TransformHandler:
        try:
            return self._handlers[handler_id]
        except KeyError as exc:
            raise TransformError(f"Unknown transform: {handler_id}") from exc

    def available(self) -> tuple[TransformHandler, ...]:
        return tuple(self._handlers.values())
