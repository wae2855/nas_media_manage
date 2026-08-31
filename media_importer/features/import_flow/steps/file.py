import os

from media_importer.features.import_flow.services import (
    ClassificationService,
    DedupService,
    ImportService,
)
from media_importer.features.import_flow.services.naming import apply_filename_template
from media_importer.features.import_flow.services.paths import (
    allowed_dirs_from_config,
    import_roots_from_config,
)
from media_importer.features.import_flow.utils import PipelineError
from media_importer.infrastructure.db import (
    get_subtitles_by_task as db_get_subtitles,
)
from media_importer.infrastructure.db import (
    update_subtitle as db_update_subtitle,
)
from media_importer.infrastructure.db import (
    update_task as db_update_task,
)


class FileStepsMixin:
    def _step_copy(self, task: dict):
        self._update_progress(task, 2, "copy", 20)
        file_location = task.get("file_location", "source")

        # S2 断点续跑：retry 保留的 temp checkpoint 有效则跳过复制
        if file_location == "temp":
            checkpoint = task.get("video_path", "")
            if checkpoint and os.path.exists(checkpoint):
                self._log("info",
                          f"断点续跑: temp 已存在，跳过复制 ({checkpoint})",
                          task, "copy")
                self._update_progress(task, 2, "copy", 30)
                return
            # checkpoint 失效（temp 被外部清理）→ 降级从头复制
            self._log("warn",
                      f"断点续跑失效: temp 不存在，重新复制 ({checkpoint})",
                      task, "copy")
            task["file_location"] = "source"

        if file_location in ("source", "recycle"):
            video_path = task.get("source_path", "")
            # 从源复制时优先用原始字幕源路径：上次复制遗留的 temp 路径可能已被失败清理
            subtitle_files = task.get("subtitle_source_files") or task.get("subtitle_files", [])
        else:
            video_path = task.get("video_path") or task.get("source_path", "")
            subtitle_files = task.get("subtitle_files", [])
        # 防御：字幕文件不存在时跳过（缺失字幕不应阻断视频入库）
        missing_subs = [sf for sf in subtitle_files if not os.path.exists(sf)]
        if missing_subs:
            for sf in missing_subs:
                self._log("warn", f"字幕文件不存在，跳过: {sf}", task, "copy")
            subtitle_files = [sf for sf in subtitle_files if os.path.exists(sf)]
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
            raise PipelineError(f"复制失败: {e}") from e

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
        decision = DedupService(self.config).check_task(task)

        if decision.message:
            self._log("info", decision.message, task, "dedup")
        task["dedup_result"] = decision.result
        if decision.result.get('existing_file'):
            task["dedup_existing_file"] = decision.result['existing_file']
        db_update_task(
            self.task_manager.conn, task.get("task_id", ""),
            dedup_result=task.get("dedup_result", {}),
            dedup_existing_file=task.get("dedup_existing_file", ""),
        )
        self._update_progress(task, 6, "dedup", 70)
        if decision.action == "review":
            from media_importer.features.import_flow.utils import PipelineReviewRequired
            raise PipelineReviewRequired(decision.message, decision.result)

    def _step_rename(self, task: dict):
        self._update_progress(task, 7, "rename", 72)
        self._log("info", f"生成文件名: {task.get('source_filename', '')}", task, "rename")

        if not task.get("final_filename"):
            templates = self.config.get('filename_templates', {})
            video_ext = os.path.splitext(task.get("video_path", ""))[1]
            scraped = task.get("scrape_result", {})
            if scraped.get('media_type') == 'tv':
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
        self._step_rename(task)

        conflict = task.get("dedup_result") or {}
        action = str(conflict.get("resolved_action") or "")
        if not action:
            self._step_dedup(task)

        result = import_service.import_task(
            task,
            original_source_video,
            original_source_subs,
            overwrite=action == "replace_existing",
            conflict_snapshot=conflict if action == "replace_existing" else None,
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
