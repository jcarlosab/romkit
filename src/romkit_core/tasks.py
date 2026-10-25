"""Plain Python progress contracts, usable without Qt."""
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class OperationProgress:
    completed: int
    total: int
    message: str = ""


ProgressCallback = Callable[[OperationProgress], None]


def report(progress: ProgressCallback | None, completed: int, total: int, message: str = "") -> None:
    if progress is not None:
        progress(OperationProgress(completed, total, message))


class TaskCancelled(Exception):
    pass


@dataclass(frozen=True)
class TaskError:
    message: str
    traceback: str
