import os
import threading

from media_importer.core.db import (
    update_task as db_update_task,
    get_subtitles_by_task as db_get_subtitles,
    update_subtitles_by_task as db_update_subtitles_by_task,
)
from media_importer.features.tasks import (
    TaskManager,
    clear_tasks_for_api,
    get_queue_status_for_api,
    pause_queue_for_api,
    resume_queue_for_api,
    retry_all_failed_for_api,
    retry_task_for_api,
)
from media_importer.api import globals
from .task_delete import delete_task
from .utils import json_response


class TaskHandlersMixin:
    def _get_task(self, task_id: str):
        task = globals._global_task_manager.get_task(task_id)
        if task is None:
            json_response(self, 404, message=f"Task not found: {task_id}")
            return
        json_response(self, 200, data={"task": task})

    def _delete_task(self, task_id: str, delete_files: bool = False):
        delete_task(self, task_id, delete_files, globals_module=globals, respond=json_response)

    def _clear_tasks(self, body: dict):
        result = clear_tasks_for_api(
            globals._global_task_manager,
            body.get("status"),
            logger=globals._global_logger,
        )
        json_response(self, result.code, data=result.data, message=result.message)

    def _retry_task(self, task_id: str):
        result = retry_task_for_api(
            globals._global_task_manager,
            globals._global_pipeline,
            task_id,
            logger=globals._global_logger,
        )
        json_response(self, result.code, data=result.data, message=result.message)

    def _queue_retry_all(self):
        result = retry_all_failed_for_api(
            globals._global_task_manager,
            globals._global_pipeline,
            logger=globals._global_logger,
        )
        json_response(self, result.code, data=result.data, message=result.message)

    def _queue_pause(self):
        result = pause_queue_for_api(globals._global_pipeline, globals._global_metrics)
        json_response(self, result.code, message=result.message)

    def _queue_resume(self):
        result = resume_queue_for_api(globals._global_pipeline, globals._global_metrics)
        json_response(self, result.code, message=result.message)

    def _queue_status(self):
        result = get_queue_status_for_api(globals._global_pipeline, globals._global_task_manager)
        json_response(self, result.code, data=result.data, message=result.message)

    def _task_confirm(self, task_id: str):
        if globals._global_pipeline is None:
            json_response(self, 500, message="Pipeline not initialized")
            return
        try:
            ok = globals._global_pipeline.confirm_task(task_id)
            if ok:
                json_response(self, 200, message="任务确认入库成功")
            else:
                task = globals._global_task_manager.get_task(task_id)
                err = task.get("error_message", "") if task else ""
                json_response(self, 500, message="确认入库失败" + (f": {err}" if err else ""))
        except Exception as e:
            json_response(self, 400, message=str(e))

    def _task_reclassify(self, task_id: str, body: dict):
        if globals._global_pipeline is None:
            json_response(self, 500, message="Pipeline not initialized")
            return
        dimensions = body.get("dimensions", {})
        if not dimensions:
            json_response(self, 400, message="缺少 dimensions 参数")
            return
        try:
            task = globals._global_pipeline.reclassify_task(task_id, dimensions)
            json_response(self, 200, data={"task": task}, message="重新分类完成")
        except Exception as e:
            json_response(self, 400, message=str(e))

    def _task_ignore(self, task_id: str):
        task = globals._global_task_manager.get_task(task_id)
        if task is None:
            json_response(self, 404, message=f"Task not found: {task_id}")
            return
        current_status = task.get("status", "")
        if current_status not in ("FAILED", "CONFIRMING"):
            json_response(self, 400, message=f"当前状态不可忽略: {current_status}")
            return
        source_policy = globals._config.get("source_policy", {}) if globals._config else {}
        recycle_dir = source_policy.get("recycle_dir", "") or source_policy.get("quarantine_dir", "")
        cleanup = source_policy.get("cleanup_source_after_done", True)
        file_location = task.get("file_location", "source")

        if file_location == "temp":
            temp_video = task.get("video_path", "")
            temp_dir = globals._config.get('temp_dir', '') if globals._config else ''
            if temp_video and temp_dir and str(temp_video).startswith(temp_dir) and os.path.exists(temp_video):
                try:
                    os.remove(temp_video)
                except OSError:
                    pass
            for sub in (task.get("subtitle_files") or []):
                sub_str = str(sub) if sub else ""
                if sub_str and temp_dir and sub_str.startswith(temp_dir) and os.path.exists(sub_str):
                    try:
                        os.remove(sub_str)
                    except OSError:
                        pass
            db_update_subtitles_by_task(
                globals._global_task_manager.conn, task_id,
                status="FAILED", target_path="")

            source_path = task.get("source_path", "")
            subtitle_paths = task.get("subtitle_files", [])
            if cleanup and recycle_dir and source_path and os.path.exists(source_path):
                globals._global_task_manager.move_to_recycle_bin(
                    task_id=task_id,
                    source_path=source_path,
                    subtitle_paths=subtitle_paths if isinstance(subtitle_paths, list) else [],
                    recycle_dir=recycle_dir,
                )
                db_update_task(globals._global_task_manager.conn, task_id,
                               status="SKIPPED",
                               skip_reason="用户忽略",
                               file_location="recycle",
                               video_path="",
                               error_message=f"已移入回收站: {recycle_dir}")
            else:
                db_update_task(globals._global_task_manager.conn, task_id,
                               status="SKIPPED",
                               skip_reason="用户忽略",
                               file_location="source",
                               video_path="")
        else:
            source_path = task.get("source_path", "")
            subtitle_paths = task.get("subtitle_files", [])
            if cleanup and recycle_dir and source_path and os.path.exists(source_path):
                globals._global_task_manager.move_to_recycle_bin(
                    task_id=task_id,
                    source_path=source_path,
                    subtitle_paths=subtitle_paths if isinstance(subtitle_paths, list) else [],
                    recycle_dir=recycle_dir,
                )
                db_update_task(globals._global_task_manager.conn, task_id,
                               status="SKIPPED",
                               skip_reason="用户忽略",
                               error_message=f"已移入回收站: {recycle_dir}")
            else:
                db_update_task(globals._global_task_manager.conn, task_id,
                               status="SKIPPED",
                               skip_reason="用户忽略")
        json_response(self, 200, message="任务已忽略")

    def _task_subtitles(self, task_id: str):
        subs = db_get_subtitles(globals._global_task_manager.conn, task_id)
        json_response(self, 200, data={"subtitles": subs, "total": len(subs)})

    def _task_rename(self, task_id: str, body: dict):
        new_filename = (body.get("new_filename") or "").strip()
        if not new_filename:
            json_response(self, 400, message="new_filename 参数必填")
            return
        task = globals._global_task_manager.get_task(task_id)
        if task is None:
            json_response(self, 404, message=f"Task not found: {task_id}")
            return
        file_location = task.get("file_location", "source")
        if file_location == "deleted":
            json_response(self, 400, message="文件已删除，无法重命名")
            return
        if file_location == "import":
            current_path = task.get("import_video_path", "")
        elif file_location == "temp":
            current_path = task.get("video_path", "")
        elif file_location == "recycle":
            current_path = task.get("source_path", "")
        else:
            current_path = task.get("source_path", "")
        if not current_path or not os.path.exists(current_path):
            json_response(self, 400, message=f"当前文件路径不存在: {current_path}")
            return
        current_dir = os.path.dirname(current_path)
        new_path = os.path.join(current_dir, new_filename)
        if os.path.exists(new_path) and new_path != current_path:
            json_response(self, 400, message=f"目标文件名已存在: {new_filename}")
            return
        try:
            os.rename(current_path, new_path)
        except OSError as e:
            json_response(self, 500, message=f"重命名失败: {e}")
            return
        update_fields = {"source_filename": new_filename}
        if file_location == "import":
            update_fields["import_video_path"] = new_path
            update_fields["final_filename"] = new_filename
        elif file_location == "temp":
            update_fields["video_path"] = new_path
        elif file_location in ("source", "recycle"):
            update_fields["source_path"] = new_path
        db_update_task(globals._global_task_manager.conn, task_id, **update_fields)
        updated_task = globals._global_task_manager.get_task(task_id)
        json_response(self, 200, data={"task": updated_task}, message="文件重命名成功")

    def _task_confirm_all(self):
        if globals._global_pipeline is None:
            json_response(self, 500, message="Pipeline not initialized")
            return
        confirming_tasks = globals._global_task_manager.list_tasks(status="CONFIRMING", limit=1000)
        results = []
        for t in confirming_tasks:
            tid = t.get("task_id", "")
            try:
                ok = globals._global_pipeline.confirm_task(tid)
                results.append({"task_id": tid, "success": ok})
            except Exception as e:
                results.append({"task_id": tid, "success": False, "error": str(e)})
        success_count = sum(1 for r in results if r["success"])
        json_response(self, 200, data={
            "results": results,
            "total": len(results),
            "success": success_count,
            "failed": len(results) - success_count,
        }, message=f"批量确认完成: 成功 {success_count}, 失败 {len(results) - success_count}")

    def _task_stats(self):
        if globals._global_task_manager is None:
            json_response(self, 500, message="TaskManager not initialized")
            return
        counts = globals._global_task_manager.count_by_status()
        json_response(self, 200, data={"by_status": counts})

    def _run_batch(self):
        if globals._global_pipeline is None:
            json_response(self, 500, message="Pipeline not initialized")
            return

        def run_background():
            globals._global_pipeline.run_all()

        thread = threading.Thread(target=run_background, daemon=True)
        thread.start()
        json_response(self, 202, message="Batch processing started in background")

    def _run_file(self, body: dict):
        if globals._global_pipeline is None:
            json_response(self, 500, message="Pipeline not initialized")
            return
        file_path = body.get("path", "")
        if not file_path:
            json_response(self, 400, message="Missing 'path' field")
            return

        from media_importer.core.safety import validate_path_safety, validate_file_ext

        source_dir = globals._config.get("source_dir", "") if globals._config else ""
        allowed_dirs = [source_dir] if source_dir else []

        ok, msg = validate_path_safety(file_path, allowed_base_dirs=allowed_dirs)
        if not ok:
            json_response(self, 400, message=f"路径校验失败: {msg}")
            return

        video_exts = globals._config.get("video_extensions", []) if globals._config else []
        sub_exts = globals._config.get("subtitle_extensions", []) if globals._config else []
        media_exts = set(
            ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            for ext in video_exts + sub_exts
        )
        ok, msg = validate_file_ext(file_path, media_exts)
        if not ok:
            json_response(self, 400, message=f"文件类型校验失败: {msg}")
            return

        if not os.path.isfile(file_path):
            json_response(self, 404, message=f"File not found: {file_path}")
            return

        def run_one():
            video_file = os.path.basename(file_path)
            task = globals._global_task_manager.create_task(
                video_path=file_path,
                video_file=video_file,
                subtitle_files=[],
                file_size_mb=os.path.getsize(file_path) / (1024 * 1024)
            )
            globals._global_pipeline.process_one(task)

        thread = threading.Thread(target=run_one, daemon=True)
        thread.start()
        json_response(self, 202, message=f"Processing started: {file_path}")

    def _restart_service(self):
        import subprocess
        import sys
        import time
        try:
            if globals._global_pipeline:
                globals._global_pipeline.pause()
            if globals._global_watcher:
                globals._global_watcher.stop()

            trim_pkgvar = os.environ.get("TRIM_PKGVAR", "")
            if trim_pkgvar:
                cmd_main = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                        "..", "cmd", "main")
                if not os.path.isfile(cmd_main):
                    cmd_main = "/var/apps/nas-media-importer/cmd/main"

                def do_fnos_restart():
                    time.sleep(0.5)
                    try:
                        subprocess.run([cmd_main, "stop"], timeout=15, capture_output=True)
                        time.sleep(1)
                        subprocess.run([cmd_main, "start"], timeout=15, capture_output=True)
                    except Exception:
                        pass

                json_response(self, 200, message="服务正在重启，请等待约5秒后刷新页面...")
                threading.Thread(target=do_fnos_restart, daemon=True).start()
            else:
                json_response(self, 200, message="服务正在重启...")
                threading.Timer(1.0, lambda: os.execv(sys.executable, [sys.executable] + sys.argv)).start()
        except Exception as e:
            json_response(self, 500, message="重启失败: " + str(e))
