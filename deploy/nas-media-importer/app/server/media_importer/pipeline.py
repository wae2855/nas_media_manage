#!/usr/bin/env python3
import os
import re
import time
import shutil
import threading
from datetime import datetime
from task_manager import TaskManager
from db import (
    get_task as db_get_task,
    update_task as db_update_task,
    list_tasks as db_list_tasks,
    list_all_tasks as db_list_all_tasks,
    get_subtitles_by_task as db_get_subtitles,
    update_subtitles_by_task as db_update_subs,
    update_subtitle as db_update_subtitle,
    count_subtitles_by_task as db_count_subs,
)
from file_scanner import FileScanner
from file_copier import FileCopier
from llm_scraper import LLMScraper, LLMScrapeError
from classifier import classify
from dedup_checker import check_duplicate
from file_mover import apply_filename_template, move_to_import, delete_source_files, delete_source_with_companions, remove_empty_parent_dir, cleanup_source_non_media
from hooks import HookRunner


def _extract_series_name(filename: str) -> str:
    name = os.path.splitext(filename)[0]
    name = re.sub(r'[._]', ' ', name)
    name = re.sub(r'\b[Ss]\d{1,2}[Ee]\d{1,2}\b.*$', '', name)
    name = re.sub(r'\b[Ss]\d{1,2}\b.*$', '', name)
    name = re.sub(r'\b(?:2160p|1080p|720p|480p|4K|UHD|HDR)\b.*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\b(?:WEB|HDTV|BluRay|BDRip|WEBRip|WEB-DL|REMUX)\b.*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\b(?:x264|x265|HEVC|H\.?264|H\.?265|AAC|DTS|DD|ATMOS)\b.*$', '', name, flags=re.IGNORECASE)
    name = name.strip(' -.')
    return name


PIPELINE_STEPS = [
    (1, "scan", "扫描源目录"),
    (2, "copy", "复制到临时目录"),
    (3, "scrape", "AI刮削元数据"),
    (4, "validate", "验证刮削结果"),
    (5, "classify", "分类匹配路径"),
    (6, "dedup", "同名文件检测"),
    (7, "rename", "生成目标文件名"),
    (8, "import", "入库移动文件"),
    (9, "notify", "发送通知"),
    (10, "record", "记录处理结果"),
]


class PipelineRunner:
    def __init__(self, config: dict, task_manager: TaskManager,
                 metrics=None, logger=None, notifier=None):
        self.config = config
        self.task_manager = task_manager
        self.metrics = metrics
        self.logger = logger
        self.notifier = notifier
        self.hooks = HookRunner(config, logger)
        self._paused = threading.Event()

        self.scraper = LLMScraper(config)
        self.copier = FileCopier(config.get('temp_dir', ''))

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
        quarantine_dir = self.config.get('quarantine_dir', '')
        scanner = FileScanner(self.config, task_manager=self.task_manager)
        groups = scanner.scan_and_filter(source_dir) if quarantine_dir else scanner.scan_and_group(source_dir)

        tasks = []
        for group in groups:
            retry_task_id = group.get("retry_task_id")
            if retry_task_id:
                db_update_task(
                    self.task_manager.conn, retry_task_id,
                    status="PENDING",
                    started_at=None,
                    completed_at=None,
                    error_code=0,
                    error_message="",
                    current_step=0,
                    step_name="",
                    percentage=0,
                    last_seen_at=datetime.now().isoformat(),
                )
                task = self.task_manager.get_task(retry_task_id)
                task["video_path"] = group["video_path"]
                task["subtitle_files"] = group["subtitle_files"]
            else:
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
        original_source_video = task.get("source_path", task.get("video_path", ""))
        original_source_subs = list(task.get("subtitle_files", []))
        temp_video_path_for_cleanup = None

        tid = task.get("task_id", "")

        task["status"] = "PROCESSING"
        task["started_at"] = datetime.now().isoformat()
        db_update_task(self.task_manager.conn, tid,
                       status="PROCESSING", started_at=task["started_at"])

        try:
            self.hooks.run_before_process(task)
            self._step_copy(task)
            temp_video_path_for_cleanup = task.get("video_path", "")
            self._step_scrape(task)
            self._step_validate(task)
            self._step_classify(task)

            manual_review = self.config.get("manual_review", {})
            review_enabled = manual_review.get("enabled", False)

            if review_enabled:
                task["confirm_status"] = "PENDING"
                task["status"] = "CONFIRMING"
                db_update_task(self.task_manager.conn, tid,
                               confirm_status="PENDING", status="CONFIRMING")
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

            task["status"] = "SUCCESS"
            task["completed_at"] = datetime.now().isoformat()
            task["import_success"] = 1
            db_update_task(self.task_manager.conn, tid,
                           status="SUCCESS", completed_at=task["completed_at"],
                           import_success=1)
            self.hooks.run_after_success(task)
            if self.metrics:
                self.metrics.record_task_complete("success")
            self._log("info", f"任务处理成功: {task.get('source_filename', '')}", task)
            return True

        except PipelineSkipError as e:
            task["status"] = "SKIPPED"
            task["skip_reason"] = str(e)
            task["completed_at"] = datetime.now().isoformat()
            db_update_task(self.task_manager.conn, tid,
                           status="SKIPPED", skip_reason=str(e),
                           completed_at=task["completed_at"])
            if self.metrics:
                self.metrics.record_task_complete("skipped")
            self._log("info", f"任务跳过: {task.get('source_filename', '')} - {e}", task)
            self._cleanup_temp_on_failure(task, temp_video_path_for_cleanup)

            delete_after_process = self.config.get('source_file_handling', {}).get('delete_after_process', True)
            if delete_after_process:
                source_dir = self.config.get('source_dir', '')
                if source_dir and original_source_video and original_source_video.startswith(source_dir):
                    video_exts = [ext.lower() for ext in self.config.get('video_extensions', [])]
                    sub_exts = [ext.lower() for ext in self.config.get('subtitle_extensions', [])]
                    companion_count = delete_source_with_companions(
                        original_source_video, original_source_subs,
                        video_exts, sub_exts, allowed_base_dirs=[source_dir]
                    )
                    msg = f"已清理源目录文件: {os.path.basename(original_source_video)}"
                    if companion_count > 0:
                        msg += f" (含 {companion_count} 个附属文件)"
                    self._log("info", msg, task, "cleanup")
                    remove_empty_parent_dir(original_source_video, source_dir)
            else:
                self._log("info", f"保留源目录文件（配置为不删除）: {os.path.basename(original_source_video)}", task, "cleanup")
            return True

        except Exception as e:
            error_msg = str(e)
            task["status"] = "FAILED"
            task["error_message"] = error_msg
            task["completed_at"] = datetime.now().isoformat()
            db_update_task(self.task_manager.conn, tid,
                           status="FAILED", error_message=error_msg,
                           completed_at=task["completed_at"])
            self.hooks.run_after_failure(task)
            if self.metrics:
                self.metrics.record_task_complete("failed")
            self._log("error", f"任务失败: {task.get('source_filename', '')} - {e}", task)
            self._cleanup_temp_on_failure(task, temp_video_path_for_cleanup)

            if self._is_system_error(error_msg):
                self._notify_program_error(
                    "system_error", error_msg,
                    {"video_file": task.get("source_filename", ""), "task_id": tid}
                )
            return False

    def confirm_task(self, task_id: str) -> bool:
        task = self.task_manager.get_task(task_id)
        if not task or task.get("status") != "CONFIRMING":
            raise PipelineError(f"任务不可确认: 状态={task.get('status', 'UNKNOWN')}")
        tid = task_id
        original_source_video = task.get("source_path", "")
        subtitle_files = task.get("subtitle_files", [])
        original_source_subs = subtitle_files or []

        task["confirm_status"] = "CONFIRMED"
        task["confirmed_at"] = datetime.now().isoformat()
        db_update_task(self.task_manager.conn, tid,
                       confirm_status="CONFIRMED",
                       confirmed_at=task["confirmed_at"])

        db_update_subs(self.task_manager.conn, tid,
                       confirm_status="CONFIRMED")

        try:
            self._step_dedup(task)
            self._step_rename(task)
            self._step_import_from_confirm(task, original_source_video, original_source_subs)
            self._step_notify(task)
            self._step_record(task)

            task["status"] = "SUCCESS"
            task["completed_at"] = datetime.now().isoformat()
            task["import_success"] = 1
            db_update_task(self.task_manager.conn, tid,
                           status="SUCCESS", completed_at=task["completed_at"],
                           import_success=1)
            self.hooks.run_after_success(task)
            if self.metrics:
                self.metrics.record_task_complete("success")
            self._log("info", f"确认入库完成: {task.get('source_filename', '')}", task)
            return True
        except Exception as e:
            error_msg = str(e)
            task["status"] = "FAILED"
            task["error_message"] = error_msg
            task["completed_at"] = datetime.now().isoformat()
            db_update_task(self.task_manager.conn, tid,
                           status="FAILED", error_message=error_msg,
                           completed_at=task["completed_at"])
            self._log("error", f"确认入库失败: {task.get('source_filename', '')} - {e}", task)
            return False

    def reclassify_task(self, task_id: str, new_dimensions: dict) -> dict:
        task = self.task_manager.get_task(task_id)
        if not task:
            raise PipelineError(f"任务不存在: {task_id}")
        tid = task_id

        current_dims = task.get("scrape_dimensions", {})
        if isinstance(current_dims, str):
            current_dims = {}
        current_dims.update(new_dimensions)
        task["scrape_dimensions"] = current_dims

        scrape_result = task.get("scrape_result", {})
        if isinstance(scrape_result, dict):
            scrape_result["dimensions"] = current_dims

        db_update_task(
            self.task_manager.conn, tid,
            scrape_dimensions=current_dims,
            classify_result="",
        )

        path_rules = self.config.get("path_rules", [])
        import_path = classify(scrape_result, path_rules)
        if not import_path:
            dims_str = ', '.join(f'{k}={v}' for k, v in current_dims.items())
            raise PipelineError(f"重新分类失败，维度=[{dims_str}]")

        if not os.path.isabs(import_path):
            project_root = os.path.dirname(
                os.path.dirname(os.path.abspath(
                    self.config.get('_config_path', '')
                ))
            )
            if project_root:
                import_path = os.path.join(project_root, import_path)

        task["import_path"] = import_path
        task["classify_result"] = import_path
        task["status"] = "CONFIRMING"
        db_update_task(self.task_manager.conn, tid,
                       import_path=import_path,
                       classify_result=import_path,
                       status="CONFIRMING")
        self._log("info", f"任务重新分类完成: {import_path}", task, "classify")
        return task

    def rollback_task(self, task_id: str, source_dir: str) -> dict:
        task = self.task_manager.get_task(task_id)
        if not task:
            raise PipelineError(f"任务不存在: {task_id}")
        tid = task_id

        source_path = task.get("source_path", "")
        source_filename = task.get("source_filename", "")
        source_filename_orig = task.get("final_filename") or source_filename

        temp_dir = self.config.get("temp_dir", "")
        temp_video = task.get("video_path", "")
        if temp_dir and temp_video.startswith(temp_dir):
            restored = False
            dest_path = os.path.join(source_dir, source_filename_orig)
            os.makedirs(source_dir, exist_ok=True)
            if os.path.exists(temp_video):
                shutil.move(temp_video, dest_path)
                restored = True
            subs = task.get("subtitle_files", [])
            for sub in subs:
                if sub.startswith(temp_dir) and os.path.exists(sub):
                    sub_dest = os.path.join(source_dir, os.path.basename(sub))
                    shutil.move(sub, sub_dest)
            if restored:
                self._log("info", f"已回退文件到源目录: {dest_path}", task, "rollback")

        db_update_task(self.task_manager.conn, tid,
                       status="ROLLBACK",
                       error_message="用户回退到源目录")
        db_update_subs(self.task_manager.conn, tid, status="ROLLBACK")
        self._log("info", f"任务已回退: {source_filename}", task, "rollback")
        return self.task_manager.get_task(tid)

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
        delete_after_process = self.config.get('source_file_handling', {}).get('delete_after_process', True)

        if delete_after_process and source_dir:
            video_exts = [ext.lower() for ext in self.config.get('video_extensions', [])]
            sub_exts = [ext.lower() for ext in self.config.get('subtitle_extensions', [])]
            deleted_files, deleted_dirs = cleanup_source_non_media(source_dir, video_exts, sub_exts)
            if deleted_files > 0 or deleted_dirs > 0:
                self._log("info", f"源目录预清理: 删除 {deleted_files} 个非媒体文件, {deleted_dirs} 个空目录")

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

    def _step_copy(self, task: dict):
        self._update_progress(task, 2, "copy", 20)
        video_path = task.get("video_path", task.get("source_path", ""))
        subtitle_files = task.get("subtitle_files", [])
        self._log("info", f"复制文件: {task.get('source_filename', '')}", task, "copy")

        def progress_cb(copied, total):
            pct = int(20 + (copied / total) * 10) if total > 0 else 25
            self._update_progress(task, 2, "copy", pct,
                                  bytes_copied=copied, total_bytes=total)

        def heartbeat_cb():
            self.task_manager.update_task(task)

        try:
            copied = self.copier.copy_to_temp(
                video_path, subtitle_files,
                progress_cb, heartbeat_cb, heartbeat_interval=30
            )
            task["video_path"] = copied[0]
            task["subtitle_files"] = copied[1:] if len(copied) > 1 else []
        except IOError as e:
            raise PipelineError(f"复制失败: {e}")

        self._update_progress(task, 2, "copy", 30)

    def _step_scrape(self, task: dict):
        self._update_progress(task, 3, "scrape", 35)
        self._log("info", f"刮削元数据: {task.get('source_filename', '')}", task, "scrape")

        try:
            result = self.scraper.scrape(
                task.get("source_filename", ""),
                task.get("subtitle_files", [])
            )
            task["scrape_result"] = result
            if self.metrics:
                self.metrics.record_llm_call(success=True)

            media_type = result.get('type', '')
            if media_type and media_type.lower() in ('tv', 'series'):
                series_dims = self._get_series_dimensions(task, result)
                if series_dims:
                    original_dims = dict(result.get('dimensions', {}))
                    result['dimensions'].update(series_dims)
                    task["scrape_result"] = result
                    changed = {k: f'{original_dims.get(k)} -> {v}'
                               for k, v in series_dims.items()
                               if original_dims.get(k) != v}
                    if changed:
                        changed_str = ', '.join(f'{k}={v}' for k, v in changed.items())
                        self._log("info", f"整剧维度覆盖: [{changed_str}]", task, "scrape")

            scrape_dimensions = result.get("dimensions", {})
            task["scrape_dimensions"] = scrape_dimensions
            task["scrape_title_cn"] = result.get('title_cn', '')
            task["scrape_title_en"] = result.get('title_en', '')
            task["scrape_year"] = result.get('year', '')
            task["scrape_media_type"] = media_type
            task["scrape_season"] = result.get('season', None)
            task["scrape_episode"] = result.get('episode', None)
            task["scrape_confidence"] = result.get('confidence', 0)

            db_update_task(
                self.task_manager.conn, task.get("task_id", ""),
                scrape_result=result,
                scrape_dimensions=scrape_dimensions,
                scrape_title_cn=result.get('title_cn', ''),
                scrape_title_en=result.get('title_en', ''),
                scrape_year=result.get('year', ''),
                scrape_media_type=media_type,
                scrape_season=result.get('season', None),
                scrape_episode=result.get('episode', None),
                scrape_confidence=result.get('confidence', 0),
            )

            detail_parts = []
            if result.get('title_cn'):
                detail_parts.append(f"标题={result['title_cn']}")
            if result.get('title_en'):
                detail_parts.append(f"英文名={result['title_en']}")
            if result.get('year'):
                detail_parts.append(f"年份={result['year']}")
            if media_type:
                detail_parts.append(f"类型={media_type}")
            if result.get('season'):
                detail_parts.append(f"季={result['season']}")
            if result.get('episode'):
                detail_parts.append(f"集={result['episode']}")
            detail_parts.append(f"置信度={result.get('confidence', 0)}")
            dims_str = ', '.join(f'{k}={v}' for k, v in scrape_dimensions.items())
            if dims_str:
                detail_parts.append(f"维度=[{dims_str}]")
            self._log("info", f"刮削结果: {', '.join(detail_parts)}", task, "scrape")

        except LLMScrapeError as e:
            if self.metrics:
                self.metrics.record_llm_call(success=False)
            raise PipelineError(f"刮削失败: {e}")

        self._update_progress(task, 3, "scrape", 50)

    def _step_validate(self, task: dict):
        self._update_progress(task, 4, "validate", 52)
        self._log("info", f"验证刮削结果: {task.get('source_filename', '')}", task, "validate")

        scraped = task.get("scrape_result", {})
        if not scraped:
            raise PipelineError("刮削结果为空，无法验证")
        missing_fields = []
        warnings = []

        title_cn = scraped.get('title_cn')
        title_en = scraped.get('title_en')
        year = scraped.get('year')
        media_type = scraped.get('type')
        confidence = scraped.get('confidence', 0)

        has_title = bool(title_cn or title_en)
        has_type = bool(media_type)
        has_year = bool(year)

        if not has_title:
            missing_fields.append("中文名(title_cn)和英文名(title_en)都缺失")
        if not has_type:
            missing_fields.append("媒体类型(type)缺失")
        if not has_year:
            if has_title and has_type:
                warnings.append(f"年份缺失(可接受，标题已识别: {title_cn or title_en})")
            else:
                missing_fields.append("年份(year)缺失")
        if title_cn and not title_en:
            warnings.append("缺少英文名(可接受)")
        if year:
            try:
                y = int(year)
                if y < 1900 or y > 2030:
                    warnings.append(f"年份异常: {year}")
                    missing_fields.append(f"年份异常: {year}")
            except ValueError:
                warnings.append(f"年份格式异常: {year}")
        if scraped.get('low_confidence'):
            if has_title and confidence >= 0.5:
                warnings.append(f"AI置信度偏低({confidence})，但标题已识别，继续处理")
            else:
                missing_fields.append("AI置信度过低")

        if missing_fields:
            error_msg = f"刮削信息不足，需要人工干预。缺失字段: {'; '.join(missing_fields)}"
            if warnings:
                error_msg += f"。警告: {'; '.join(warnings)}"
            raise PipelineError(error_msg)

        if warnings:
            self._log("warn", f"刮削警告: {'; '.join(warnings)}", task, "validate")
        self._update_progress(task, 4, "validate", 55)

    def _step_classify(self, task: dict):
        self._update_progress(task, 5, "classify", 56)
        self._log("info", f"分类匹配: {task.get('source_filename', '')}", task, "classify")

        path_rules = self.config.get('path_rules', [])
        dimensions = task.get("scrape_dimensions", {})
        dims_str = ', '.join(f'{k}={v}' for k, v in dimensions.items()) if dimensions else '无'
        self._log("info", f"文件维度: [{dims_str}]", task, "classify")

        scraped = task.get("scrape_result", {})
        import_path = classify(scraped, path_rules)
        if not import_path:
            rules_desc = []
            for i, rule in enumerate(path_rules):
                cond = rule.get('conditions', {})
                cond_str = ', '.join(f'{k}={v}' for k, v in cond.items())
                rules_desc.append(f"规则{i+1}: [{cond_str}]")
            self._log("error",
                      f"无匹配规则。文件维度=[{dims_str}], "
                      f"可用规则: {'; '.join(rules_desc) if rules_desc else '无规则配置'}",
                      task, "classify")
            raise PipelineError(f"分类匹配失败，无匹配规则。维度=[{dims_str}]")

        self._log("info", f"匹配路径: {import_path}", task, "classify")

        if not os.path.isabs(import_path):
            project_root = os.path.dirname(
                os.path.dirname(os.path.abspath(
                    self.config.get('_config_path', '')
                ))
            )
            if project_root:
                import_path = os.path.join(project_root, import_path)

        task["import_path"] = import_path
        task["classify_result"] = import_path
        db_update_task(self.task_manager.conn, task.get("task_id", ""),
                       import_path=import_path, classify_result=import_path)
        self._update_progress(task, 5, "classify", 60)

    def _get_series_dimensions(self, task: dict, scrape_result: dict) -> dict:
        cached_dims = self._find_cached_series_dims(task, scrape_result)
        if cached_dims is not None:
            return cached_dims
        series_name = _extract_series_name(task.get("source_filename", ""))
        if not series_name:
            return {}
        title_from_scrape = scrape_result.get('title_cn', '') or scrape_result.get('title_en', '')
        query_name = title_from_scrape if title_from_scrape else series_name
        self._log("info", f"按剧名整体刮削维度: {query_name}", task, "scrape")
        try:
            series_result = self.scraper.scrape_series(query_name)
            if self.metrics:
                self.metrics.record_llm_call(success=True)
            series_dims = series_result.get('dimensions', {})
            if series_dims:
                self._log("info",
                          f"整剧维度结果: [{', '.join(f'{k}={v}' for k, v in series_dims.items())}]",
                          task, "scrape")
                return series_dims
        except LLMScrapeError as e:
            self._log("warn", f"整剧维度刮削失败，使用逐集结果: {e}", task, "scrape")
            if self.metrics:
                self.metrics.record_llm_call(success=False)
        return {}

    def _find_cached_series_dims(self, task: dict, scrape_result: dict) -> dict:
        title = scrape_result.get('title_cn', '') or scrape_result.get('title_en', '')
        if not title:
            return None
        try:
            tasks = db_list_all_tasks(self.task_manager.conn, limit=500)
        except Exception:
            return None
        tid = task.get("task_id", "")
        for t in tasks:
            if t.get("task_id") == tid:
                continue
            if t.get("status") not in ('SUCCESS',):
                continue
            t_result = t.get("scrape_result", {})
            if isinstance(t_result, str):
                continue
            t_dims = t_result.get('dimensions', {}) if isinstance(t_result, dict) else {}
            if t_dims.get('media_type') not in ('tv', 'TV', 'series'):
                continue
            t_title = t_result.get('title_cn', '') or t_result.get('title_en', '')
            if t_title and t_title == title:
                self._log("info", f"复用同剧缓存维度: {title}", task, "scrape")
                return t_dims
        return None

    def _get_import_roots(self) -> list:
        path_rules = self.config.get('path_rules', [])
        templates = [r.get('template', '') for r in path_rules if r.get('template')]
        if not templates:
            return []
        roots = []
        for tpl in templates:
            if not os.path.isabs(tpl):
                project_root = os.path.dirname(
                    os.path.dirname(os.path.abspath(
                        self.config.get('_config_path', '')
                    ))
                )
                if project_root:
                    tpl = os.path.join(project_root, tpl)
            tpl = os.path.normpath(tpl)
            parts = tpl.split(os.sep)
            for i, p in enumerate(parts):
                if p.startswith('{'):
                    if i > 0:
                        roots.append(os.sep.join(parts[:i]))
                    break
            else:
                roots.append(tpl)
        return roots

    def _step_dedup(self, task: dict):
        self._update_progress(task, 6, "dedup", 65)
        dedup_cfg = self.config.get('duplicate_handling', {}) or {}
        enabled = dedup_cfg.get('enabled', True)
        if not enabled:
            self._log("info", f"智能同名检测已关闭，跳过跨目录扫描: {task.get('source_filename', '')}", task, "dedup")
            return
        self._log("info", f"同名检测: {task.get('source_filename', '')}", task, "dedup")
        strategy = dedup_cfg.get('strategy', 'skip')
        import_roots = self._get_import_roots()
        dedup_result = {'is_duplicate': False}
        scraped = task.get("scrape_result", {})
        video_path = task.get("video_path", "")
        for search_dir in import_roots:
            if not os.path.isdir(search_dir):
                continue
            result = check_duplicate(search_dir, scraped, strategy, video_path)
            if result['is_duplicate']:
                dedup_result = result
                break
        if dedup_result['is_duplicate']:
            if strategy == 'skip':
                skip_msg = dedup_result.get('skip_message',
                    f"同名文件已存在: {dedup_result.get('existing_file', 'unknown')}")
                raise PipelineSkipError(skip_msg)
            elif strategy == 'rename':
                task["final_filename"] = os.path.basename(
                    dedup_result['suggested_filename']
                )
            elif strategy == 'replace':
                self._log("info", f"替换模式: 将删除已存在文件 {dedup_result['existing_file']}", task, "dedup")
                if os.path.exists(dedup_result['existing_path']):
                    from safety import safe_delete
                    allowed_dirs = [task.get("import_path", "")]
                    ok, msg = safe_delete(dedup_result['existing_path'], allowed_base_dirs=allowed_dirs)
                    if ok:
                        self._log("info", f"已删除已存在文件: {dedup_result['existing_file']}", task, "dedup")
                    else:
                        self._log("warning", f"删除文件失败: {msg}", task, "dedup")
                        raise PipelineError(f"无法删除已存在文件: {msg}")
            elif strategy == 'quality':
                quality_decision = dedup_result.get('quality_decision')
                if quality_decision == 'replace':
                    self._log("info", f"质量优先: 新文件质量更高，将替换已存在文件", task, "dedup")
                    if os.path.exists(dedup_result['existing_path']):
                        from safety import safe_delete
                        allowed_dirs = [task.get("import_path", "")]
                        ok, msg = safe_delete(dedup_result['existing_path'], allowed_base_dirs=allowed_dirs)
                        if ok:
                            self._log("info", f"已删除已存在文件: {dedup_result['existing_file']}", task, "dedup")
                        else:
                            self._log("warning", f"删除文件失败: {msg}", task, "dedup")
                            raise PipelineError(f"无法删除已存在文件: {msg}")
                elif quality_decision == 'keep_existing':
                    skip_msg = dedup_result.get('skip_message', "质量优先: 保留已存在文件")
                    raise PipelineSkipError(skip_msg)

        task["dedup_result"] = dedup_result
        if dedup_result.get('existing_file'):
            task["dedup_existing_file"] = dedup_result['existing_file']
        db_update_task(
            self.task_manager.conn, task.get("task_id", ""),
            dedup_result=task.get("dedup_result", {}),
            dedup_existing_file=task.get("dedup_existing_file", ""),
        )
        self._update_progress(task, 6, "dedup", 70)

    def _step_rename(self, task: dict):
        self._update_progress(task, 7, "rename", 72)
        self._log("info", f"生成文件名: {task.get('source_filename', '')}", task, "rename")

        if not task.get("final_filename"):
            templates = self.config.get('filename_templates', {})
            video_ext = os.path.splitext(task.get("video_path", ""))[1]
            scraped = task.get("scrape_result", {})
            if scraped.get('type') == 'tv':
                template = templates.get('tv', '')
            else:
                template = templates.get('movie', '')
            task["final_filename"] = apply_filename_template(
                scraped, template, video_ext
            )
        self._update_progress(task, 7, "rename", 75)

    def _get_allowed_dirs(self) -> list:
        allowed_dirs = [
            self.config.get('source_dir', ''),
            self.config.get('temp_dir', ''),
        ]
        for r in self.config.get('path_rules', []):
            tpl = r.get('template', '')
            if tpl:
                parts = tpl.split('/')
                for i, p in enumerate(parts):
                    if p.startswith('{'):
                        allowed_dirs.append('/'.join(parts[:i]))
                        break
                else:
                    allowed_dirs.append(tpl.rstrip('/'))
        return allowed_dirs

    def _step_import(self, task: dict, original_source_video: str,
                     original_source_subs: list):
        self._update_progress(task, 8, "import", 80)
        self._log("info", f"入库: {task.get('source_filename', '')}", task, "import")

        templates = self.config.get('filename_templates', {})
        allowed_dirs = self._get_allowed_dirs()
        temp_video_path = task.get("video_path", "")

        move_result = move_to_import(
            temp_video_path,
            task.get("subtitle_files", []),
            task.get("import_path", ""),
            task.get("scrape_result", {}),
            templates,
            allowed_base_dirs=allowed_dirs,
        )

        task["video_path"] = move_result.get('video', temp_video_path)
        task["subtitle_files"] = move_result.get('subtitles', [])

        source_dir = self.config.get('source_dir', '')
        delete_after_process = self.config.get('source_file_handling', {}).get('delete_after_process', True)

        if delete_after_process and source_dir and original_source_video:
            video_exts = [ext.lower() for ext in self.config.get('video_extensions', [])]
            sub_exts = [ext.lower() for ext in self.config.get('subtitle_extensions', [])]
            companion_count = delete_source_with_companions(
                original_source_video, original_source_subs,
                video_exts, sub_exts, allowed_base_dirs=allowed_dirs
            )
            remove_empty_parent_dir(original_source_video, source_dir)
            msg = f"已清理源目录文件: {os.path.basename(original_source_video)}"
            if companion_count > 0:
                msg += f" (含 {companion_count} 个附属文件)"
            self._log("info", msg, task, "import")
        elif not delete_after_process and source_dir and original_source_video:
            self._log("info", f"保留源目录文件（配置为不删除）: {os.path.basename(original_source_video)}", task, "import")

        temp_dir = self.config.get('temp_dir', '')
        if temp_video_path and temp_dir and str(temp_video_path).startswith(temp_dir):
            delete_source_files([temp_video_path], allowed_base_dirs=allowed_dirs)
            self._log("info", f"已清理临时文件: {os.path.basename(temp_video_path)}", task, "import")

        self._update_progress(task, 8, "import", 90)

    def _step_import_from_confirm(self, task: dict, original_source_video: str,
                                   original_source_subs: list):
        self._update_progress(task, 8, "import", 80)
        tid = task.get("task_id", "")
        self._log("info", f"确认入库: {task.get('source_filename', '')}", task, "import")

        manual_review = self.config.get("manual_review", {})
        temp_dir = self.config.get("temp_dir", "")
        temp_video_path = task.get("video_path", "")

        if manual_review.get("enabled", False):
            for ext in (".temp", ".tmp"):
                if temp_video_path.endswith(ext):
                    new_path = temp_video_path[:-len(ext)]
                    if os.path.exists(temp_video_path):
                        os.rename(temp_video_path, new_path)
                        task["video_path"] = new_path
                        temp_video_path = new_path
                    break

        self._step_dedup(task)
        self._step_rename(task)

        templates = self.config.get('filename_templates', {})
        allowed_dirs = self._get_allowed_dirs()

        move_result = move_to_import(
            temp_video_path,
            task.get("subtitle_files", []),
            task.get("import_path", ""),
            task.get("scrape_result", {}),
            templates,
            allowed_base_dirs=allowed_dirs,
        )

        task["video_path"] = move_result.get('video', temp_video_path)
        task["subtitle_files"] = move_result.get('subtitles', [])
        task["import_video_path"] = move_result.get('video', "")

        source_dir = self.config.get('source_dir', '')
        delete_after_process = self.config.get('source_file_handling', {}).get('delete_after_process', True)
        if delete_after_process and source_dir and original_source_video:
            video_exts = [ext.lower() for ext in self.config.get('video_extensions', [])]
            sub_exts = [ext.lower() for ext in self.config.get('subtitle_extensions', [])]
            delete_source_with_companions(
                original_source_video, original_source_subs,
                video_exts, sub_exts, allowed_base_dirs=allowed_dirs
            )
            remove_empty_parent_dir(original_source_video, source_dir)

        if temp_dir and temp_video_path:
            delete_source_files([temp_video_path], allowed_base_dirs=allowed_dirs)

        db_update_task(self.task_manager.conn, tid,
                       import_video_path=task.get("import_video_path", ""),
                       import_success=1)

        db_update_subs(self.task_manager.conn, tid,
                       status="SUCCESS", confirm_status="CONFIRMED",
                       completed_at=datetime.now().isoformat())

        self._update_progress(task, 8, "import", 90)

    def _step_notify(self, task: dict):
        self._update_progress(task, 9, "notify", 95)

    def _step_record(self, task: dict):
        self._update_progress(task, 10, "record", 100)
        self.task_manager.update_task(task)


class PipelineError(Exception):
    pass


class PipelineSkipError(Exception):
    pass