import os
from media_importer.core.db import (
    update_task as db_update_task,
    get_subtitles_by_task as db_get_subtitles,
    update_subtitle as db_update_subtitle,
)
from media_importer.domains.import_flow.services import (
    ClassificationService,
    DedupService,
    ImportService,
)
from media_importer.domains.import_flow.services.paths import (
    allowed_dirs_from_config,
    import_roots_from_config,
)
from media_importer.storage.file_mover import apply_filename_template
from media_importer.domains.import_flow.utils import PipelineError, PipelineSkipError


class FileStepsMixin:
    def _step_copy(self, task: dict):
        self._update_progress(task, 2, "copy", 20)
        file_location = task.get("file_location", "source")
        if file_location in ("source", "recycle"):
            video_path = task.get("source_path", "")
        else:
            video_path = task.get("video_path") or task.get("source_path", "")
        subtitle_files = task.get("subtitle_files", [])
        self._log("info", f"复制文件: {task.get('source_filename', '')} (从{file_location})", task, "copy")

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
            tid = task.get("task_id", "")
            if tid:
                sub_target_paths = copied[1:] if len(copied) > 1 else []
                subs = db_get_subtitles(self.task_manager.conn, tid)
                for i, sub in enumerate(subs):
                    if i < len(sub_target_paths):
                        db_update_subtitle(self.task_manager.conn, sub["id"],
                                           target_path=sub_target_paths[i])
        except IOError as e:
            raise PipelineError(f"复制失败: {e}")

        self._update_progress(task, 2, "copy", 30)

    def _step_classify(self, task: dict):
        self._update_progress(task, 5, "classify", 56)
        self._log("info", f"分类匹配: {task.get('source_filename', '')}", task, "classify")

        result = ClassificationService(self.config).classify_task(task)
        self._log("info", f"文件维度: [{result.dimensions_text}]", task, "classify")
        if not result.import_path:
            self._log("error",
                      f"无匹配规则。文件维度=[{result.dimensions_text}], "
                      f"可用规则: {result.rules_description}",
                      task, "classify")
            raise PipelineError(f"分类匹配失败，无匹配规则。维度=[{result.dimensions_text}]")
        if result.used_fallback:
            self._log("info", f"无匹配规则，使用兜底目录: {result.import_path}", task, "classify")
        self._log("info", f"匹配路径: {result.import_path}", task, "classify")

        task["import_path"] = result.import_path
        task["classify_result"] = result.classify_result
        db_update_task(self.task_manager.conn, task.get("task_id", ""),
                       import_path=result.import_path,
                       classify_result=result.classify_result)
        self._update_progress(task, 5, "classify", 60)

    def _get_import_roots(self) -> list:
        return import_roots_from_config(self.config)

    def _step_dedup(self, task: dict):
        self._update_progress(task, 6, "dedup", 65)
        self._log("info", f"同名检测: {task.get('source_filename', '')}", task, "dedup")
        try:
            decision = DedupService(self.config).check_task(task)
        except OSError as e:
            self._log("warning", f"移入回收站失败: {e}", task, "dedup")
            raise PipelineError(f"无法移入回收站: {e}")

        if decision.message:
            self._log("info", decision.message, task, "dedup")
        if decision.action == "skip":
            raise PipelineSkipError(decision.message)
        if decision.action == "rename":
            task["final_filename"] = decision.final_filename
        if decision.action == "replace":
            existing_file = decision.result.get("existing_file", "")
            if existing_file:
                self._log("info", f"已移入回收站: {existing_file}", task, "dedup")

        task["dedup_result"] = decision.result
        if decision.result.get('existing_file'):
            task["dedup_existing_file"] = decision.result['existing_file']
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
        return allowed_dirs_from_config(self.config)

    def _step_import(self, task: dict, original_source_video: str,
                     original_source_subs: list):
        self._update_progress(task, 8, "import", 80)
        self._log("info", f"入库: {task.get('source_filename', '')}", task, "import")

        result = ImportService(self.config, self.task_manager.conn).import_task(
            task,
            original_source_video,
            original_source_subs,
            overwrite=False,
        )
        if result.source_cleanup.message:
            self._log("info", result.source_cleanup.message, task, "import")
        if result.temp_cleanup.message:
            self._log("info", result.temp_cleanup.message, task, "import")

        tid = task.get("task_id", "")
        db_update_task(self.task_manager.conn, tid,
                       import_video_path=task.get("import_video_path", ""),
                       import_success=1)

        self._update_progress(task, 8, "import", 90)

    def _step_import_from_confirm(self, task: dict, original_source_video: str,
                                   original_source_subs: list):
        self._update_progress(task, 8, "import", 80)
        tid = task.get("task_id", "")
        self._log("info", f"确认入库: {task.get('source_filename', '')}", task, "import")

        import_service = ImportService(self.config, self.task_manager.conn)
        import_service.restore_confirm_temp_name(task)
        self._step_dedup(task)
        self._step_rename(task)

        result = import_service.import_task(
            task,
            original_source_video,
            original_source_subs,
        )
        if result.source_cleanup.message:
            self._log("info", result.source_cleanup.message, task, "import")
        if result.temp_cleanup.message:
            self._log("info", result.temp_cleanup.message, task, "import")

        db_update_task(self.task_manager.conn, tid,
                       import_video_path=task.get("import_video_path", ""),
                       import_success=1)

        self._update_progress(task, 8, "import", 90)

    def _step_notify(self, task: dict):
        self._update_progress(task, 9, "notify", 95)

    def _step_record(self, task: dict):
        self._update_progress(task, 10, "record", 100)
        self.task_manager.update_task(task)
