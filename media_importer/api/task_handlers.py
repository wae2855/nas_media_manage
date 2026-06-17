import os
import threading

from media_importer.features.import_flow import run_batch_for_api, run_file_for_api
from media_importer.features.tasks import (
    cancel_task_for_api,
    clear_tasks_for_api,
    confirm_all_tasks_for_api,
    confirm_task_for_api,
    get_task_for_api,
    get_task_stats_for_api,
    get_task_subtitles_for_api,
    get_queue_status_for_api,
    ignore_task_for_api,
    pause_queue_for_api,
    preview_task_for_api,
    reclassify_task_for_api,
    rename_task_file_for_api,
    resume_queue_for_api,
    retry_all_failed_for_api,
    retry_task_for_api,
)
from media_importer.features.import_flow.services.classification import ClassificationService
from media_importer.core.db.dimension_repo import get_enabled_dimensions
from media_importer.api import globals
from .task_delete import delete_task
from .utils import json_response


class TaskHandlersMixin:
    def _get_task(self, *, body: dict, params: dict, query: dict):
        task_id = params.get("task_id", "")
        result = get_task_for_api(globals._global_task_manager, task_id)
        json_response(self, result.code, data=result.data, message=result.message)

    def _delete_task(self, *, body: dict, params: dict, query: dict):
        task_id = params.get("task_id", "")
        delete_files = bool((body or {}).get("delete_files", False))
        delete_task(self, task_id, delete_files, globals_module=globals, respond=json_response)

    def _clear_tasks(self, *, body: dict, params: dict, query: dict):
        result = clear_tasks_for_api(
            globals._global_task_manager,
            body.get("status"),
            logger=globals._global_logger,
        )
        json_response(self, result.code, data=result.data, message=result.message)

    def _retry_task(self, *, body: dict, params: dict, query: dict):
        task_id = params.get("task_id", "")
        result = retry_task_for_api(
            globals._global_task_manager,
            globals._global_pipeline,
            task_id,
            logger=globals._global_logger,
        )
        json_response(self, result.code, data=result.data, message=result.message)

    def _task_cancel(self, *, body: dict, params: dict, query: dict):
        task_id = params.get("task_id", "")
        result = cancel_task_for_api(
            globals._global_task_manager,
            task_id,
            logger=globals._global_logger,
        )
        json_response(self, result.code, data=result.data, message=result.message)

    def _queue_retry_all(self, *, body: dict, params: dict, query: dict):
        result = retry_all_failed_for_api(
            globals._global_task_manager,
            globals._global_pipeline,
            logger=globals._global_logger,
        )
        json_response(self, result.code, data=result.data, message=result.message)

    def _queue_pause(self, *, body: dict, params: dict, query: dict):
        result = pause_queue_for_api(globals._global_pipeline, globals._global_metrics)
        json_response(self, result.code, message=result.message)

    def _queue_resume(self, *, body: dict, params: dict, query: dict):
        result = resume_queue_for_api(globals._global_pipeline, globals._global_metrics)
        json_response(self, result.code, message=result.message)

    def _queue_status(self, *, body: dict, params: dict, query: dict):
        result = get_queue_status_for_api(globals._global_pipeline, globals._global_task_manager)
        json_response(self, result.code, data=result.data, message=result.message)

    def _task_confirm(self, *, body: dict, params: dict, query: dict):
        task_id = params.get("task_id", "")
        result = confirm_task_for_api(
            globals._global_pipeline,
            globals._global_task_manager,
            task_id,
        )
        json_response(self, result.code, data=result.data, message=result.message)

    def _task_reclassify(self, *, body: dict, params: dict, query: dict):
        task_id = params.get("task_id", "")
        result = reclassify_task_for_api(
            globals._global_pipeline,
            task_id,
            body.get("dimensions", {}),
            task_manager=globals._global_task_manager,
        )
        json_response(self, result.code, data=result.data, message=result.message)

    def _task_preview(self, *, body: dict, params: dict, query: dict):
        task_id = params.get("task_id", "")
        result = preview_task_for_api(
            globals._global_pipeline,
            task_id,
            body,
            task_manager=globals._global_task_manager,
        )
        json_response(self, result.code, data=result.data, message=result.message)

    def _task_classify_preview(self, *, body: dict, params: dict, query: dict):
        task_id = params.get("task_id", "")
        task = get_task_for_api(globals._global_task_manager, task_id) if globals._global_task_manager else None
        if not task or task.code != 200:
            json_response(self, 404, message=f"Task not found: {task_id}")
            return
        task_data = task.data.get("task", {})
        svc = ClassificationService(globals._config or {})

        enabled_dims = None
        if globals._global_task_manager and hasattr(globals._global_task_manager, 'conn'):
            enabled_dims = {d["name"] for d in get_enabled_dimensions(globals._global_task_manager.conn)}

        result = svc.preview_classify(
            task_data,
            override_dimensions=body.get("dimensions"),
            override_filename=body.get("filename"),
            enabled_dims=enabled_dims,
        )
        json_response(self, 200, data=result)

    def _task_ignore(self, *, body: dict, params: dict, query: dict):
        task_id = params.get("task_id", "")
        result = ignore_task_for_api(
            globals._global_task_manager,
            globals._config or {},
            task_id,
        )
        json_response(self, result.code, data=result.data, message=result.message)

    def _task_subtitles(self, *, body: dict, params: dict, query: dict):
        task_id = params.get("task_id", "")
        result = get_task_subtitles_for_api(globals._global_task_manager, task_id)
        json_response(self, result.code, data=result.data, message=result.message)

    def _task_rename(self, *, body: dict, params: dict, query: dict):
        task_id = params.get("task_id", "")
        result = rename_task_file_for_api(
            globals._global_task_manager,
            task_id,
            body.get("new_filename"),
        )
        json_response(self, result.code, data=result.data, message=result.message)

    def _task_confirm_all(self, *, body: dict, params: dict, query: dict):
        result = confirm_all_tasks_for_api(
            globals._global_pipeline,
            globals._global_task_manager,
        )
        json_response(self, result.code, data=result.data, message=result.message)

    def _task_stats(self, *, body: dict, params: dict, query: dict):
        result = get_task_stats_for_api(globals._global_task_manager)
        json_response(self, result.code, data=result.data, message=result.message)

    def _run_batch(self, *, body: dict, params: dict, query: dict):
        result = run_batch_for_api(globals._global_pipeline)
        json_response(self, result.code, data=result.data, message=result.message)

    def _run_file(self, *, body: dict, params: dict, query: dict):
        result = run_file_for_api(
            globals._config or {},
            globals._global_task_manager,
            globals._global_pipeline,
            body.get("path", ""),
        )
        json_response(self, result.code, data=result.data, message=result.message)

    def _restart_service(self, *, body: dict, params: dict, query: dict):
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
