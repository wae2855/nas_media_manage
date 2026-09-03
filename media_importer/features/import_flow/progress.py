import threading
import time
from dataclasses import dataclass


@dataclass
class _ProgressSnapshot:
    step_name: str
    completed_bytes: int
    phase_percent: float
    saved_at: float


class TaskProgressReporter:
    """Persist truthful file progress without committing SQLite per chunk."""

    def __init__(
        self,
        task_manager,
        *,
        min_interval: float = 1.0,
        min_percent_delta: float = 1.0,
        min_bytes_delta: int = 64 * 1024 * 1024,
    ):
        self.task_manager = task_manager
        self.min_interval = min_interval
        self.min_percent_delta = min_percent_delta
        self.min_bytes_delta = min_bytes_delta
        self._snapshots: dict[str, _ProgressSnapshot] = {}
        self._lock = threading.Lock()

    def update(
        self,
        task: dict,
        step_num: int,
        step_name: str,
        percentage: int,
        *,
        completed_bytes: int = 0,
        total_bytes: int = 0,
        force: bool = False,
        **kwargs,
    ) -> bool:
        task_id = task.get("task_id", "")
        now = time.monotonic()
        completed = max(0, int(completed_bytes or 0))
        total = max(0, int(total_bytes or 0))
        phase_percent = (completed / total * 100.0) if total else 0.0

        with self._lock:
            previous = self._snapshots.get(task_id)
            should_save = force or previous is None or previous.step_name != step_name
            if previous is not None and previous.step_name == step_name:
                should_save = should_save or now - previous.saved_at >= self.min_interval
                should_save = should_save or completed - previous.completed_bytes >= self.min_bytes_delta
                should_save = should_save or phase_percent - previous.phase_percent >= self.min_percent_delta
            if total and completed >= total:
                should_save = True
            if not should_save:
                return False

            monotonic_percentage = max(
                int(task.get("percentage") or 0),
                min(100, max(0, int(percentage))),
            )
            progress_fields = dict(kwargs)
            progress_fields.update(bytes_copied=completed, total_bytes=total)
            self.task_manager.update_progress(
                task,
                step_num,
                step_name,
                monotonic_percentage,
                **progress_fields,
            )
            self._snapshots[task_id] = _ProgressSnapshot(
                step_name=step_name,
                completed_bytes=completed,
                phase_percent=phase_percent,
                saved_at=now,
            )
            return True

    def clear(self, task_id: str) -> None:
        with self._lock:
            self._snapshots.pop(task_id, None)
