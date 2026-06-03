import os
import threading

from media_importer.core.db import get_subtitles_by_task as db_get_subtitles
from media_importer.features.tasks import (
    TaskManager,
    clear_tasks_for_api,
    confirm_all_tasks_for_api,
    confirm_task_for_api,
    get_queue_status_for_api,
    ignore_task_for_api,
    pause_queue_for_api,
    reclassify_task_for_api,
    rename_task_file_for_api,
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
        result = confirm_task_for_api(
            globals._global_pipeline,
            globals._global_task_manager,
            task_id,
        )
        json_response(self, result.code, data=result.data, message=result.message)

    def _task_reclassify(self, task_id: str, body: dict):
        result = reclassify_task_for_api(
            globals._global_pipeline,
            task_id,
            body.get("dimensions", {}),
        )
        json_response(self, result.code, data=result.data, message=result.message)

    def _task_ignore(self, task_id: str):
        result = ignore_task_for_api(
            globals._global_task_manager,
            globals._config or {},
            task_id,
        )
        json_response(self, result.code, data=result.data, message=result.message)

    def _task_subtitles(self, task_id: str):
        subs = db_get_subtitles(globals._global_task_manager.conn, task_id)
        json_response(self, 200, data={"subtitles": subs, "total": len(subs)})

    def _task_rename(self, task_id: str, body: dict):
        result = rename_task_file_for_api(
            globals._global_task_manager,
            task_id,
            body.get("new_filename"),
        )
        json_response(self, result.code, data=result.data, message=result.message)

    def _task_confirm_all(self):
        result = confirm_all_tasks_for_api(
            globals._global_pipeline,
            globals._global_task_manager,
        )
        json_response(self, result.code, data=result.data, message=result.message)

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
