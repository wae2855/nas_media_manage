import os
import threading
import time
from typing import Optional

from media_importer.features.import_flow.confirm import ConfirmMixin
from media_importer.features.import_flow.context import TaskContext
from media_importer.features.import_flow.progress import TaskProgressReporter
from media_importer.features.import_flow.scan_service import FileScanner
from media_importer.features.import_flow.steps import StepsMixin
from media_importer.features.import_flow.utils import (
    PipelineCancelled,
    PipelineReviewRequired,
    PipelineSkipError,
)
from media_importer.features.scraping import MetadataScraper
from media_importer.features.scraping.match_enums import TierShortReason
from media_importer.features.source_files import SourceCleanupService
from media_importer.features.tasks import (
    FILE_LOCATION_RECYCLE,
    FILE_LOCATION_SOURCE,
    mark_confirming,
    mark_failed,
    mark_imported,
    mark_needs_review,
    mark_skipped,
    start_processing,
)
from media_importer.infrastructure.db import (
    compare_and_update_task,
)
from media_importer.infrastructure.db import (
    count_subtitles_by_task as db_count_subs,
)
from media_importer.infrastructure.db import (
    get_subtitles_by_task as db_get_subtitles,
)
from media_importer.infrastructure.db import (
    update_task as db_update_task,
)
from media_importer.notify.hooks import HookRunner


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
        self.progress_reporter = TaskProgressReporter(task_manager)

        self.scraper = MetadataScraper(config)
        self._last_notified_error = None
        self._last_notified_time = 0
        self._error_notify_cooldown = 300

    def pause(self):
        self._paused.set()

    def resume(self):
        self._paused.clear()

    def is_paused(self) -> bool:
        return self._paused.is_set()

    def _log(self, level: str, message: str, task: Optional[dict] = None, step: str = ""):
        if self.logger:
            if task:
                self.logger.step_log(task.get("task_id", ""), step, level, message)
            else:
                log_method = getattr(self.logger, level.lower(), self.logger.info)
                log_method(message)

    def _update_progress(self, task: dict, step_num: int, step_name: str,
                         percentage: int, **kwargs):
        self._raise_if_stop_requested(task)
        self._get_progress_reporter().update(
            task,
            step_num,
            step_name,
            percentage,
            completed_bytes=kwargs.pop("bytes_copied", 0),
            total_bytes=kwargs.pop("total_bytes", 0),
            force=True,
            **kwargs,
        )

    def _update_transfer_progress(
        self,
        task: dict,
        step_num: int,
        step_name: str,
        percentage: int,
        completed_bytes: int,
        total_bytes: int,
        *,
        check_stop: bool = True,
    ):
        try:
            if check_stop:
                self._raise_if_stop_requested(task)
            self._get_progress_reporter().update(
                task,
                step_num,
                step_name,
                percentage,
                completed_bytes=completed_bytes,
                total_bytes=total_bytes,
            )
        except PipelineCancelled:
            raise
        except Exception as error:
            # 进度是观察能力；SQLite 短暂不可用不能改变文件校验、发布或保留顺序。
            self._log(
                "warn",
                f"进度记录暂时失败，文件处理继续按安全协议执行: {error}",
                task,
                step_name,
            )

    def _raise_if_stop_requested(self, task: dict) -> None:
        from media_importer.features.tasks import task_stop_requested

        task_id = str(task.get("task_id", ""))
        if task_id and task_stop_requested(self.task_manager, task_id):
            raise PipelineCancelled("用户请求停止任务")

    def _complete_user_stop(self, task: dict) -> None:
        from media_importer.features.tasks import complete_requested_stop

        result = complete_requested_stop(
            self.task_manager,
            self.config,
            str(task.get("task_id", "")),
        )
        self._log(
            "info" if result.code == 200 else "warn",
            result.message,
            task,
            "cancel",
        )

    def _get_progress_reporter(self) -> TaskProgressReporter:
        reporter = getattr(self, "progress_reporter", None)
        if reporter is None:
            reporter = TaskProgressReporter(self.task_manager)
            self.progress_reporter = reporter
        return reporter

    def _complete_source_cleanup(self, task: dict) -> None:
        tid = task.get("task_id", "")
        if not task.get("source_unit_id"):
            task["source_cleanup_status"] = "SKIPPED"
            db_update_task(
                self.task_manager.conn,
                tid,
                source_cleanup_status="SKIPPED",
            )
            return

        from media_importer.features.source_files import SourceUnitCoordinator

        self._update_progress(task, 10, "source_cleanup", 96)

        def cleanup_progress(phase, completed, total):
            ranges = {
                "resume_check": (96, 96),
                "transfer": (96, 98),
                "verify_source": (98, 98),
                "verify_target": (98, 99),
                "publish": (99, 99),
            }
            start, end = ranges.get(phase, (96, 99))
            fraction = min(1.0, completed / total) if total > 0 else 0.0
            pct = int(start + (end - start) * fraction)
            self._update_transfer_progress(
                task,
                10,
                f"source_cleanup_{phase}",
                pct,
                completed,
                total,
            )

        try:
            cleanup = SourceUnitCoordinator(
                self.task_manager.conn,
                self.config,
            ).try_recycle(
                task["source_unit_id"],
                completing_task_id=tid,
                phase_callback=cleanup_progress,
            )
            task["source_cleanup_status"] = cleanup.state
        except Exception as cleanup_error:
            task["source_cleanup_status"] = "FAILED"
            self._log(
                "error",
                f"影片已安全入库，但来源处理失败并已保留来源: {cleanup_error}",
                task,
                "cleanup",
            )
            cleanup = None
        db_update_task(
            self.task_manager.conn,
            tid,
            source_cleanup_status=task["source_cleanup_status"],
            source_disposition=(
                {
                    "DELETED": "deleted",
                    "RECYCLED": "recycled",
                    "SKIPPED": "kept",
                    "WAITING": "pending",
                    "BLOCKED": "failed",
                }.get(cleanup.state, "pending")
                if cleanup
                else "failed"
            ),
            source_disposition_message=(
                cleanup.message
                if cleanup
                else "影片已安全入库，但来源处理失败；来源文件已保留"
            ),
        )
        if cleanup:
            self._log("info", cleanup.message, task, "cleanup")

    def _is_system_error(self, error_message: str) -> bool:
        system_error_keywords = [
            "API", "api", "认证", "密钥", "key", "连接", "网络",
            "timeout", "timeout", "配置", "config", "401", "403", "404",
        ]
        error_lower = error_message.lower()
        return any(keyword in error_lower for keyword in system_error_keywords)

    def _notify_program_error(self, error_type: str, error_message: str,
                              extra_data: Optional[dict] = None):
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
        source_mode = (self.config.get("source_policy", {}) or {}).get("mode")
        self.retry_pending_source_cleanup()
        scanner = FileScanner(self.config, task_manager=self.task_manager)
        groups = scanner.scan_and_filter(source_dir)
        if scanner.last_ignored_candidates:
            by_disposition = {}
            for ignored in scanner.last_ignored_candidates:
                disposition = ignored.get("disposition", "ignored")
                by_disposition[disposition] = by_disposition.get(disposition, 0) + 1
            labels = {
                "ignore_promotion": "明显广告",
                "ignore_small_companion": "小视频片段",
            }
            summary = "、".join(
                f"{labels.get(key, key)} {count} 个"
                for key, count in sorted(by_disposition.items())
            )
            examples = "、".join(
                os.path.basename(item["path"])
                for item in scanner.last_ignored_candidates[:3]
            )
            self._log(
                "info",
                f"扫描时已忽略 {len(scanner.last_ignored_candidates)} 个非正片视频："
                f"{summary}；例如 {examples}",
                None,
                "scan",
            )

        tasks = []
        for group in groups:
            source_unit_id = ""
            if source_mode == "recycle_source_unit":
                from media_importer.features.source_files import register_source_unit
                source_unit_id = register_source_unit(
                    self.task_manager.conn,
                    source_dir,
                    group["video_path"],
                    config=self.config,
                ).unit_id
            task = self.task_manager.create_task(
                video_path=group["video_path"],
                video_file=group["video_file"],
                subtitle_files=group["subtitle_files"],
                file_size_mb=group["file_size_mb"],
                source_unit_id=source_unit_id,
            )
            tasks.append(task)

        self._log("info", f"扫描完成，创建/重试 {len(tasks)} 个任务")
        return tasks

    def retry_pending_source_cleanup(self) -> list:
        source_mode = (self.config.get("source_policy", {}) or {}).get("mode")
        if source_mode != "recycle_source_unit":
            return []
        from media_importer.features.source_files import SourceUnitCoordinator

        results = SourceUnitCoordinator(
            self.task_manager.conn,
            self.config,
        ).retry_pending()
        for cleanup in results:
            self._log("info", cleanup.message, None, "cleanup")
        return results

    def process_one(self, task: dict, *, claimed: bool = False) -> bool:
        if not claimed:
            # 对直接处理单个任务的入口也执行 CAS，避免与批处理线程重复消费。
            start_fields = start_processing(dict(task))
            claimed_task = compare_and_update_task(
                self.task_manager.conn,
                task.get("task_id", ""),
                expect_status="PENDING",
                expect_stage="QUEUED",
                **start_fields,
            )
            if claimed_task is None:
                self._log("warn", "任务已被其他执行器领取，跳过重复处理", task)
                return False
            task.update(claimed_task)

        ctx = TaskContext(task)
        original_source_video = ctx.source_path or ctx.current_video_path
        original_source_subs = list(ctx.subtitle_files)
        tid = ctx.task_id

        try:
            self.hooks.run_before_process(task)
            self._step_scrape(task)
            self._step_validate(task)

            # 检查 FAILED 状态（AI 判定为非影视文件）
            match_result = (task.get("scrape_result") or {}).get("match_level", "")
            if match_result == "FAILED":
                scrape_res = task.get("scrape_result", {})
                fail_msg = scrape_res.get("tier_short_reason", "AI 判定为非影视文件")
                db_update_task(self.task_manager.conn, tid,
                               **mark_failed(
                                   ctx, fail_msg,
                                   file_location=ctx.file_location,
                                   video_path=ctx.current_video_path,
                                   completed=False,
                               ))
                self._log("error", f"任务失败: {fail_msg}", task)
                return False

            if task.get("_force_fail"):
                fail_reason = task.get("_fail_reason", "未知失败原因")
                db_update_task(self.task_manager.conn, tid,
                               **mark_failed(
                                   ctx, fail_reason,
                                   file_location=ctx.file_location,
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
                scrape_result = task.get("scrape_result", {})
                tier_short = scrape_result.get('tier_short_reason') or TierShortReason.UNKNOWN
                # 组合文案：匹配状态 + 具体拦截原因（前端及日志都能看懂为何待确认）
                concern_msgs = [
                    c.get("message") for c in (scrape_result.get("match_concerns") or [])
                    if isinstance(c, dict) and c.get("message")
                ]
                confirm_reason = "；".join([tier_short] + concern_msgs[:2]) if concern_msgs else tier_short
                fields = mark_confirming(ctx, confirm_reason)
                # 同步持久化刮削结果（含 match_concerns 待确认原因），供前端展示
                fields.update({
                    "scrape_result": scrape_result,
                    "scrape_dimensions": task.get("scrape_dimensions", {}),
                })
                db_update_task(self.task_manager.conn, tid, **fields)
                self._log("info", f"任务等待人工确认: {task.get('source_filename', '')} - {tier_short}", task)
                self.hooks.run_after_success(task)
                if self.metrics:
                    self.metrics.record_task_complete("confirming")
                return True

            self._step_classify(task)
            self._step_rename(task)
            if task.get("used_fallback"):
                concern = {
                    "code": "NO_CLASSIFICATION_RULE",
                    "message": "没有匹配到正式入库规则，将进入待整理区",
                }
                task["match_concerns"] = [concern]
                fields = mark_confirming(
                    ctx,
                    "没有匹配到正式入库规则，请调整维度、重新刮削，或明确确认放入待整理区",
                )
                fields.update({
                    "match_concerns": task["match_concerns"],
                    "import_path": task.get("import_path", ""),
                    "classify_result": task.get("classify_result", ""),
                    "final_filename": task.get("final_filename", ""),
                    "used_fallback": 1,
                })
                db_update_task(self.task_manager.conn, tid, **fields)
                self._log(
                    "info",
                    "任务未匹配正式规则，等待用户确认是否放入待整理区",
                    task,
                    "classify",
                )
                if self.metrics:
                    self.metrics.record_task_complete("confirming")
                return True
            self._step_dedup(task)

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

            self._prepare_import_input(task)
            self._step_import(task, original_source_video, original_source_subs)
            self._step_notify(task)
            self._complete_source_cleanup(task)
            self._step_record(task)
            db_update_task(self.task_manager.conn, tid,
                           **mark_imported(ctx))
            self.hooks.run_after_success(task)
            if self.metrics:
                self.metrics.record_task_complete("success")
            self._log("info", f"任务处理成功: {task.get('source_filename', '')}", task)
            return True

        except PipelineCancelled:
            self._complete_user_stop(task)
            if self.metrics:
                self.metrics.record_task_complete("cancelled")
            return False

        except PipelineReviewRequired as e:
            fields = mark_confirming(ctx, str(e))
            fields.update({
                "dedup_result": e.result,
                "dedup_existing_file": e.result.get("existing_file", ""),
                "final_filename": task.get("final_filename", ""),
                "import_path": task.get("import_path", ""),
            })
            db_update_task(self.task_manager.conn, tid, **fields)
            self._log("info", f"目标片库冲突待确认: {task.get('source_filename', '')}", task, "dedup")
            if self.metrics:
                self.metrics.record_task_complete("confirming")
            return True

        except PipelineSkipError as e:
            self._log("info", f"任务跳过: {task.get('source_filename', '')} - {e}", task)
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

    def run_all(self):
        from media_importer.features.configuration import (
            inspect_processing_support_readiness,
        )

        readiness = inspect_processing_support_readiness(self.config)
        if readiness["state"] != "READY":
            blocking = ", ".join(readiness["blocking"])
            raise RuntimeError(f"配置尚未就绪，已阻止文件处理: {blocking}")
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
            "PENDING": 0, "SUCCESS": 0, "FAILED": 0, "SKIPPED": 0,
            "total": 0, "subtitle_count": 0, "video_count": 0,
        }

        while not self._paused.is_set():
            task = self.task_manager.claim_next_pending()
            if task is None:
                break
            batch_stats["total"] += 1
            total, _ = db_count_subs(self.task_manager.conn, task.get("task_id", ""))
            batch_stats["subtitle_count"] += total
            batch_stats["video_count"] += 1
            self.process_one(task, claimed=True)
            final_status = task.get("status", "UNKNOWN")
            batch_stats[final_status] = batch_stats.get(final_status, 0) + 1

        batch_stats["total_files"] = batch_stats["video_count"] + batch_stats["subtitle_count"]

        if self.notifier and self.notifier.should_notify("batch_complete"):
            try:
                self.notifier.notify_batch_complete([], summary=batch_stats)
            except Exception:
                pass
        self._log("info", "批量处理完成")
