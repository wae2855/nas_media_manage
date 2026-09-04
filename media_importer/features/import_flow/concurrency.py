import threading
from contextlib import contextmanager
from typing import Callable, Iterator

DEFAULT_TASK_CONCURRENCY = 1
MAX_TASK_CONCURRENCY = 2


def effective_max_concurrent(config: dict | None) -> int:
    """Return the safe runtime limit, including compatibility for old configs."""
    task_queue = (config or {}).get("task_queue", {})
    raw_value = (
        task_queue.get("max_concurrent", DEFAULT_TASK_CONCURRENCY)
        if isinstance(task_queue, dict)
        else DEFAULT_TASK_CONCURRENCY
    )
    if isinstance(raw_value, bool):
        return DEFAULT_TASK_CONCURRENCY
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return DEFAULT_TASK_CONCURRENCY
    return min(MAX_TASK_CONCURRENCY, max(DEFAULT_TASK_CONCURRENCY, value))


class TaskConcurrencyGate:
    """Process-wide gate shared by every task-processing entry point."""

    def __init__(self, config_getter: Callable[[], dict | None]):
        self._config_getter = config_getter
        self._condition = threading.Condition()
        self._active_count = 0

    @property
    def active_count(self) -> int:
        with self._condition:
            return self._active_count

    @contextmanager
    def slot(self) -> Iterator[None]:
        with self._condition:
            while self._active_count >= effective_max_concurrent(
                self._config_getter()
            ):
                self._condition.wait(timeout=0.25)
            self._active_count += 1
        try:
            yield
        finally:
            with self._condition:
                self._active_count -= 1
                self._condition.notify_all()
