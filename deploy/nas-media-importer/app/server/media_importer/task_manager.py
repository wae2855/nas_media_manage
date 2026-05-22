#!/usr/bin/env python3
import os
import shutil
import threading
from datetime import datetime

from db import (
    init_db, create_task as db_create_task,
    get_task as db_get_task,
    update_task as db_update_task,
    list_tasks as db_list_tasks,
    list_all_tasks as db_list_all_tasks,
    count_by_status as db_count_by_status,
    has_active_tasks as db_has_active_tasks,
    get_next_pending as db_get_next_pending,
    count_all_tasks as db_count_all_tasks,
    find_by_source_path as db_find_by_source_path,
    find_failed_too_many as db_find_failed,
    create_subtitles as db_create_subtitles,
    get_subtitles_by_task as db_get_subtitles,
    update_subtitles_by_task as db_update_subs,
    count_subtitles_by_task as db_count_subs,
    VALID_STATUSES,
)


VALID_STATUSES = list(VALID_STATUSES)


class TaskManager:
    def __init__(self, persistence_path: str, config: dict = None):
        self.config = config or {}
        db_dir = os.path.dirname(persistence_path)
        db_path = os.path.join(db_dir, "tasks.db")
        self.conn = init_db(db_path)
        self._lock = threading.RLock()

    def create_task(self, video_path: str, video_file: str,
                    subtitle_files: list = None,
                    file_size_mb: float = 0) -> dict:
        task = db_create_task(
            self.conn,
            source_path=video_path,
            source_filename=video_file,
            file_size_mb=file_size_mb,
        )
        subs = subtitle_files or []
        if subs:
            db_create_subtitles(self.conn, task["task_id"], subs)
        count_subs = len(subs)
        task["subtitle_files"] = subs
        task["subtitle_total"] = count_subs
        task["subtitle_success"] = 0
        return task

    def get_task(self, task_id: str) -> dict:
        return db_get_task(self.conn, task_id)

    def get_next_pending(self) -> dict:
        return db_get_next_pending(self.conn)

    def update_task(self, task: dict):
        if task is None:
            return
        if isinstance(task, dict):
            task_id = task.get("task_id", "")
            update_fields = {k: v for k, v in task.items()
                            if k not in ("subtitle_files", "subtitle_total",
                                        "subtitle_success", "logs")}
            db_update_task(self.conn, task_id, **update_fields)
        else:
            task_id = getattr(task, "task_id", "")
            db_update_task(self.conn, task_id, status=getattr(task, "status", ""))

    def update_progress(self, task: dict, step_num: int, step_name: str,
                        percentage: int, **kwargs):
        if isinstance(task, dict):
            task["current_step"] = step_num
            task["step_name"] = step_name
            task["percentage"] = min(100, max(0, percentage))
            for k, v in kwargs.items():
                if k in ("bytes_copied", "total_bytes", "import_path",
                         "final_filename", "video_path", "subtitle_files"):
                    task[k] = v
            db_update_task(
                self.conn, task["task_id"],
                current_step=step_num, step_name=step_name,
                percentage=min(100, max(0, percentage)),
                **kwargs
            )

    def list_tasks(self, status: str = None, limit: int = 20,
                   offset: int = 0, exclude_completed: bool = None) -> list:
        page = (offset // limit) + 1 if limit > 0 else 1
        page_size = limit
        if exclude_completed is True and not status:
            rows, _, _ = db_list_tasks(
                self.conn, page=1, page_size=10000, status=None
            )
            result = []
            for r in rows:
                if r["status"] in ("PENDING", "PROCESSING", "FAILED",
                                   "CONFIRMING", "NEEDS_REVIEW"):
                    result.append(r)
            return result[offset:offset + limit]
        rows, _, _ = db_list_tasks(
            self.conn, page=page, page_size=page_size, status=status
        )
        return rows

    def list_all_tasks(self, limit: int = 50, offset: int = 0) -> list:
        rows = db_list_all_tasks(self.conn, limit=limit + offset)
        return rows[offset:offset + limit]

    def retry_task(self, task_id: str) -> dict:
        task = db_get_task(self.conn, task_id)
        if task and task.get("status") in ("FAILED", "NEEDS_REVIEW"):
            db_update_task(
                self.conn, task_id,
                status="PENDING",
                retry_count=task.get("retry_count", 0) + 1,
                error_code=0,
                error_message="",
                current_step=0,
                step_name="",
                percentage=0,
            )
        return db_get_task(self.conn, task_id)

    def retry_all_failed(self) -> list:
        rows = db_list_all_tasks(self.conn, limit=10000)
        retried = []
        for task in rows:
            if task["status"] in ("FAILED", "NEEDS_REVIEW"):
                db_update_task(
                    self.conn, task["task_id"],
                    status="PENDING",
                    retry_count=task.get("retry_count", 0) + 1,
                    error_code=0,
                    error_message="",
                    current_step=0,
                    step_name="",
                    percentage=0,
                )
                retried.append(task)
        return retried

    def clear_tasks(self, status: str = None):
        if status:
            db_update_task(self.conn, "_clear_all_")
        else:
            rows = db_list_all_tasks(self.conn, limit=100000)
            for r in rows:
                db_update_task(self.conn, r["task_id"], status="SKIPPED")

    def count_by_status(self) -> dict:
        return db_count_by_status(self.conn)

    def has_active_tasks(self) -> bool:
        return db_has_active_tasks(self.conn)

    def check_source_duplicate(self, source_path: str) -> dict:
        history = db_find_by_source_path(self.conn, source_path)
        if history is None:
            return {
                "exists": False,
                "task_id": None,
                "action": "CREATE",
                "reason": "新文件，无历史记录",
            }
        old_status = history.get("status", "")
        old_retry = history.get("retry_count", 0)
        if old_status in ("SUCCESS",):
            return {
                "exists": True,
                "task_id": history["task_id"],
                "old_status": old_status,
                "old_retry": old_retry,
                "action": "QUARANTINE",
                "reason": f"历史已处理 ({old_status})",
            }
        if old_status in ("FAILED", "SKIPPED"):
            max_retries = self.config.get("source_dedup", {}).get(
                "max_auto_retries", 3
            )
            if old_retry >= max_retries:
                return {
                    "exists": True,
                    "task_id": history["task_id"],
                    "old_status": old_status,
                    "old_retry": old_retry,
                    "action": "QUARANTINE",
                    "reason": f"历史失败/跳过已达最大重试次数 ({old_retry}次)",
                }
            return {
                "exists": True,
                "task_id": history["task_id"],
                "old_status": old_status,
                "old_retry": old_retry,
                "action": "RETRY",
                "reason": f"历史失败/跳过，重试次数 {old_retry} < {max_retries}，可重新处理",
            }
        if old_status in ("PROCESSING", "CONFIRMING"):
            return {
                "exists": True,
                "task_id": history["task_id"],
                "old_status": old_status,
                "old_retry": old_retry,
                "action": "SKIP",
                "reason": f"任务正在处理/待确认，跳过 ({old_status})",
            }
        if old_status in ("NEEDS_REVIEW", "ROLLBACK"):
            return {
                "exists": True,
                "task_id": history["task_id"],
                "old_status": old_status,
                "old_retry": old_retry,
                "action": "SKIP",
                "reason": f"任务在隔离区/已回退，跳过 ({old_status})",
            }
        return {
            "exists": True,
            "task_id": history["task_id"],
            "old_status": old_status,
            "old_retry": old_retry,
            "action": "CREATE",
            "reason": f"未知状态 ({old_status})，创建新任务",
        }

    def move_to_quarantine(self, task_id: str, source_path: str,
                            subtitle_paths: list, quarantine_dir: str):
        os.makedirs(quarantine_dir, exist_ok=True)
        task = db_get_task(self.conn, task_id)
        if not task:
            return
        video_filename = os.path.basename(source_path)
        dest_video = os.path.join(quarantine_dir, video_filename)
        if os.path.exists(source_path):
            shutil.move(source_path, dest_video)
        for sub_path in subtitle_paths:
            if os.path.exists(sub_path):
                sub_name = os.path.basename(sub_path)
                dest_sub = os.path.join(quarantine_dir, sub_name)
                shutil.move(sub_path, dest_sub)
        db_update_task(
            self.conn, task_id,
            status="NEEDS_REVIEW",
            source_path=dest_video,
            error_message=f"已移入隔离区: {quarantine_dir}",
        )
        db_update_subs(self.conn, task_id, status="NEEDS_REVIEW")
        self._cleanup_empty_dirs(source_path)

    def _cleanup_empty_dirs(self, file_path: str):
        parent = os.path.dirname(file_path)
        try:
            if os.path.isdir(parent) and not os.listdir(parent):
                os.rmdir(parent)
        except OSError:
            pass