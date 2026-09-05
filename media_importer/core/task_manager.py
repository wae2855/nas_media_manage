#!/usr/bin/env python3
import os
import shutil
import threading
from typing import Optional

from media_importer.features.operation_locks import serialize_source_disposition
from media_importer.features.organization_state import serialize_reorganization
from media_importer.features.tasks.task_lifecycle_compat import mark_cancelled, reset_for_retry

from .db import (
    VALID_STATUSES,
    init_db,
)
from .db import (
    claim_next_pending as db_claim_next_pending,
)
from .db import (
    clear_tasks as db_clear_tasks,
)
from .db import (
    count_by_status as db_count_by_status,
)
from .db import (
    count_by_status_and_stage as db_count_by_status_and_stage,
)
from .db import (
    create_subtitles as db_create_subtitles,
)
from .db import (
    create_task as db_create_task,
)
from .db import (
    find_by_fingerprint as db_find_by_fingerprint,
)
from .db import (
    find_by_source_path as db_find_by_source_path,
)
from .db import (
    get_next_pending as db_get_next_pending,
)
from .db import (
    get_subtitles_by_task as db_get_subtitles,
)
from .db import (
    get_task as db_get_task,
)
from .db import (
    has_running_tasks as db_has_running_tasks,
)
from .db import (
    list_all_tasks as db_list_all_tasks,
)
from .db import (
    list_tasks as db_list_tasks,
)
from .db import (
    update_subtitle as db_update_subtitle,
)
from .db import (
    update_subtitles_by_task as db_update_subs,
)
from .db import (
    update_task as db_update_task,
)

VALID_STATUSES = list(VALID_STATUSES)


class TaskManager:
    def __init__(self, data_dir: str, config: Optional[dict] = None):
        self.config = config or {}
        db_path = os.path.join(data_dir, "tasks.db")
        self.conn = init_db(db_path)
        if self.config:
            from media_importer.features.tasks.organization_service import (
                backfill_fallback_outcomes,
            )

            try:
                backfill_fallback_outcomes(self.conn, self.config)
            except (OSError, TypeError, ValueError):
                # 历史标记是兼容增强，不能让尚未完成存储配置的首次启动失败。
                pass
        self._lock = threading.RLock()

    def create_task(self, video_path: str, video_file: str,
                    subtitle_files: Optional[list] = None,
                    file_size_mb: float = 0,
                    initial_status: Optional[str] = None,
                    source_unit_id: str = "", stage: str = "QUEUED",
                    task_kind: str = "IMPORT", parent_task_id: str = "",
                    source_fingerprint: str = "", source_file_size: int = 0,
                    source_mtime: str = "") -> dict:
        task = db_create_task(
            self.conn,
            source_path=video_path,
            source_filename=video_file,
            file_size_mb=file_size_mb,
            source_unit_id=source_unit_id,
            stage=stage,
            task_kind=task_kind,
            parent_task_id=parent_task_id,
            source_fingerprint=source_fingerprint,
            source_file_size=source_file_size,
            source_mtime=source_mtime,
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

    def create_or_reuse_source_task(
        self,
        video_path: str,
        video_file: str,
        subtitle_files: Optional[list] = None,
        file_size_mb: float = 0,
        source_unit_id: str = "",
        source_fingerprint: str = "",
        source_file_size: int = 0,
        source_mtime: str = "",
    ) -> dict:
        """Atomically create one import task or reuse the latest source task.

        The process lock closes the check-then-create race shared by scanner,
        watcher and manual single-file requests in the fnOS single-process
        deployment. Processing itself always happens after this lock is released.
        """
        canonical_path = os.path.realpath(video_path)
        source_filename = video_file or os.path.basename(video_path)
        with self._lock:
            decision = self.check_source_duplicate(
                video_path,
                source_fingerprint=source_fingerprint,
            )
            action = decision.get("action", "CREATE")
            if action != "CREATE" and action != "REPROCESS":
                task_id = decision.get("task_id")
                task = db_get_task(self.conn, task_id) if task_id else None
                updates = {"last_seen_at": self._now_iso()}
                refresh_evidence = action in ("RENAME_DETECTED", "UPDATE_MTIME")
                if source_fingerprint and (
                    refresh_evidence or not (task or {}).get("source_fingerprint")
                ):
                    updates["source_fingerprint"] = source_fingerprint
                if source_file_size and (
                    refresh_evidence or not (task or {}).get("source_file_size")
                ):
                    updates["source_file_size"] = source_file_size
                if source_mtime and (
                    refresh_evidence or not (task or {}).get("source_mtime")
                ):
                    updates["source_mtime"] = source_mtime
                if action == "RENAME_DETECTED":
                    updates["source_path"] = canonical_path
                    updates["source_filename"] = source_filename
                task = db_update_task(self.conn, task_id, **updates) if task_id else task
                return {
                    "created": False,
                    "task": task,
                    **decision,
                }

            task = self.create_task(
                video_path=canonical_path,
                video_file=source_filename,
                subtitle_files=subtitle_files,
                file_size_mb=file_size_mb,
                source_unit_id=source_unit_id,
                source_fingerprint=source_fingerprint,
                source_file_size=source_file_size,
                source_mtime=source_mtime,
            )
            return {
                "created": True,
                "task": task,
                "exists": action == "REPROCESS",
                "task_id": task["task_id"],
                "action": action,
                "reason": decision.get("reason", "已创建新任务"),
            }

    @staticmethod
    def _now_iso() -> str:
        from datetime import datetime

        return datetime.now().isoformat()

    def get_task(self, task_id: str) -> Optional[dict]:
        return db_get_task(self.conn, task_id)

    def get_next_pending(self) -> Optional[dict]:
        return db_get_next_pending(self.conn)

    def claim_next_pending(self) -> Optional[dict]:
        return db_claim_next_pending(self.conn)

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
                         "final_filename", "video_path", "subtitle_files",
                         "progress_item_name", "progress_item_kind",
                         "progress_item_index", "progress_item_total"):
                    task[k] = v
            db_update_task(
                self.conn, task["task_id"],
                current_step=step_num, step_name=step_name,
                percentage=min(100, max(0, percentage)),
                **kwargs
            )

    def list_tasks(self, status: Optional[str] = None, limit: int = 20,
                   offset: int = 0, exclude_completed: Optional[bool] = None,
                   stage: Optional[str] = None) -> list:
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

    @serialize_reorganization
    @serialize_source_disposition(
        lambda self, task_id, **_kwargs: (
            (db_get_task(self.conn, task_id) or {}).get("source_unit_id") or f"task:{task_id}"
        )
    )
    def retry_task(self, task_id: str, *, expected_status: str = "") -> Optional[dict]:
        """整任务重试；CAS 保证并发双 retry 只成功一次。"""
        task = db_get_task(self.conn, task_id)
        if not task:
            return None
        if expected_status and task.get("status") != expected_status:
            return None
        source_unit_id = str(task.get("source_unit_id") or "")
        if source_unit_id:
            from media_importer.infrastructure.db import get_source_unit

            unit = get_source_unit(self.conn, source_unit_id)
            if unit and unit.get("state") in {"RECYCLING", "DELETING", "RECYCLED", "DELETED"}:
                return None
        from media_importer.features.tasks.transitions import can_apply
        if not can_apply(task, "retry"):
            return None
        # 先取期望态（reset_for_retry 会就地修改 task dict）
        expect_status = task.get("status", "")
        expect_stage = task.get("stage", "")
        if task.get("task_kind") == "REORGANIZE":
            from media_importer.features.tasks.transitions import apply
            from media_importer.infrastructure.db import find_active_reorganization

            active = find_active_reorganization(self.conn, str(task.get("parent_task_id") or ""))
            if active and active["task_id"] != task_id:
                return None
            fields = apply(task, "retry_reorganization")
        else:
            fields = reset_for_retry(task)
        from media_importer.infrastructure.db import compare_and_update_task
        return compare_and_update_task(
            self.conn, task_id,
            expect_status=expect_status,
            expect_stage=expect_stage,
            **fields,
        )

    def cancel_task(self, task_id: str, reason: str = "用户取消") -> Optional[dict]:
        with self._lock:
            task = db_get_task(self.conn, task_id)
            if not task:
                return None
            from media_importer.features.tasks.transitions import can_apply
            if not can_apply(task, "cancel"):
                return {"error": f"当前状态不可取消: {task.get('status')}/{task.get('stage')}"}
            fields = mark_cancelled(task, reason)
            from media_importer.infrastructure.db import compare_and_update_task
            return compare_and_update_task(
                self.conn, task_id,
                expect_status="PENDING", expect_stage="QUEUED",
                **fields,
            )

    def retry_all_failed(self, *, include_skipped: bool = False,
                         include_cancelled: bool = False) -> list:
        """批量重试（S3 决策 D2）：默认仅 FAILED。

        SKIPPED/CANCELLED 是用户终态决策，需显式参数才复活。
        """
        resurrectable = {"FAILED"}
        if include_skipped:
            resurrectable.add("SKIPPED")
        if include_cancelled:
            resurrectable.add("CANCELLED")
        rows = db_list_all_tasks(self.conn, limit=10000)
        retried = []
        for task in rows:
            if task["status"] in resurrectable:
                updated = self.retry_task(task["task_id"], expected_status=task["status"])
                if updated:
                    retried.append(updated)
        return retried

    def clear_tasks(self, status: Optional[str] = None, stage: Optional[str] = None):
        db_clear_tasks(self.conn, status=status, stage=stage)

    def count_by_status(self) -> dict:
        return db_count_by_status(self.conn)

    def count_by_status_and_stage(self) -> dict:
        return db_count_by_status_and_stage(self.conn)

    def has_running_tasks(self) -> bool:
        return db_has_running_tasks(self.conn)

    def check_source_duplicate(self, source_path: str,
                                source_fingerprint: str = "") -> dict:
        canonical_path = os.path.realpath(source_path)
        history = db_find_by_source_path(self.conn, canonical_path)
        if history is None and canonical_path != source_path:
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
        if old_status == "PENDING":
            return {
                "exists": True,
                "task_id": history["task_id"],
                "old_status": old_status,
                "action": "SKIP",
                "reason": f"同一来源已有活动任务，跳过 ({old_status}/{old_stage})",
            }
        if old_status == "FAILED":
            return {
                "exists": True,
                "task_id": history["task_id"],
                "old_status": old_status,
                "action": "SKIP",
                "reason": "同一路径已有失败任务，请在原任务上手动重试",
            }
        if old_status in ("SUCCESS", "SKIPPED", "CANCELLED") and self._is_file_changed(
            canonical_path, history
        ):
            current_size = (
                os.path.getsize(canonical_path) if os.path.isfile(canonical_path) else 0
            )
            old_size = history.get("source_file_size") or int(
                (history.get("file_size_mb") or 0) * 1024 * 1024
            )
            exact_size_changed = bool(
                history.get("source_file_size")
                and current_size != history["source_file_size"]
            )
            if exact_size_changed or (
                not history.get("source_file_size")
                and old_size
                and abs(current_size - old_size) > 1024
            ):
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
        if old_status in ("SUCCESS", "SKIPPED", "CANCELLED"):
            return {
                "exists": True,
                "task_id": history["task_id"],
                "old_status": old_status,
                "action": "SKIP",
                "reason": f"同一来源已有未变化的已结束任务 ({old_status})",
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
        old_size = history.get("source_file_size")
        if old_size:
            if current_size != old_size:
                return True
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
        task = db_get_task(self.conn, task_id)
        if not task:
            return False
        from media_importer.features.configuration.storage_topology import path_in_library

        protected_paths = [source_path, *(str(path) for path in subtitle_paths if path)]
        if task.get("file_location") == "import" or any(
            path_in_library(self.config, path) for path in protected_paths
        ):
            return False
        os.makedirs(recycle_dir, exist_ok=True)
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
            recycle_dir,
        ]
        self._cleanup_empty_dirs(source_path, protected_dirs=protected)
        return True

    def _cleanup_empty_dirs(self, file_path: str, protected_dirs: Optional[list] = None):
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
