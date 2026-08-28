import os
from typing import Optional

from media_importer.features.import_flow.context import TaskContext
from media_importer.features.import_flow.services import (
    ClassificationService,
    apply_filename_template,
)
from media_importer.features.import_flow.utils import PipelineError, PipelineSkipError
from media_importer.features.source_files import SourceCleanupService
from media_importer.features.tasks import (
    FILE_LOCATION_RECYCLE,
    FILE_LOCATION_SOURCE,
    mark_failed,
    mark_imported,
    mark_processing_step,
    mark_skipped,
)
from media_importer.infrastructure.db import get_enabled_dimensions
from media_importer.infrastructure.db import update_subtitles_by_task as db_update_subs
from media_importer.infrastructure.db import update_task as db_update_task


class ConfirmMixin:  # type: ignore[misc]
    def confirm_task(self, task_id: str, confirmed_title: Optional[str] = None,
                     override_source: Optional[str] = None) -> bool:
        task = self.task_manager.get_task(task_id)
        if not task or task.get("stage") != "AWAIT_REVIEW":
            raise PipelineError(f"任务不可确认: 状态={task.get('status', 'UNKNOWN') if task else 'NOT_FOUND'}/{task.get('stage', '') if task else ''}")
        ctx = TaskContext(task)
        tid = task_id
        original_source_video = task.get("source_path", "")
        subtitle_source_files = task.get("subtitle_source_files", [])
        original_source_subs = subtitle_source_files or task.get("subtitle_files", [])
        temp_video_path_for_cleanup = task.get("video_path", "")

        # S3 CAS：AWAIT_REVIEW → RUNNING 一次性占用（并发双 confirm 只成功一次）
        from media_importer.features.tasks.transitions import apply as _apply_transition
        from media_importer.infrastructure.db import compare_and_update_task
        claim_fields = _apply_transition(task, "confirm_start")
        claimed = compare_and_update_task(
            self.task_manager.conn, tid,
            expect_status="PENDING", expect_stage="AWAIT_REVIEW",
            **claim_fields,
        )
        if claimed is None:
            raise PipelineError("任务状态已变更（可能已被并发确认），请刷新后重试")

        confirmed_override = 1 if override_source else 0
        db_update_task(self.task_manager.conn, tid,
                       confirmed_override=confirmed_override,
                       confirmed_title=confirmed_title or "",
                       override_source=override_source or "")

        db_update_subs(self.task_manager.conn, tid,
                       confirm_status="CONFIRMED")

        try:
            enabled_dim_names = {d["name"] for d in get_enabled_dimensions(self.task_manager.conn)}
            classify_result = ClassificationService(self.config).classify_task(task, enabled_dim_names)
            task["import_path"] = classify_result.import_path
            task["classify_result"] = classify_result.classify_result
            db_update_task(self.task_manager.conn, tid,
                           import_path=classify_result.import_path,
                           classify_result=classify_result.classify_result)
            self._log("info", f"确认分类: {classify_result.import_path}", task, "classify")

            self._step_import_from_confirm(task, original_source_video, original_source_subs)
            self._step_notify(task)
            self._step_record(task)

            db_update_task(self.task_manager.conn, tid, **mark_imported(ctx))
            self.hooks.run_after_success(task)
            if self.metrics:
                self.metrics.record_task_complete("success")
            self._log("info", f"确认入库完成: {task.get('source_filename', '')}", task)
            return True
        except PipelineSkipError as e:
            # 去重判重等跳过场景：标 SKIPPED 而非 FAILED（与正常流程 runner 行为一致）
            self._log("info", f"确认入库跳过: {task.get('source_filename', '')} - {e}", task)
            self._cleanup_temp_on_failure(task, temp_video_path_for_cleanup or "")
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
            self._cleanup_temp_on_failure(task, temp_video_path_for_cleanup)
            db_update_task(self.task_manager.conn, tid,
                           **mark_failed(
                                ctx, error_msg,
                                file_location=FILE_LOCATION_SOURCE,
                                video_path=temp_video_path_for_cleanup or "",
                            ))
            self._log("error", f"确认入库失败: {task.get('source_filename', '')} - {e}", task)
            return False

    def preview_task(self, task_id: str, updates: dict) -> dict:
        """预览元数据/维度/文件名变更，只更新 DB + 重跑分类，不触发文件操作。"""
        task = self.task_manager.get_task(task_id)
        if not task:
            raise PipelineError(f"任务不存在: {task_id}")
        tid = task_id

        scrape_result = task.get("scrape_result", {})
        if isinstance(scrape_result, str):
            scrape_result = {}

        if "title_cn" in updates:
            scrape_result["title_cn"] = updates["title_cn"]
        if "title_en" in updates:
            scrape_result["title_en"] = updates["title_en"]
        if "year" in updates:
            scrape_result["year"] = updates["year"]

        current_dims = task.get("scrape_dimensions", {})
        if isinstance(current_dims, str):
            current_dims = {}
        if "dimensions" in updates:
            dims = updates["dimensions"]
            current_dims.update(dims)
            enabled_dim_names = {d["name"] for d in get_enabled_dimensions(self.task_manager.conn)}
            current_dims = {k: v for k, v in current_dims.items() if k in enabled_dim_names}
            scrape_result["dimensions"] = current_dims
            # 人工修改的维度记录来源为 manual（区别于 provider/file/default）
            dim_sources = task.get("dim_sources") or {}
            if isinstance(dim_sources, str):
                dim_sources = {}
            for k in dims:
                dim_sources[k] = "manual"
            task["dim_sources"] = dim_sources

        task["scrape_result"] = scrape_result
        task["scrape_dimensions"] = current_dims

        db_update_task(
            self.task_manager.conn, tid,
            scrape_result=scrape_result,
            scrape_dimensions=current_dims,
            scrape_title_cn=scrape_result.get("title_cn", ""),
            scrape_title_en=scrape_result.get("title_en", ""),
            scrape_year=str(scrape_result.get("year", "")) if scrape_result.get("year") else "",
            dim_sources=task.get("dim_sources", {}),
            classify_result="",
        )

        enabled_dim_names = {d["name"] for d in get_enabled_dimensions(self.task_manager.conn)}
        result = ClassificationService(self.config).classify_task(task, enabled_dim_names)
        task["import_path"] = result.import_path
        task["classify_result"] = result.classify_result

        if "filename" in updates:
            task["final_filename"] = updates["filename"]
        elif not task.get("final_filename"):
            templates = self.config.get("filename_templates", {})
            video_ext = os.path.splitext(task.get("video_path", "") or task.get("source_filename", ""))[1]
            if scrape_result.get("media_type") == "tv":
                template = templates.get("tv", "{title_cn}.{title_en}.{year}.S{season}E{episode}.{ext}")
            else:
                template = templates.get("movie", "{title_cn}.{title_en}.{year}.{resolution}.{quality}.{ext}")
            task["final_filename"] = apply_filename_template(scrape_result, template, video_ext)

        db_update_task(
            self.task_manager.conn, tid,
            scrape_result=scrape_result,
            scrape_dimensions=current_dims,
            classify_result=result.classify_result,
            import_path=result.import_path,
            final_filename=task["final_filename"],
        )

        self._log("info", f"预览更新完成: {task.get('source_filename', '')}", task)
        return self.task_manager.get_task(tid)

    def reclassify_task(self, task_id: str, new_dimensions: dict) -> dict:
        task = self.task_manager.get_task(task_id)
        if not task:
            raise PipelineError(f"任务不存在: {task_id}")
        ctx = TaskContext(task)
        tid = task_id

        current_dims = task.get("scrape_dimensions", {})
        if isinstance(current_dims, str):
            current_dims = {}
        current_dims.update(new_dimensions)

        # 清洗已禁用维度的值
        enabled_dim_names = {d["name"] for d in get_enabled_dimensions(self.task_manager.conn)}
        current_dims = {k: v for k, v in current_dims.items() if k in enabled_dim_names}
        task["scrape_dimensions"] = current_dims

        # 人工重新分类的维度记录来源为 manual
        dim_sources = task.get("dim_sources", {})
        if isinstance(dim_sources, str):
            dim_sources = {}
        for k in new_dimensions:
            dim_sources[k] = "manual"
        task["dim_sources"] = dim_sources

        scrape_result = task.get("scrape_result", {})
        if isinstance(scrape_result, dict):
            scrape_result["dimensions"] = current_dims

        db_update_task(
            self.task_manager.conn, tid,
            scrape_dimensions=current_dims,
            dim_sources=dim_sources,
            classify_result="",
        )

        result = ClassificationService(self.config).classify_task(task, enabled_dim_names)
        if not result.import_path:
            raise PipelineError(f"重新分类失败，维度=[{result.dimensions_text}]")
        if result.used_fallback:
            self._log("info", f"重新分类：无匹配规则，使用兜底目录: {result.import_path}", task, "classify")

        task["import_path"] = result.import_path
        task["classify_result"] = result.classify_result
        fields = mark_processing_step(
            ctx, current_step=5, step_name="classify", percentage=50
        )
        fields.update({
            "import_path": result.import_path,
            "classify_result": result.classify_result,
        })
        db_update_task(self.task_manager.conn, tid,
                       **fields)
        self._log("info", f"任务重新分类完成: {result.import_path}，继续后续流程", task, "classify")

        # 重分类不再触发入库（改为预览逻辑，兼容旧调用方）
        templates = self.config.get("filename_templates", {})
        video_ext = os.path.splitext(task.get("video_path", "") or task.get("source_filename", ""))[1]
        if scrape_result.get("media_type") == "tv":
            template = templates.get("tv", "{title_cn}.{title_en}.{year}.S{season}E{episode}.{ext}")
        else:
            template = templates.get("movie", "{title_cn}.{title_en}.{year}.{resolution}.{quality}.{ext}")
        task["final_filename"] = apply_filename_template(
            scrape_result, template, video_ext)

        db_update_task(self.task_manager.conn, tid,
                       import_path=result.import_path,
                       classify_result=result.classify_result,
                       final_filename=task["final_filename"])

        self._log("info", f"重新分类（预览）完成: {result.import_path}", task, "classify")
        return self.task_manager.get_task(tid)
