import os
import time
import threading
from media_importer.core.db import (
    update_task as db_update_task,
    get_subtitles_by_task as db_get_subtitles,
    count_subtitles_by_task as db_count_subs,
)
from media_importer.core.task_lifecycle import (
    FILE_LOCATION_RECYCLE,
    FILE_LOCATION_SOURCE,
    FILE_LOCATION_TEMP,
    mark_confirming,
    mark_failed,
    mark_imported,
    mark_needs_review,
    mark_skipped,
    mark_temp_ready,
    start_processing,
)
from media_importer.features.import_flow.confirm import ConfirmMixin
from media_importer.features.import_flow.context import TaskContext
from media_importer.features.import_flow.services import SourceCleanupService
from media_importer.storage.file_scanner import FileScanner
from media_importer.storage.file_copier import FileCopier
from media_importer.scraper.metadata_scraper import MetadataScraper
from media_importer.storage.file_mover import delete_source_files
from media_importer.notify.hooks import HookRunner
from media_importer.features.import_flow.utils import PipelineSkipError
from media_importer.features.import_flow.steps import StepsMixin


class PipelineRunner(StepsMixin, ConfirmMixin):
    def __init__(self, config: dict, task_manager,
                 metrics=None, logger=None, notifier=None):
        self.config = config
        self.task_manager = task_manager
        self.metrics = metrics
        self.logger = logger
        self.notifier = notifier
        self.hooks = HookRunner(config, logger)
        self._paused = threading.Event()

        self.scraper = MetadataScraper(config)
        video_exts = config.get("video_extensions", [])
        sub_exts = config.get("subtitle_extensions", [])
        media_exts = set(
            ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            for ext in video_exts + sub_exts
        )
        self.copier = FileCopier(config.get('temp_dir', ''), media_exts)

        self._last_notified_error = None
        self._last_notified_time = 0
        self._error_notify_cooldown = 300

    def pause(self):
        self._paused.set()

    def resume(self):
        self._paused.clear()

    def is_paused(self) -> bool:
        return self._paused.is_set()

    def _log(self, level: str, message: str, task: dict = None, step: str = ""):
        if self.logger:
            if task:
                self.logger.step_log(task.get("task_id", ""), step, level, message)
            else:
                log_method = getattr(self.logger, level.lower(), self.logger.info)
                log_method(message)

    def _update_progress(self, task: dict, step_num: int, step_name: str,
                         percentage: int, **kwargs):
        self.task_manager.update_progress(
            task, step_num, step_name, percentage, **kwargs
        )

    def _is_system_error(self, error_message: str) -> bool:
        system_error_keywords = [
            "API", "api", "认证", "密钥", "key", "连接", "网络",
            "timeout", "timeout", "配置", "config", "401", "403", "404",
        ]
        error_lower = error_message.lower()
        return any(keyword in error_lower for keyword in system_error_keywords)

    def _notify_program_error(self, error_type: str, error_message: str,
                              extra_data: dict = None):
        if not self.notifier:
            return
        current_time = time.time()
        error_key = f"{error_type}:{error_message[:100]}"
        if (self._last_notified_error == error_key and
                current_time - self._last_notified_time < self._error_notify_cooldown):
            self._log("debug", f"跳过重复系统错误通知: {error_type}", None, "notify")
            return
        try:
            self.notifier.notify_program_error(error_type, error_message, extra_data)
            self._last_notified_error = error_key
            self._last_notified_time = current_time
            self._log("info", f"发送系统错误通知: {error_type}", None, "notify")
        except Exception as e:
            self._log("warn", f"系统错误通知发送失败: {e}", None, "notify")

    def _notify(self, event_type: str, task: dict):
        if self.notifier and self.notifier.should_notify(event_type):
            try:
                self.notifier.notify(event_type, task)
            except Exception as e:
                self._log("warn", f"通知发送失败: {e}", task, "notify")

    def scan_and_create_tasks(self) -> list:
        source_dir = self.config.get('source_dir', '')
        scanner = FileScanner(self.config, task_manager=self.task_manager)
        groups = scanner.scan_and_filter(source_dir)

        tasks = []
        for group in groups:
            task = self.task_manager.create_task(
                video_path=group["video_path"],
                video_file=group["video_file"],
                subtitle_files=group["subtitle_files"],
                file_size_mb=group["file_size_mb"],
            )
            tasks.append(task)

        self._log("info", f"扫描完成，创建/重试 {len(tasks)} 个任务")
        return tasks

    def process_one(self, task: dict) -> bool:
        ctx = TaskContext(task)
        original_source_video = ctx.source_path or ctx.current_video_path
        original_source_subs = list(ctx.subtitle_files)
        temp_video_path_for_cleanup = None

        tid = ctx.task_id

        db_update_task(self.task_manager.conn, tid, **start_processing(ctx))

        try:
            self.hooks.run_before_process(task)
            self._step_copy(task)
            temp_video_path_for_cleanup = ctx.current_video_path
            db_update_task(self.task_manager.conn, tid, **mark_temp_ready(ctx))
            self._step_scrape(task)
            self._step_validate(task)

            if task.get("_force_fail"):
                fail_reason = task.get("_fail_reason", "未知失败原因")
                db_update_task(self.task_manager.conn, tid,
                               **mark_failed(
                                   ctx, fail_reason,
                                   file_location=FILE_LOCATION_TEMP,
                                   video_path=ctx.current_video_path,
                                   completed=False,
                               ))
                self._log("error", fail_reason, task)
                return False

            if task.get("_needs_review"):
                skip_reason = task.get("skip_reason", "需人工审核")
                db_update_task(self.task_manager.conn, tid,
                               **mark_needs_review(ctx, skip_reason))
                self._log("warn", f"任务需人工审核: {skip_reason}", task)
                return False

            if task.get("_needs_confirm"):
                confirm_reason = task.get("_confirm_reason", "刮削信息不足")
                db_update_task(self.task_manager.conn, tid,
                               **mark_confirming(ctx, confirm_reason))
                self._log("info", f"任务等待人工确认: {task.get('source_filename', '')} - {confirm_reason}", task)
                self.hooks.run_after_success(task)
                if self.metrics:
                    self.metrics.record_task_complete("confirming")
                return True

            self._step_classify(task)

            manual_review = self.config.get("manual_review", {})
            review_enabled = manual_review.get("enabled", False)

            if review_enabled:
                db_update_task(self.task_manager.conn, tid,
                               **mark_confirming(ctx))
                self._log("info", f"任务等待人工确认: {task.get('source_filename', '')}", task)
                self.hooks.run_after_success(task)
                if self.metrics:
                    self.metrics.record_task_complete("confirming")
                return True

            self._step_dedup(task)
            self._step_rename(task)
            self._step_import(task, original_source_video, original_source_subs)
            self._step_notify(task)
            self._step_record(task)

            db_update_task(self.task_manager.conn, tid,
                           **mark_imported(ctx))
            self.hooks.run_after_success(task)
            if self.metrics:
                self.metrics.record_task_complete("success")
            self._log("info", f"任务处理成功: {task.get('source_filename', '')}", task)
            return True

        except PipelineSkipError as e:
            self._log("info", f"任务跳过: {task.get('source_filename', '')} - {e}", task)
            self._cleanup_temp_on_failure(task, temp_video_path_for_cleanup)
            source_cleanup = SourceCleanupService(self.config).recycle_source_after_skip(
                task,
                original_source_video,
                original_source_subs,
            )
            file_location = FILE_LOCATION_RECYCLE if source_cleanup.moved_count else FILE_LOCATION_SOURCE
            if source_cleanup.message:
                self._log("info", source_cleanup.message, task, "cleanup")
            fields = mark_skipped(ctx, str(e), file_location=file_location)

            db_update_task(self.task_manager.conn, tid, **fields)

            if self.metrics:
                self.metrics.record_task_complete("skipped")
            return True

        except Exception as e:
            error_msg = str(e)
            fields = mark_failed(ctx, error_msg, file_location=FILE_LOCATION_SOURCE)
            self._log("error", f"任务失败: {task.get('source_filename', '')} - {e}", task)
            self._cleanup_temp_on_failure(task, temp_video_path_for_cleanup)

            db_update_task(self.task_manager.conn, tid, **fields)

            self.hooks.run_after_failure(task)
            if self.metrics:
                self.metrics.record_task_complete("failed")

            if self._is_system_error(error_msg):
                self._notify_program_error(
                    "system_error", error_msg,
                    {"video_file": task.get("source_filename", ""), "task_id": tid}
                )
            return False

    def _cleanup_temp_on_failure(self, task: dict, temp_video_path: str):
        temp_dir = self.config.get('temp_dir', '')
        source_dir = self.config.get('source_dir', '')
        allowed_dirs = [source_dir, temp_dir]
        files_to_delete = []
        if temp_video_path and temp_dir and str(temp_video_path).startswith(temp_dir):
            files_to_delete.append(temp_video_path)
            for sub in task.get("subtitle_files", []):
                if temp_dir in str(sub):
                    files_to_delete.append(sub)
        if files_to_delete:
            delete_source_files(files_to_delete, allowed_base_dirs=allowed_dirs)
            self._log("info", f"已清理 temp 目录失败文件: {len(files_to_delete)} 个", task, "cleanup")

    def run_all(self):
        self._log("info", "开始批量处理")

        source_dir = self.config.get("source_dir", "")

        pending_task = self.task_manager.get_next_pending()

        if pending_task is None:
            self.scan_and_create_tasks()
            all_tasks = self.task_manager.list_tasks(limit=10000)
            video_count = sum(1 for t in all_tasks if t.get("status") == "PENDING")
            subtitle_count = sum(
                len(db_get_subtitles(self.task_manager.conn, t.get("task_id", "")))
                for t in all_tasks if t.get("status") == "PENDING"
            )
            if video_count > 0 and self.notifier:
                self.notifier.notify_batch_start(source_dir, video_count, subtitle_count)
        else:
            all_tasks = self.task_manager.list_tasks(status="PENDING", limit=10000)
            if self.notifier:
                video_count = len(all_tasks)
                subtitle_count = 0
                for t in all_tasks:
                    total, _ = db_count_subs(self.task_manager.conn, t.get("task_id", ""))
                    subtitle_count += total
                self.notifier.notify_batch_start(source_dir, video_count, subtitle_count)

        batch_stats = {
            "PROCESSING": 0, "SUCCESS": 0, "FAILED": 0, "SKIPPED": 0,
            "total": 0, "subtitle_count": 0, "video_count": 0,
        }

        while not self._paused.is_set():
            task = self.task_manager.get_next_pending()
            if task is None:
                break
            batch_stats["total"] += 1
            total, _ = db_count_subs(self.task_manager.conn, task.get("task_id", ""))
            batch_stats["subtitle_count"] += total
            batch_stats["video_count"] += 1
            self.process_one(task)
            final_status = task.get("status", "UNKNOWN")
            batch_stats[final_status] = batch_stats.get(final_status, 0) + 1

        batch_stats["total_files"] = batch_stats["video_count"] + batch_stats["subtitle_count"]

        if self.notifier and self.notifier.should_notify("batch_complete"):
            try:
                self.notifier.notify_batch_complete([], summary=batch_stats)
            except Exception:
                pass
        self._log("info", "批量处理完成")
