from dataclasses import dataclass


from romkit_core.tasks import TaskError


@dataclass(frozen=True)
class TaskState:
    task_id: str
    label: str
    running: bool = False
    completed: int = 0
    total: int = 0
