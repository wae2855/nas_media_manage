#!/usr/bin/env python3
import os
import time
from task_manager import Task, TaskManager
from file_scanner import scan_source_dir
from file_copier import FileCopier
from llm_scraper import LLMScraper, LLMScrapeError
from classifier import classify
from dedup_checker import check_duplicate
from file_mover import apply_filename_template, move_to_import, delete_source_files
from hooks import HookRunner


PIPELINE_STEPS = [
    (1, "scan", "扫描源目录"),
    (2, "copy", "复制到临时目录"),
    (3, "scrape", "AI刮削元数据"),
    (4, "classify", "分类匹配路径"),
    (5, "dedup", "同名文件检测"),
    (6, "rename", "生成目标文件名"),
    (7, "import", "入库移动文件"),
    (8, "notify", "发送通知"),
    (9, "record", "记录处理结果")
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
        self._paused = False

        self.scraper = LLMScraper(config)
        self.copier = FileCopier(config.get('temp_dir', ''))

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def is_paused(self) -> bool:
        return self._paused

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
        try:
            task.transition_to("PROCESSING")
            self.task_manager.update_task(task)
        except ValueError as e:
            self._log("error", f"任务状态转换失败: {e}", task)
            return False

        try:
            self.hooks.run_before_process(task.to_dict())
            self._step_copy(task)
            self._step_scrape(task)
            self._step_classify(task)
            self._step_dedup(task)
            self._step_rename(task)
            self._step_import(task)
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
            return True

        except Exception as e:
            task.transition_to("FAILED")
            task.error_message = str(e)
            self.task_manager.update_task(task)
            self.hooks.run_after_failure(task.to_dict())
            if self.metrics:
                self.metrics.record_task_complete("failed")
            self._log("error", f"任务失败: {task.video_file} - {e}", task)
            return False

    def run_all(self):
        self._log("info", "开始批量处理")
        while not self._paused:
            task = self.task_manager.get_next_pending()
            if task is None:
                break
            self.process_one(task)

        if self.notifier and self.notifier.should_notify("batch_complete"):
            try:
                all_tasks = self.task_manager.list_tasks(limit=10000)
                self.notifier.notify_batch_complete(all_tasks)
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

        try:
            copied = self.copier.copy_to_temp(
                task.video_path, task.subtitle_files, progress_cb
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

    def _step_classify(self, task: Task):
        self._update_progress(task, 4, "classify", 55)
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
        self._update_progress(task, 4, "classify", 60)

    def _step_dedup(self, task: Task):
        self._update_progress(task, 5, "dedup", 65)
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

        self._update_progress(task, 5, "dedup", 70)

    def _step_rename(self, task: Task):
        self._update_progress(task, 6, "rename", 72)
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

        self._update_progress(task, 6, "rename", 75)

    def _step_import(self, task: Task):
        self._update_progress(task, 7, "import", 80)
        self._log("info", f"入库: {task.video_file}", task, "import")

        templates = self.config.get('filename_templates', {})
        allowed_dirs = [
            self.config.get('source_dir', ''),
            self.config.get('temp_dir', ''),
        ]
        import_dirs = [r.get('template', '') for r in self.config.get('path_rules', [])]
        allowed_dirs.extend(import_dirs)

        move_result = move_to_import(
            task.video_path, task.subtitle_files,
            task.import_path, task.scraped_info, templates,
            allowed_base_dirs=allowed_dirs
        )

        task.video_path = move_result['video']
        task.subtitle_files = move_result['subtitles']

        source_dir = self.config.get('source_dir', '')
        if source_dir:
            original_video = os.path.join(source_dir, task.video_file)
            original_subs = [
                os.path.join(source_dir, os.path.basename(s))
                for s in task.subtitle_files
            ]
            delete_source_files([original_video] + original_subs,
                                allowed_base_dirs=allowed_dirs)

        self._update_progress(task, 7, "import", 90)

    def _step_notify(self, task: Task):
        self._update_progress(task, 8, "notify", 95)
        if task.status == "SUCCESS":
            self._notify("task_complete", task)
        elif task.status == "FAILED":
            self._notify("task_failed", task)
        elif task.status == "SKIPPED":
            self._notify("task_skipped", task)

    def _step_record(self, task: Task):
        self._update_progress(task, 9, "record", 100)
        task.add_log("record", "INFO", f"处理完成: {task.final_filename}")
        self.task_manager.update_task(task)


class PipelineError(Exception):
    pass


class PipelineSkipError(Exception):
    pass
