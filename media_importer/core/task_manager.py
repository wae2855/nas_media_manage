#!/usr/bin/env python3
import os
import shutil
import threading
from datetime import datetime

from .task_lifecycle import reset_for_retry
from .db import (
    init_db, create_task as db_create_task,
    get_task as db_get_task,
    update_task as db_update_task,
    delete_task as db_delete_task,
    clear_tasks as db_clear_tasks,
    list_tasks as db_list_tasks,
    list_all_tasks as db_list_all_tasks,
    count_by_status as db_count_by_status,
    has_running_tasks as db_has_running_tasks,
    get_next_pending as db_get_next_pending,
    count_all_tasks as db_count_all_tasks,
    find_by_source_path as db_find_by_source_path,
    find_by_fingerprint as db_find_by_fingerprint,
    find_failed_too_many as db_find_failed,
    create_subtitles as db_create_subtitles,
    get_subtitles_by_task as db_get_subtitles,
    update_subtitles_by_task as db_update_subs,
    update_subtitle as db_update_subtitle,
    count_subtitles_by_task as db_count_subs,
    VALID_STATUSES,
)


VALID_STATUSES = list(VALID_STATUSES)


class TaskManager:
    def __init__(self, data_dir: str, config: dict = None):
        self.config = config or {}
        db_path = os.path.join(data_dir, "tasks.db")
        self.conn = init_db(db_path)
        self._lock = threading.RLock()

    def create_task(self, video_path: str, video_file: str,
                    subtitle_files: list = None,
                    file_size_mb: float = 0,
                    initial_status: str = None) -> dict:
        task = db_create_task(
            self.conn,
            source_path=video_path,
            source_filename=video_file,
            file_size_mb=file_size_mb,
        )
        if initial_status and initial_status in VALID_STATUSES:
            db_update_task(self.conn, task["task_id"], status=initial_status)
            task["status"] = initial_status
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
            skip_keys = ("task_id", "subtitle_files", "subtitle_total",
                         "subtitle_success", "logs")
            update_fields = {k: v for k, v in task.items()
                            if k not in skip_keys}
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
                   offset: int = 0, exclude_completed: bool = None,
                   stage: str = None) -> list:
        page = (offset // limit) + 1 if limit > 0 else 1
        page_size = limit
        if exclude_completed is True and not status:
            rows, _, _ = db_list_tasks(
                self.conn, page=1, page_size=10000, status=None
            )
            result = []
            for r in rows:
                if r["status"] in ("PENDING", "FAILED"):
                    result.append(r)
            return result[offset:offset + limit]
        rows, _, _ = db_list_tasks(
            self.conn, page=page, page_size=page_size, status=status, stage=stage
        )
        return rows

    def list_all_tasks(self, limit: int = 50, offset: int = 0) -> list:
        rows = db_list_all_tasks(self.conn, limit=limit + offset)
        return rows[offset:offset + limit]

    def retry_task(self, task_id: str) -> dict:
        task = db_get_task(self.conn, task_id)
        if not task or task.get("status") not in ("FAILED", "SKIPPED"):
            return None
        db_update_task(self.conn, task_id, **reset_for_retry(task))
        return db_get_task(self.conn, task_id)

    def retry_all_failed(self) -> list:
        rows = db_list_all_tasks(self.conn, limit=10000)
        retried = []
        for task in rows:
            if task["status"] in ("FAILED", "SKIPPED"):
                db_update_task(self.conn, task["task_id"], **reset_for_retry(task))
                retried.append(task)
        return retried

    def clear_tasks(self, status: str = None):
        db_clear_tasks(self.conn, status=status)

    def count_by_status(self) -> dict:
        return db_count_by_status(self.conn)

    def has_running_tasks(self) -> bool:
        return db_has_running_tasks(self.conn)

    def check_source_duplicate(self, source_path: str,
                                source_fingerprint: str = "") -> dict:
        history = db_find_by_source_path(self.conn, source_path)
        if history is None:
            if source_fingerprint:
                fp_hit = db_find_by_fingerprint(self.conn, source_fingerprint)
                if fp_hit:
                    old_status = fp_hit.get("status", "")
                    old_stage = fp_hit.get("stage", "")
                    if old_status == "PENDING" and old_stage in ("RUNNING", "AWAIT_REVIEW"):
                        return {
                            "exists": True,
                            "task_id": fp_hit["task_id"],
                            "old_status": old_status,
                            "action": "SKIP",
                            "reason": f"指纹匹配到正在处理的任务 ({old_status}/{old_stage})",
                        }
                    if old_status == "SUCCESS":
                        return {
                            "exists": True,
                            "task_id": fp_hit["task_id"],
                            "old_status": old_status,
                            "action": "RENAME_DETECTED",
                            "old_path": fp_hit.get("source_path", ""),
                            "reason": f"文件改名检测: 原名 {fp_hit.get('source_filename', '')}",
                        }
            return {
                "exists": False,
                "task_id": None,
                "action": "CREATE",
                "reason": "新文件，无历史记录",
            }
        old_status = history.get("status", "")
        old_stage = history.get("stage", "")
        if old_status == "PENDING" and old_stage in ("RUNNING", "AWAIT_REVIEW"):
            return {
                "exists": True,
                "task_id": history["task_id"],
                "old_status": old_status,
                "action": "SKIP",
                "reason": f"任务正在处理/待确认，跳过 ({old_status}/{old_stage})",
            }
        if old_status == "SUCCESS" and self._is_file_changed(source_path, history):
            current_size = os.path.getsize(source_path) if os.path.isfile(source_path) else 0
            old_size = history.get("source_file_size") or int((history.get("file_size_mb") or 0) * 1024 * 1024)
            if old_size and abs(current_size - old_size) > 1024:
                return {
                    "exists": True,
                    "task_id": history["task_id"],
                    "old_status": old_status,
                    "action": "REPROCESS",
                    "reason": "文件大小变化，可能是新版本",
                }
            return {
                "exists": True,
                "task_id": history["task_id"],
                "old_status": old_status,
                "action": "UPDATE_MTIME",
                "reason": "仅修改时间变化，文件大小未变",
            }
        return {
            "exists": True,
            "task_id": history["task_id"],
            "old_status": old_status,
            "action": "CREATE",
            "reason": "历史任务已结束，创建新任务",
        }

    def _is_file_changed(self, source_path: str, history: dict) -> bool:
        if not os.path.isfile(source_path):
            return False
        try:
            current_size = os.path.getsize(source_path)
            current_mtime = os.path.getmtime(source_path)
        except OSError:
            return False
        old_size = history.get("file_size_bytes") or history.get("file_size_mb")
        if old_size is not None:
            if history.get("file_size_bytes"):
                if current_size != old_size:
                    return True
            elif history.get("file_size_mb"):
                current_mb = current_size / (1024 * 1024)
                if abs(current_mb - old_size) > 0.1:
                    return True
        old_mtime_str = history.get("source_mtime", "")
        if old_mtime_str:
            try:
                from datetime import datetime
                old_dt = datetime.fromisoformat(old_mtime_str)
                old_mtime = old_dt.timestamp()
                if abs(current_mtime - old_mtime) > 1:
                    return True
            except (ValueError, TypeError):
                pass
        return False

    @staticmethod
    def _resolve_dest_path(dest_dir: str, filename: str) -> str:
        dest = os.path.join(dest_dir, filename)
        if not os.path.exists(dest):
            return dest
        name, ext = os.path.splitext(filename)
        counter = 1
        while True:
            new_name = f"{name}_{counter}{ext}"
            dest = os.path.join(dest_dir, new_name)
            if not os.path.exists(dest):
                return dest
            counter += 1

    def move_to_recycle_bin(self, task_id: str, source_path: str,
                            subtitle_paths: list, recycle_dir: str):
        os.makedirs(recycle_dir, exist_ok=True)
        task = db_get_task(self.conn, task_id)
        if not task:
            return
        video_filename = os.path.basename(source_path)
        source_abs = os.path.abspath(source_path)
        recycle_abs = os.path.abspath(recycle_dir)
        if source_abs.startswith(recycle_abs + os.sep) or source_abs == recycle_abs:
            dest_video = source_path
        else:
            dest_video = self._resolve_dest_path(recycle_dir, video_filename)
            if os.path.exists(source_path):
                shutil.move(source_path, dest_video)
        new_sub_paths = {}
        for sub_path in subtitle_paths:
            if os.path.exists(sub_path):
                sub_name = os.path.basename(sub_path)
                sub_abs = os.path.abspath(sub_path)
                if sub_abs.startswith(recycle_abs + os.sep):
                    dest_sub = sub_path
                else:
                    dest_sub = self._resolve_dest_path(recycle_dir, sub_name)
                    shutil.move(sub_path, dest_sub)
                new_sub_paths[os.path.basename(sub_path)] = dest_sub

        if new_sub_paths:
            subs = db_get_subtitles(self.conn, task_id)
            for sub in subs:
                sub_basename = os.path.basename(sub.get("source_path", "") or sub.get("target_path", ""))
                if sub_basename in new_sub_paths:
                    db_update_subtitle(self.conn, sub["id"],
                                       target_path=new_sub_paths[sub_basename])
        db_update_task(
            self.conn, task_id,
            source_path=dest_video,
            source_filename=os.path.basename(dest_video),
            file_location="recycle",
            error_message=f"已移入回收站: {recycle_dir}",
        )
        db_update_subs(self.conn, task_id, status="FAILED")
        protected = [
            self.config.get("source_dir", ""),
            self.config.get("temp_dir", ""),
            recycle_dir,
        ]
        self._cleanup_empty_dirs(source_path, protected_dirs=protected)

    def _cleanup_empty_dirs(self, file_path: str, protected_dirs: list = None):
        protected = set()
        if protected_dirs:
            for d in protected_dirs:
                if d:
                    protected.add(os.path.normpath(d).rstrip('/'))
        parent = os.path.dirname(file_path)
        try:
            if os.path.isdir(parent) and not os.listdir(parent):
                if os.path.normpath(parent).rstrip('/') not in protected:
                    os.rmdir(parent)
        except OSError:
            pass
