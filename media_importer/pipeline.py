#!/usr/bin/env python3
import os
import threading
from task_manager import Task, TaskManager
from file_scanner import scan_source_dir
from file_copier import FileCopier
from llm_scraper import LLMScraper, LLMScrapeError
from classifier import classify
from dedup_checker import check_duplicate
from file_mover import apply_filename_template, move_to_import, delete_source_files, remove_empty_parent_dir
from hooks import HookRunner


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
    (10, "record", "记录处理结果")
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

    def pause(self):
        self._paused.set()

    def resume(self):
        self._paused.clear()

    def is_paused(self) -> bool:
        return self._paused.is_set()

    def _log(self, level: str, message: str, task: Task = None, step: str = ""):
        if self.logger:
            if task:
                self.logger.step_log(task.task_id, step, level, message)
            else:
                log_method = getattr(self.logger, level.lower(), self.logger.info)
                log_method(message)

    def _update_progress(self, task: Task, step_num: int, step_name: str,
                         percentage: int, **kwargs):
        self.task_manager.update_progress(
            task, step_num, step_name, percentage, **kwargs
        )

    def _notify(self, event_type: str, task: Task):
        if self.notifier and self.notifier.should_notify(event_type):
            try:
                self.notifier.notify(event_type, task)
            except Exception as e:
                self._log("warn", f"通知发送失败: {e}", task, "notify")

    def scan_and_create_tasks(self) -> list:
        source_dir = self.config.get('source_dir', '')
        groups = scan_source_dir(source_dir, self.config)

        tasks = []
        for group in groups:
            video_path = group['video']
            video_file = os.path.basename(video_path)
            subtitle_files = group.get('subtitles', [])
            file_size_mb = 0
            try:
                file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            except OSError:
                pass

            task = self.task_manager.create_task(
                video_path=video_path,
                video_file=video_file,
                subtitle_files=subtitle_files,
                file_size_mb=file_size_mb
            )
            tasks.append(task)

        self._log("info", f"扫描完成，创建 {len(tasks)} 个任务")
        return tasks

    def process_one(self, task: Task) -> bool:
        original_source_video = task.video_path
        original_source_subs = list(task.subtitle_files)
        temp_video_path_for_cleanup = None
        
        try:
            task.transition_to("PROCESSING")
            self.task_manager.update_task(task)
        except ValueError as e:
            self._log("error", f"任务状态转换失败: {e}", task)
            return False

        try:
            self.hooks.run_before_process(task.to_dict())
            self._step_copy(task)
            temp_video_path_for_cleanup = task.video_path
            self._step_scrape(task)
            self._step_validate(task)
            self._step_classify(task)
            self._step_dedup(task)
            self._step_rename(task)
            self._step_import(task, original_source_video, original_source_subs)
            self._step_notify(task)
            self._step_record(task)

            task.transition_to("SUCCESS")
            self.task_manager.update_task(task)
            self.hooks.run_after_success(task.to_dict())
            if self.metrics:
                self.metrics.record_task_complete("success")
            self._log("info", f"任务处理成功: {task.video_file}", task)
            return True

        except PipelineSkipError as e:
            task.transition_to("SKIPPED")
            task.error_message = str(e)
            self.task_manager.update_task(task)
            if self.metrics:
                self.metrics.record_task_complete("skipped")
            self._log("info", f"任务跳过: {task.video_file} - {e}", task)
            self._cleanup_temp_on_failure(task, temp_video_path_for_cleanup)
            return True

        except Exception as e:
            task.transition_to("FAILED")
            task.error_message = str(e)
            self.task_manager.update_task(task)
            self.hooks.run_after_failure(task.to_dict())
            if self.metrics:
                self.metrics.record_task_complete("failed")
            self._log("error", f"任务失败: {task.video_file} - {e}", task)
            self._cleanup_temp_on_failure(task, temp_video_path_for_cleanup)
            return False

    def _cleanup_temp_on_failure(self, task: Task, temp_video_path: str):
        """失败时清理 temp 目录文件，保留 source 让用户查看"""
        temp_dir = self.config.get('temp_dir', '')
        source_dir = self.config.get('source_dir', '')
        allowed_dirs = [
            source_dir,
            temp_dir,
        ]
        
        files_to_delete = []
        
        if temp_video_path and temp_dir and temp_video_path.startswith(temp_dir):
            files_to_delete.append(temp_video_path)
            for sub in task.subtitle_files:
                if temp_dir in sub:
                    files_to_delete.append(sub)
        
        if files_to_delete:
            delete_source_files(files_to_delete, allowed_base_dirs=allowed_dirs)
            self._log("info", f"已清理 temp 目录失败文件: {len(files_to_delete)} 个", task, "cleanup")

    def run_all(self):
        self._log("info", "开始批量处理")
        
        source_dir = self.config.get("source_dir", "")
        pending_tasks = self.task_manager.get_next_pending()
        
        if pending_tasks is None:
            self.scan_and_create_tasks()
            all_tasks = self.task_manager.list_tasks(limit=10000)
            video_count = sum(1 for t in all_tasks if t.status == "PENDING")
            subtitle_count = sum(len(t.subtitle_files) for t in all_tasks if t.status == "PENDING")
            if video_count > 0 and self.notifier:
                self.notifier.notify_batch_start(source_dir, video_count, subtitle_count)
        else:
            all_tasks = self.task_manager.list_tasks(status="PENDING", limit=10000)
            if self.notifier:
                video_count = len(all_tasks)
                subtitle_count = sum(len(t.subtitle_files) for t in all_tasks)
                self.notifier.notify_batch_start(source_dir, video_count, subtitle_count)
        
        batch_stats = {"PROCESSING": 0, "SUCCESS": 0, "FAILED": 0, "SKIPPED": 0,
                        "total": 0, "subtitle_count": 0, "video_count": 0}
        
        while not self._paused.is_set():
            task = self.task_manager.get_next_pending()
            if task is None:
                break
            batch_stats["total"] += 1
            batch_stats["subtitle_count"] += len(task.subtitle_files)
            batch_stats["video_count"] += 1
            self.process_one(task)
            final_status = task.status
            batch_stats[final_status] = batch_stats.get(final_status, 0) + 1

        batch_stats["total_files"] = batch_stats["video_count"] + batch_stats["subtitle_count"]

        if self.notifier and self.notifier.should_notify("batch_complete"):
            try:
                self.notifier.notify_batch_complete([], summary=batch_stats)
            except Exception:
                pass

        self._log("info", "批量处理完成")

    def _step_copy(self, task: Task):
        self._update_progress(task, 2, "copy", 20)
        self._log("info", f"复制文件: {task.video_file}", task, "copy")

        def progress_cb(copied, total):
            pct = int(20 + (copied / total) * 10) if total > 0 else 25
            self._update_progress(task, 2, "copy", pct,
                                  bytes_copied=copied, total_bytes=total)

        def heartbeat_cb():
            """心跳回调：更新任务时间戳，防止超时被认为是死锁"""
            self.task_manager.update_task(task)

        try:
            copied = self.copier.copy_to_temp(
                task.video_path, task.subtitle_files, 
                progress_cb, heartbeat_cb, heartbeat_interval=30
            )
            task.video_path = copied[0]
            task.subtitle_files = copied[1:] if len(copied) > 1 else []
        except IOError as e:
            raise PipelineError(f"复制失败: {e}")

        self._update_progress(task, 2, "copy", 30)

    def _step_scrape(self, task: Task):
        self._update_progress(task, 3, "scrape", 35)
        self._log("info", f"刮削元数据: {task.video_file}", task, "scrape")

        try:
            result = self.scraper.scrape(
                task.video_file, task.subtitle_files
            )
            task.scraped_info = result
            if self.metrics:
                self.metrics.record_llm_call(success=True)
        except LLMScrapeError as e:
            if self.metrics:
                self.metrics.record_llm_call(success=False)
            raise PipelineError(f"刮削失败: {e}")

        self._update_progress(task, 3, "scrape", 50)

    def _step_validate(self, task: Task):
        self._update_progress(task, 4, "validate", 52)
        self._log("info", f"验证刮削结果: {task.video_file}", task, "validate")

        scraped = task.scraped_info
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

        if year and (int(year) < 1900 or int(year) > 2030):
            warnings.append(f"年份异常: {year}")
            missing_fields.append(f"年份异常: {year}")

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

    def _step_classify(self, task: Task):
        self._update_progress(task, 5, "classify", 56)
        self._log("info", f"分类匹配: {task.video_file}", task, "classify")

        path_rules = self.config.get('path_rules', [])
        import_path = classify(task.scraped_info, path_rules)
        if not import_path:
            raise PipelineError("分类匹配失败，无匹配规则")

        if not os.path.isabs(import_path):
            project_root = os.path.dirname(
                os.path.dirname(os.path.abspath(self.config.get('_config_path', '')))
            )
            if project_root:
                import_path = os.path.join(project_root, import_path)

        task.import_path = import_path
        self._update_progress(task, 5, "classify", 60)

    def _step_dedup(self, task: Task):
        self._update_progress(task, 6, "dedup", 65)
        self._log("info", f"同名检测: {task.video_file}", task, "dedup")

        strategy = self.config.get('duplicate_handling', {}).get('strategy', 'skip')
        dedup_result = check_duplicate(
            task.import_path, task.scraped_info, strategy
        )

        if dedup_result['is_duplicate']:
            if strategy == 'skip':
                raise PipelineSkipError(
                    f"同名文件已存在: {dedup_result['existing_file']}"
                )
            elif strategy == 'rename':
                task.final_filename = os.path.basename(
                    dedup_result['suggested_filename']
                )

        self._update_progress(task, 6, "dedup", 70)

    def _step_rename(self, task: Task):
        self._update_progress(task, 7, "rename", 72)
        self._log("info", f"生成文件名: {task.video_file}", task, "rename")

        if not task.final_filename:
            templates = self.config.get('filename_templates', {})
            video_ext = os.path.splitext(task.video_path)[1]
            if task.scraped_info.get('type') == 'tv':
                template = templates.get('tv', '')
            else:
                template = templates.get('movie', '')
            task.final_filename = apply_filename_template(
                task.scraped_info, template, video_ext
            )

        self._update_progress(task, 7, "rename", 75)

    def _step_import(self, task: Task, original_source_video: str, original_source_subs: list):
        self._update_progress(task, 8, "import", 80)
        self._log("info", f"入库: {task.video_file}", task, "import")

        templates = self.config.get('filename_templates', {})
        temp_dir = self.config.get('temp_dir', '')
        allowed_dirs = [
            self.config.get('source_dir', ''),
            temp_dir,
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

        temp_video_path = task.video_path

        move_result = move_to_import(
            task.video_path, task.subtitle_files,
            task.import_path, task.scraped_info, templates,
            allowed_base_dirs=allowed_dirs
        )

        task.video_path = move_result['video']
        task.subtitle_files = move_result['subtitles']

        source_dir = self.config.get('source_dir', '')

        if source_dir and original_source_video:
            files_to_delete = [original_source_video]
            for sub in original_source_subs:
                files_to_delete.append(sub)
            delete_source_files(files_to_delete,
                                allowed_base_dirs=allowed_dirs)
            remove_empty_parent_dir(original_source_video, source_dir)
            self._log("info", f"已清理源目录文件: {os.path.basename(original_source_video)}", task, "import")

        if temp_video_path and temp_dir and temp_video_path.startswith(temp_dir):
            delete_source_files([temp_video_path], allowed_base_dirs=allowed_dirs)
            self._log("info", f"已清理临时文件: {os.path.basename(temp_video_path)}", task, "import")

        self._update_progress(task, 8, "import", 90)

    def _step_notify(self, task: Task):
        self._update_progress(task, 9, "notify", 95)

    def _step_record(self, task: Task):
        self._update_progress(task, 10, "record", 100)
        task.add_log("record", "INFO", f"处理完成: {task.final_filename}")
        self.task_manager.update_task(task)


class PipelineError(Exception):
    pass


class PipelineSkipError(Exception):
    pass
