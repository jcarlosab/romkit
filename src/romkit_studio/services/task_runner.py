from collections.abc import Callable
from threading import Event
import traceback
from uuid import uuid4

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot

from romkit_core.tasks import TaskCancelled
from romkit_studio.models.task_state import TaskError


class _Signals(QObject):
    started = Signal(str)
    progress = Signal(str, object)
    result = Signal(str, object)
    error = Signal(str, object)
    finished = Signal(str)


class _Job(QRunnable):
    def __init__(self, task_id, function, args, kwargs, with_progress):
        super().__init__()
        self.setAutoDelete(False)
        self.task_id = task_id
        self.function, self.args, self.kwargs = function, args, kwargs
        self.with_progress = with_progress
        self.signals = _Signals()
        self.cancelled = Event()

    def _progress(self, value):
        if self.cancelled.is_set():
            raise TaskCancelled()
        self.signals.progress.emit(self.task_id, value)

    def run(self):
        self.signals.started.emit(self.task_id)
        try:
            if self.cancelled.is_set():
                raise TaskCancelled()
            kwargs = dict(self.kwargs)
            if self.with_progress:
                kwargs["progress"] = self._progress
            result = self.function(*self.args, **kwargs)
            if not self.cancelled.is_set():
                self.signals.result.emit(self.task_id, result)
        except TaskCancelled:
            pass
        except Exception as exc:
            self.signals.error.emit(self.task_id, TaskError(str(exc) or type(exc).__name__, traceback.format_exc()))
        finally:
            self.signals.finished.emit(self.task_id)


class TaskRunner(QObject):
    started = Signal(str)
    progress = Signal(str, object)
    result = Signal(str, object)
    error = Signal(str, object)
    finished = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self._jobs: dict[str, _Job] = {}
        self._retired = []

    @property
    def busy(self) -> bool:
        return bool(self._jobs)

    def submit(self, function: Callable, *args, with_progress: bool = False, **kwargs) -> str:
        task_id = uuid4().hex
        job = _Job(task_id, function, args, kwargs, with_progress)
        for name in ("started", "progress", "result", "error"):
            getattr(job.signals, name).connect(getattr(self, name))
        job.signals.finished.connect(self._finished)
        self._jobs[task_id] = job
        self.pool.start(job)
        return task_id

    def cancel_all(self) -> None:
        for job in self._jobs.values():
            job.cancelled.set()

    @Slot(str)
    def _finished(self, task_id: str) -> None:
        job = self._jobs.pop(task_id, None)
        if job is not None:
            self._retired.append(job)
        QTimer.singleShot(0, self._release_finished)
        self.finished.emit(task_id)

    @Slot()
    def _release_finished(self):
        # finished can reach the UI before QRunnable.run has returned. Retain the
        # Python wrapper and signal object until Qt confirms workers are idle.
        if self.pool.waitForDone(0):
            self._retired.clear()
        elif self._retired:
            QTimer.singleShot(10, self._release_finished)
