from dataclasses import dataclass


@dataclass(frozen=True)
class TaskError:
    message: str
    traceback: str


@dataclass(frozen=True)
class TaskState:
    task_id: str
    label: str
    running: bool = False
    completed: int = 0
    total: int = 0
