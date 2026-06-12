#!/usr/bin/env python3
import time
import threading
from datetime import timedelta


class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self.start_time = time.time()
        self._counters = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0
        }
        self._processing_times = []
        self._llm_calls = 0
        self._llm_failures = 0
        self._queue_status = {
            "queued": 0,
            "running": 0,
            "paused": False
        }

    def record_task_start(self):
        with self._lock:
            self._counters["total"] += 1
            self._queue_status["running"] += 1
            if self._queue_status["queued"] > 0:
                self._queue_status["queued"] -= 1

    def record_task_complete(self, status: str, duration: float = None):
        with self._lock:
            self._queue_status["running"] -= 1

            if status == "success":
                self._counters["success"] += 1
            elif status == "failed":
                self._counters["failed"] += 1
            elif status == "skipped":
                self._counters["skipped"] += 1

            if duration is not None:
                self._processing_times.append(duration)
                if len(self._processing_times) > 1000:
                    self._processing_times = self._processing_times[-1000:]

    def record_llm_call(self, success: bool):
        with self._lock:
            self._llm_calls += 1
            if not success:
                self._llm_failures += 1

    def set_queue_pending(self, count: int):
        with self._lock:
            self._queue_status["queued"] = count

    def set_queue_paused(self, paused: bool):
        with self._lock:
            self._queue_status["paused"] = paused

    @property
    def success_rate(self) -> float:
        total = self._counters["success"] + self._counters["failed"]
        if total == 0:
            return 0.0
        return self._counters["success"] / total

    @property
    def avg_processing_time(self) -> float:
        if not self._processing_times:
            return 0.0
        return sum(self._processing_times) / len(self._processing_times)

    @property
    def uptime(self) -> str:
        uptime_seconds = time.time() - self.start_time
        td = timedelta(seconds=int(uptime_seconds))
        days = td.days
        hours, remainder = divmod(td.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0 or days > 0:
            parts.append(f"{hours}h")
        if minutes > 0 or hours > 0 or days > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")

        return " ".join(parts)

    def to_dict(self) -> dict:
        return {
            "total_tasks": self._counters["total"],
            "success_tasks": self._counters["success"],
            "failed_tasks": self._counters["failed"],
            "skipped_tasks": self._counters["skipped"],
            "success_rate": self.success_rate,
            "avg_processing_time_seconds": self.avg_processing_time,
            "total_llm_calls": self._llm_calls,
            "llm_failures": self._llm_failures,
            "current_queue_queued": self._queue_status["queued"],
            "current_queue_running": self._queue_status["running"],
            "queue_paused": self._queue_status["paused"],
            "uptime": self.uptime
        }


_default_metrics = None


def get_metrics() -> Metrics:
    global _default_metrics
    if _default_metrics is None:
        _default_metrics = Metrics()
    return _default_metrics
