import os

from media_importer.features.import_flow.services import (
    ClassificationService,
    DedupService,
    ImportService,
    ReorganizationService,
    plan_subtitle_filenames,
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
    def _prepare_import_input(self, task: dict) -> None:
        """Bind the import to the original source; retries always start here."""
        task["file_location"] = "source"
        task["video_path"] = task.get("source_path", "")
        task["subtitle_files"] = (
            task.get("subtitle_source_files") or task.get("subtitle_files", [])
        )
        db_update_task(
            self.task_manager.conn,
            task.get("task_id", ""),
            file_location="source",
            video_path=task.get("video_path", ""),
        )
        self._log(
            "info",
            "传输计划已确定：来源将直接安全写入目标片库",
            task,
            "transfer_plan",
        )

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
        task["used_fallback"] = 1 if result.used_fallback else 0
        db_update_task(self.task_manager.conn, task.get("task_id", ""),
                       import_path=result.import_path,
                       classify_result=result.classify_result,
                       used_fallback=task["used_fallback"])
        self._update_progress(task, 5, "classify", 60)

    def _get_import_roots(self) -> list:
        return import_roots_from_config(self.config)

    def _step_dedup(self, task: dict):
        self._update_progress(task, 6, "dedup", 65)
        self._log("info", f"同名检测: {task.get('source_filename', '')}", task, "dedup")
        from media_importer.features.configuration import (
            automatic_blocking_reasons,
            inspect_selected_target_readiness,
        )

        video_path = task.get("video_path") or task.get("source_path", "")
        try:
            write_bytes = os.path.getsize(video_path) if video_path else 0
        except OSError:
            write_bytes = 0
        readiness = inspect_selected_target_readiness(
            self.config,
            str(task.get("import_path", "")),
            write_bytes=write_bytes,
        )
        if not readiness.get("automatic_allowed"):
            reasons = automatic_blocking_reasons(readiness)
            reason = reasons[0] if reasons else "目标片库当前不可用"
            raise PipelineError(f"目标片库检查未通过: {reason}")
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
            video_ext = os.path.splitext(
                task.get("video_path")
                or task.get("source_path")
                or task.get("source_filename", "")
            )[1]
            scraped = task.get("scrape_result", {})
            if scraped.get('media_type') == 'tv':
                template = templates.get('tv', '')
            else:
                template = templates.get('movie', '')
            task["final_filename"] = apply_filename_template(
                scraped, template, video_ext
            )
        db_update_task(
            self.task_manager.conn,
            task.get("task_id", ""),
            final_filename=task.get("final_filename", ""),
        )
        subtitle_rows = db_get_subtitles(
            self.task_manager.conn,
            task.get("task_id", ""),
        )
        subtitle_plan = plan_subtitle_filenames(
            [row.get("source_path", "") for row in subtitle_rows],
            task.get("final_filename", ""),
            self.config.get("filename_templates", {}).get(
                "subtitle", "{video_filename}.{lang}.{ext}"
            ),
        )
        for row, planned in zip(subtitle_rows, subtitle_plan, strict=False):
            db_update_subtitle(
                self.task_manager.conn,
                row["id"],
                planned_filename=planned["filename"],
                lang=planned["lang"],
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
            phase_callback=self._import_phase_callback(task),
        )
        if result.source_cleanup.message:
            self._log("info", result.source_cleanup.message, task, "import")

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
        self._step_rename(task)

        conflict = task.get("dedup_result") or {}
        action = str(conflict.get("resolved_action") or "")
        if not action:
            self._step_dedup(task)

        if action == "replace_existing":
            conflict = DedupService(self.config).prepare_replace(task, conflict)
            task["dedup_result"] = conflict
            db_update_task(
                self.task_manager.conn,
                tid,
                dedup_result=conflict,
                dedup_existing_file=conflict.get("existing_file", ""),
            )

        self._prepare_import_input(task)

        result = import_service.import_task(
            task,
            original_source_video,
            original_source_subs,
            overwrite=action == "replace_existing",
            conflict_snapshot=conflict if action == "replace_existing" else None,
            phase_callback=self._import_phase_callback(task),
        )
        if result.source_cleanup.message:
            self._log("info", result.source_cleanup.message, task, "import")

        db_update_task(self.task_manager.conn, tid,
                       import_video_path=task.get("import_video_path", ""),
                       import_success=1)

        self._update_progress(task, 8, "import", 90)

    def _step_reorganize_from_confirm(self, task: dict):
        """Move a fallback library bundle to the current formal rule target."""
        self._update_progress(task, 8, "reorganize", 80)
        tid = task.get("task_id", "")
        self._log("info", f"重新整理: {task.get('source_filename', '')}", task, "import")
        self._step_rename(task)

        conflict = task.get("dedup_result") or {}
        action = str(conflict.get("resolved_action") or "")
        if not action:
            self._step_dedup(task)
        if action == "replace_existing":
            raise PipelineError("重新整理不会覆盖片库现有文件，请选择保留现有或两个都保留")
        if action == "keep_both":
            task["final_filename"] = str(conflict.get("suggested_filename") or "")
            db_update_task(
                self.task_manager.conn,
                tid,
                final_filename=task["final_filename"],
            )

        result = ReorganizationService(
            self.config,
            self.task_manager.conn,
        ).reorganize_task(
            task,
            phase_callback=self._import_phase_callback(task),
        )
        task["video_path"] = result.video_path
        task["import_video_path"] = result.video_path
        task["subtitle_files"] = result.subtitle_files
        db_update_task(
            self.task_manager.conn,
            tid,
            video_path=result.video_path,
            import_video_path=result.video_path,
            import_success=1,
            file_location="import",
        )
        self._update_progress(task, 8, "reorganize", 90)

    def _import_phase_callback(self, task: dict):
        phase_ranges = {
            "resume_check": (80, 81),
            "transfer": (80, 87),
            "verify_source": (87, 88),
            "verify_target": (88, 89),
            "publish": (89, 90),
        }

        def callback(phase, completed, total):
            start, end = phase_ranges.get(phase, (80, 90))
            fraction = min(1.0, completed / total) if total > 0 else 0.0
            pct = int(start + (end - start) * fraction)
            self._update_transfer_progress(
                task,
                8,
                f"import_{phase}",
                pct,
                completed,
                total,
                check_stop=not (phase == "publish" and total > 0 and completed >= total),
            )

        return callback

    def _step_notify(self, task: dict):
        self._update_progress(task, 9, "notify", 95)

    def _step_record(self, task: dict):
        self._update_progress(task, 10, "record", 100)
        self.task_manager.update_task(task)
