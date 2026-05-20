#!/usr/bin/env python3
import json
import uuid
import time
import threading
import os
from datetime import datetime
from dataclasses import dataclass, field, asdict


VALID_STATUSES = ["PENDING", "PROCESSING", "SUCCESS", "FAILED", "SKIPPED"]

STATUS_TRANSITIONS = {
    "PENDING": ["PROCESSING", "SKIPPED"],
    "PROCESSING": ["SUCCESS", "FAILED", "SKIPPED"],
    "SUCCESS": [],
    "FAILED": ["PENDING"],
    "SKIPPED": ["PENDING"]
}


@dataclass
class Task:
    task_id: str = ""
    video_file: str = ""
    video_path: str = ""
    file_size_mb: float = 0
    subtitle_files: list = field(default_factory=list)
    scraped_info: dict = field(default_factory=dict)
    import_path: str = ""
    final_filename: str = ""
    status: str = "PENDING"
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    error_code: int = 0
    error_message: str = ""
    retry_count: int = 0
    logs: list = field(default_factory=list)
    current_step: int = 0
    total_steps: int = 10
    step_name: str = ""
    percentage: int = 0
    bytes_copied: int = 0
    total_bytes: int = 0

    def __post_init__(self):
        if not self.task_id:
            self.task_id = uuid.uuid4().hex[:12]
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def can_transition_to(self, new_status: str) -> bool:
        return new_status in STATUS_TRANSITIONS.get(self.status, [])

    def transition_to(self, new_status: str):
        if not self.can_transition_to(new_status):
            raise ValueError(
                f"Invalid transition: {self.status} -> {new_status}"
            )
        self.status = new_status
        if new_status == "PROCESSING":
            self.started_at = datetime.now().isoformat()
        elif new_status in ["SUCCESS", "FAILED", "SKIPPED"]:
            self.completed_at = datetime.now().isoformat()

    def add_log(self, step: str, level: str, message: str):
        self.logs.append({
            "timestamp": datetime.now().isoformat(),
            "step": step,
            "level": level,
            "message": message
        })

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        return cls(**data)


class TaskManager:
    def __init__(self, persistence_path: str, config: dict = None):
        self.path = persistence_path
        self.config = config or {}
        self._lock = threading.RLock()
        self._tasks = {}
        self._load_tasks()

    def create_task(self, video_path: str, video_file: str,
                    subtitle_files: list = None,
                    file_size_mb: float = 0) -> Task:
        task = Task(
            video_file=video_file,
            video_path=video_path,
            subtitle_files=subtitle_files or [],
            file_size_mb=file_size_mb
        )
        with self._lock:
            self._tasks[task.task_id] = task
            self._save_tasks()
        return task

    def get_task(self, task_id: str) -> Task:
        with self._lock:
            return self._tasks.get(task_id)

    def get_next_pending(self) -> Task:
        with self._lock:
            for task in self._tasks.values():
                if task.status == "PENDING":
                    return task
        return None

    def update_task(self, task: Task):
        with self._lock:
            self._tasks[task.task_id] = task
            self._save_tasks()
        if self.config.get('auto_delete_success') and task.status == "SUCCESS":
            self._cleanup_success_task(task.task_id)

    def _cleanup_success_task(self, task_id: str):
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                self._save_tasks()

    def update_progress(self, task: Task, step_num: int, step_name: str,
                        percentage: int, **kwargs):
        task.current_step = step_num
        task.step_name = step_name
        task.percentage = min(100, max(0, percentage))
        for k, v in kwargs.items():
            if hasattr(task, k):
                setattr(task, k, v)
        self.update_task(task)

    def list_tasks(self, status: str = None, limit: int = 20,
                   offset: int = 0, exclude_completed: bool = None) -> list:
        with self._lock:
            tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        elif exclude_completed is None or exclude_completed:
            tasks = [t for t in tasks if t.status in ["PENDING", "PROCESSING", "FAILED"]]
        tasks = sorted(tasks, key=lambda t: t.created_at)
        return tasks[offset:offset + limit]

    def list_all_tasks(self, limit: int = 50, offset: int = 0) -> list:
        with self._lock:
            tasks = list(self._tasks.values())
        tasks = sorted(tasks, key=lambda t: t.created_at, reverse=True)
        return tasks[offset:offset + limit]

    def retry_task(self, task_id: str) -> Task:
        task = self.get_task(task_id)
        if task and task.status == "FAILED":
            task.transition_to("PENDING")
            task.retry_count += 1
            task.error_code = 0
            task.error_message = ""
            task.current_step = 0
            task.step_name = ""
            task.percentage = 0
            self.update_task(task)
        return task

    def retry_all_failed(self) -> list:
        retried = []
        with self._lock:
            for task in self._tasks.values():
                if task.status == "FAILED":
                    task.transition_to("PENDING")
                    task.retry_count += 1
                    task.error_code = 0
                    task.error_message = ""
                    task.current_step = 0
                    task.step_name = ""
                    task.percentage = 0
                    retried.append(task)
            self._save_tasks()
        return retried

    def clear_tasks(self, status: str = None):
        with self._lock:
            if status:
                self._tasks = {
                    tid: t for tid, t in self._tasks.items()
                    if t.status != status
                }
            else:
                self._tasks = {}
            self._save_tasks()

    def count_by_status(self) -> dict:
        counts = {s: 0 for s in VALID_STATUSES}
        with self._lock:
            for task in self._tasks.values():
                if task.status in counts:
                    counts[task.status] += 1
        return counts

    def _save_tasks(self):
        dir_path = os.path.dirname(self.path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        data = {tid: t.to_dict() for tid, t in self._tasks.items()}
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_tasks(self):
        if not os.path.exists(self.path):
            self._tasks = {}
            return
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._tasks = {tid: Task.from_dict(td) for tid, td in data.items()}
        except (json.JSONDecodeError, KeyError):
            self._tasks = {}
