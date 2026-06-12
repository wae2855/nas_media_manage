import os
from media_importer.core.db import update_task as db_update_task, update_subtitles_by_task as db_update_subs
from media_importer.core.db.dimension_repo import get_enabled_dimensions
from media_importer.features.tasks import (
    FILE_LOCATION_RECYCLE,
    FILE_LOCATION_SOURCE,
    mark_confirmed,
    mark_failed,
    mark_imported,
    mark_processing_step,
    mark_skipped,
)
from media_importer.features.import_flow.context import TaskContext
from media_importer.features.import_flow.services import ClassificationService
from media_importer.features.import_flow.utils import PipelineError, PipelineSkipError


class ConfirmMixin:
    def confirm_task(self, task_id: str) -> bool:
        task = self.task_manager.get_task(task_id)
        if not task or task.get("stage") != "AWAIT_REVIEW":
            raise PipelineError(f"任务不可确认: 状态={task.get('status', 'UNKNOWN')}/{task.get('stage', '')}")
        ctx = TaskContext(task)
        tid = task_id
        original_source_video = task.get("source_path", "")
        subtitle_source_files = task.get("subtitle_source_files", [])
        original_source_subs = subtitle_source_files or task.get("subtitle_files", [])
        temp_video_path_for_cleanup = task.get("video_path", "")

        db_update_task(self.task_manager.conn, tid, **mark_confirmed(ctx))

        db_update_subs(self.task_manager.conn, tid,
                       confirm_status="CONFIRMED")

        try:
            self._step_import_from_confirm(task, original_source_video, original_source_subs)
            self._step_notify(task)
            self._step_record(task)

            db_update_task(self.task_manager.conn, tid, **mark_imported(ctx))
            self.hooks.run_after_success(task)
            if self.metrics:
                self.metrics.record_task_complete("success")
            self._log("info", f"确认入库完成: {task.get('source_filename', '')}", task)
            return True
        except Exception as e:
            error_msg = str(e)
            self._cleanup_temp_on_failure(task, temp_video_path_for_cleanup)
            db_update_task(self.task_manager.conn, tid,
                           **mark_failed(
                               ctx, error_msg,
                               file_location=FILE_LOCATION_SOURCE,
                               video_path=None,
                           ))
            self._log("error", f"确认入库失败: {task.get('source_filename', '')} - {e}", task)
            return False

    def reclassify_task(self, task_id: str, new_dimensions: dict) -> dict:
        task = self.task_manager.get_task(task_id)
        if not task:
            raise PipelineError(f"任务不存在: {task_id}")
        ctx = TaskContext(task)
        tid = task_id
        temp_video_path_for_cleanup = task.get("video_path", "")

        current_dims = task.get("scrape_dimensions", {})
        if isinstance(current_dims, str):
            current_dims = {}
        current_dims.update(new_dimensions)

        # 清洗已禁用维度的值
        enabled_dim_names = {d["name"] for d in get_enabled_dimensions(self.task_manager.conn)}
        current_dims = {k: v for k, v in current_dims.items() if k in enabled_dim_names}
        task["scrape_dimensions"] = current_dims

        scrape_result = task.get("scrape_result", {})
        if isinstance(scrape_result, dict):
            scrape_result["dimensions"] = current_dims

        db_update_task(
            self.task_manager.conn, tid,
            scrape_dimensions=current_dims,
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

        try:
            self._step_dedup(task)
            self._step_rename(task)
            original_source_video = task.get("source_path", "")
            subtitle_source_files = task.get("subtitle_source_files", [])
            original_source_subs = subtitle_source_files or task.get("subtitle_files", [])
            self._step_import(task, original_source_video, original_source_subs)
            self._step_notify(task)
            self._step_record(task)

            db_update_task(self.task_manager.conn, tid, **mark_imported(ctx))
            self.hooks.run_after_success(task)
            if self.metrics:
                self.metrics.record_task_complete("success")
            self._log("info", f"重新分类入库成功: {task.get('source_filename', '')}", task)
        except PipelineSkipError as e:
            source_policy = self.config.get("source_policy", {})
            recycle_dir = source_policy.get("recycle_dir", "")
            source_dir = self.config.get('source_dir', '')
            self._cleanup_temp_on_failure(task, temp_video_path_for_cleanup)
            source_path = task.get("source_path", "")
            if source_path and os.path.exists(source_path) and source_path.startswith(source_dir):
                self.task_manager.move_to_recycle_bin(
                    task_id=tid,
                    source_path=source_path,
                    subtitle_paths=task.get("subtitle_files", []),
                    recycle_dir=recycle_dir,
                )
                db_update_task(self.task_manager.conn, tid,
                               **mark_skipped(
                                   ctx, str(e),
                                   file_location=FILE_LOCATION_RECYCLE,
                               ))
            elif source_path and source_path.startswith(recycle_dir):
                db_update_task(self.task_manager.conn, tid,
                               **mark_skipped(
                                   ctx, str(e),
                                   file_location=FILE_LOCATION_RECYCLE,
                               ))
            else:
                db_update_task(self.task_manager.conn, tid,
                               **mark_skipped(
                                   ctx, str(e),
                                   file_location=FILE_LOCATION_SOURCE,
                               ))
            self._log("info", f"重新分类后跳过: {task.get('source_filename', '')} - {e}", task)
        except Exception as e:
            error_msg = str(e)
            self._cleanup_temp_on_failure(task, temp_video_path_for_cleanup)
            db_update_task(self.task_manager.conn, tid,
                           **mark_failed(
                               ctx, error_msg,
                               file_location=FILE_LOCATION_SOURCE,
                           ))
            self._log("error", f"重新分类入库失败: {task.get('source_filename', '')} - {e}", task)

        return self.task_manager.get_task(tid)
