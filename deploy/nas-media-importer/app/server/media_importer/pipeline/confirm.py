import os
from datetime import datetime
from media_importer.core.db import update_task as db_update_task, update_subtitles_by_task as db_update_subs
from media_importer.storage.classifier import classify, render_template
from .utils import PipelineError, PipelineSkipError


class ConfirmMixin:
    def confirm_task(self, task_id: str) -> bool:
        task = self.task_manager.get_task(task_id)
        if not task or task.get("status") != "CONFIRMING":
            raise PipelineError(f"任务不可确认: 状态={task.get('status', 'UNKNOWN')}")
        tid = task_id
        original_source_video = task.get("source_path", "")
        subtitle_source_files = task.get("subtitle_source_files", [])
        original_source_subs = subtitle_source_files or task.get("subtitle_files", [])
        temp_video_path_for_cleanup = task.get("video_path", "")

        task["confirm_status"] = "CONFIRMED"
        task["confirmed_at"] = datetime.now().isoformat()
        db_update_task(self.task_manager.conn, tid,
                       confirm_status="CONFIRMED",
                       confirmed_at=task["confirmed_at"])

        db_update_subs(self.task_manager.conn, tid,
                       confirm_status="CONFIRMED")

        try:
            self._step_import_from_confirm(task, original_source_video, original_source_subs)
            self._step_notify(task)
            self._step_record(task)

            task["status"] = "SUCCESS"
            task["completed_at"] = datetime.now().isoformat()
            task["import_success"] = 1
            db_update_task(self.task_manager.conn, tid,
                           status="SUCCESS", completed_at=task["completed_at"],
                           import_success=1, file_location="import",
                           import_video_path=task.get("import_video_path", ""))
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
            self._cleanup_temp_on_failure(task, temp_video_path_for_cleanup)
            db_update_task(self.task_manager.conn, tid,
                           status="FAILED", error_message=error_msg,
                           completed_at=task["completed_at"],
                           file_location="source")
            self._log("error", f"确认入库失败: {task.get('source_filename', '')} - {e}", task)
            return False

    def reclassify_task(self, task_id: str, new_dimensions: dict) -> dict:
        task = self.task_manager.get_task(task_id)
        if not task:
            raise PipelineError(f"任务不存在: {task_id}")
        tid = task_id
        temp_video_path_for_cleanup = task.get("video_path", "")

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
            fallback_dir = self.config.get("fallback_dir", "")
            if fallback_dir:
                import_path = render_template(fallback_dir, scrape_result)
                self._log("info", f"重新分类：无匹配规则，使用兜底目录: {import_path}", task, "classify")
            else:
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
        task["status"] = "PROCESSING"
        db_update_task(self.task_manager.conn, tid,
                       import_path=import_path,
                       classify_result=import_path,
                       status="PROCESSING",
                       current_step=5,
                       step_name="classify",
                       percentage=50)
        self._log("info", f"任务重新分类完成: {import_path}，继续后续流程", task, "classify")

        try:
            self._step_dedup(task)
            self._step_rename(task)
            original_source_video = task.get("source_path", "")
            subtitle_source_files = task.get("subtitle_source_files", [])
            original_source_subs = subtitle_source_files or task.get("subtitle_files", [])
            self._step_import(task, original_source_video, original_source_subs)
            self._step_notify(task)
            self._step_record(task)

            task["status"] = "SUCCESS"
            task["completed_at"] = datetime.now().isoformat()
            task["import_success"] = 1
            db_update_task(self.task_manager.conn, tid,
                           status="SUCCESS", completed_at=task["completed_at"],
                           import_success=1, file_location="import",
                           import_video_path=task.get("import_video_path", ""))
            self.hooks.run_after_success(task)
            if self.metrics:
                self.metrics.record_task_complete("success")
            self._log("info", f"重新分类入库成功: {task.get('source_filename', '')}", task)
        except PipelineSkipError as e:
            task["status"] = "SKIPPED"
            task["skip_reason"] = str(e)
            task["completed_at"] = datetime.now().isoformat()
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
                               status="SKIPPED", skip_reason=str(e),
                               completed_at=task["completed_at"],
                               file_location="recycle", video_path="")
            elif source_path and source_path.startswith(recycle_dir):
                db_update_task(self.task_manager.conn, tid,
                               status="SKIPPED", skip_reason=str(e),
                               completed_at=task["completed_at"],
                               file_location="recycle", video_path="")
            else:
                db_update_task(self.task_manager.conn, tid,
                               status="SKIPPED", skip_reason=str(e),
                               completed_at=task["completed_at"],
                               file_location="source", video_path="")
            self._log("info", f"重新分类后跳过: {task.get('source_filename', '')} - {e}", task)
        except Exception as e:
            error_msg = str(e)
            task["status"] = "FAILED"
            task["error_message"] = error_msg
            task["completed_at"] = datetime.now().isoformat()
            self._cleanup_temp_on_failure(task, temp_video_path_for_cleanup)
            db_update_task(self.task_manager.conn, tid,
                           status="FAILED", error_message=error_msg,
                           completed_at=task["completed_at"],
                           file_location="source", video_path="")
            self._log("error", f"重新分类入库失败: {task.get('source_filename', '')} - {e}", task)

        return self.task_manager.get_task(tid)
