import os
import shutil
import threading

from media_importer.core.db import (
    update_task as db_update_task,
    delete_task as db_delete_task,
    get_subtitles_by_task as db_get_subtitles,
    update_subtitles_by_task as db_update_subtitles_by_task,
    update_subtitle as db_update_subtitle,
    count_by_status as db_count_by_status,
    count_by_specific_status as db_count_specific,
    VALID_STATUSES,
)
from media_importer.core.task_manager import TaskManager
from media_importer.api import globals
from .utils import json_response


class TaskHandlersMixin:
    def _get_task(self, task_id: str):
        task = globals._global_task_manager.get_task(task_id)
        if task is None:
            json_response(self, 404, message=f"Task not found: {task_id}")
            return
        json_response(self, 200, data={"task": task})

    def _delete_task(self, task_id: str, delete_files: bool = False):
        task = globals._global_task_manager.get_task(task_id)
        if task is None:
            json_response(self, 404, message=f"Task not found: {task_id}")
            return

        current_status = task.get("status", "")
        if current_status == "PROCESSING":
            json_response(self, 400, message="任务正在处理中，无法删除，请等待处理完成")
            return

        deleted_files = []
        missing_files = []
        file_location = task.get("file_location", "source")

        temp_files_to_cleanup = []
        if file_location == "temp":
            vp = task.get("video_path", "")
            if vp:
                if os.path.exists(vp):
                    temp_files_to_cleanup.append(vp)
                else:
                    missing_files.append(os.path.basename(vp))
            for sub in (task.get("subtitle_files") or []):
                sub_str = str(sub) if sub else ""
                if sub_str:
                    if os.path.exists(sub_str):
                        temp_files_to_cleanup.append(sub_str)
                    else:
                        missing_files.append(os.path.basename(sub_str))

        temp_dir = globals._config.get('temp_dir', '') if globals._config else ''
        for f in temp_files_to_cleanup:
            try:
                f_abs = os.path.abspath(f)
                if temp_dir and f_abs.startswith(os.path.abspath(temp_dir) + os.sep):
                    if os.path.exists(f):
                        os.remove(f)
                        deleted_files.append(os.path.basename(f))
                    else:
                        missing_files.append(os.path.basename(f))
            except OSError:
                pass

        if delete_files:
            files_to_delete = []
            files_to_check = []

            if file_location == "import":
                ivp = task.get("import_video_path", "")
                if ivp:
                    files_to_check.append(ivp)
                for sub in (task.get("subtitle_files") or []):
                    sub_str = str(sub) if sub else ""
                    if sub_str:
                        files_to_check.append(sub_str)
            elif file_location == "recycle":
                sp = task.get("source_path", "")
                if sp:
                    files_to_check.append(sp)
                for sub in (task.get("subtitle_files") or []):
                    sub_str = str(sub) if sub else ""
                    if sub_str:
                        files_to_check.append(sub_str)
            elif file_location == "source":
                sp = task.get("source_path", "")
                if sp:
                    files_to_check.append(sp)
                for sub in (task.get("subtitle_files") or []):
                    sub_str = str(sub) if sub else ""
                    if sub_str:
                        files_to_check.append(sub_str)

            for f in files_to_check:
                if os.path.exists(f):
                    files_to_delete.append(f)
                else:
                    missing_files.append(os.path.basename(f))

            source_policy = globals._config.get("source_policy", {}) if globals._config else {}
            import_dirs = []
            for rule in (globals._config.get("path_rules", []) if globals._config else []):
                tpl = rule.get("template", "")
                if tpl:
                    import_dirs.append(tpl)

            allowed_dirs = [
                globals._config.get("source_dir", "") if globals._config else "",
                globals._config.get("temp_dir", "") if globals._config else "",
                source_policy.get("recycle_dir", ""),
            ] + import_dirs

            for f in files_to_delete:
                try:
                    f_abs = os.path.abspath(f)
                    allowed = any(
                        d and f_abs.startswith(os.path.abspath(d) + os.sep)
                        for d in allowed_dirs
                    )
                    if allowed and os.path.exists(f):
                        os.remove(f)
                        deleted_files.append(os.path.basename(f))
                except OSError:
                    pass

        db_delete_task(globals._global_task_manager.conn, task_id)

        location_labels = {
            "source": "源文件", "recycle": "回收站文件",
            "import": "入库文件", "temp": "中转文件",
        }
        loc_label = location_labels.get(file_location, "文件")
        result = {"deleted": task_id, "file_location": file_location}

        msg_parts = ["任务已删除"]

        if deleted_files:
            result["deleted_files"] = deleted_files
            msg_parts.append(f"已删除 {len(deleted_files)} 个{loc_label}")

        if missing_files and delete_files:
            result["missing_files"] = missing_files
            msg_parts.append(f"{len(missing_files)} 个文件已不存在")

        json_response(self, 200, data=result, message="，".join(msg_parts))

    def _clear_tasks(self, body: dict):
        status = body.get("status")
        if status:
            status = str(status).strip().upper()
        if status and status != "ALL" and status not in VALID_STATUSES:
            if globals._global_logger:
                globals._global_logger.warning(f"Invalid status filter: {status}, VALID_STATUSES={VALID_STATUSES}")
            json_response(self, 400, message=f"Invalid status: {status}")
            return
        if status and status == "ALL":
            status = None
        globals._global_task_manager.clear_tasks(status=status)
        json_response(self, 200, message="Tasks cleared", data={"status": status or "all"})

    def _retry_task(self, task_id: str):
        task = globals._global_task_manager.retry_task(task_id)
        if task is None:
            json_response(self, 400, message=f"任务不存在或当前状态不可重试: {task_id}")
            return

        if globals._global_pipeline and not globals._global_pipeline.is_paused():
            def run_retry():
                try:
                    globals._global_pipeline.process_one(task)
                except Exception as e:
                    globals._global_logger.error(f"重试任务执行异常: {e}")
            threading.Thread(target=run_retry, daemon=True).start()

        json_response(self, 200, data={"task": task}, message="任务已重试并开始执行")

    def _queue_retry_all(self):
        retried = globals._global_task_manager.retry_all_failed()

        if retried and globals._global_pipeline and not globals._global_pipeline.is_paused():
            def run_retry_all():
                try:
                    globals._global_pipeline.run_all()
                except Exception as e:
                    globals._global_logger.error(f"批量重试执行异常: {e}")
            threading.Thread(target=run_retry_all, daemon=True).start()

        json_response(self, 200, data={
            "retried_count": len(retried),
            "task_ids": [t.get("task_id", "") for t in retried]
        }, message=f"已重试 {len(retried)} 个失败任务并开始执行")

    def _queue_pause(self):
        if globals._global_pipeline:
            globals._global_pipeline.pause()
        if globals._global_metrics:
            globals._global_metrics.set_queue_paused(True)
        json_response(self, 200, message="Queue paused")

    def _queue_resume(self):
        if globals._global_pipeline:
            globals._global_pipeline.resume()
        if globals._global_metrics:
            globals._global_metrics.set_queue_paused(False)
        json_response(self, 200, message="Queue resumed")

    def _queue_status(self):
        paused = globals._global_pipeline.is_paused() if globals._global_pipeline else False
        counts = globals._global_task_manager.count_by_status() if globals._global_task_manager else {}
        json_response(self, 200, data={
            "paused": paused,
            "by_status": counts
        })

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
        recycle_dir = source_policy.get("recycle_dir", "")
        file_location = task.get("file_location", "source")

        if file_location == "temp":
            temp_video = task.get("video_path", "")
            if recycle_dir and temp_video and os.path.exists(temp_video):
                os.makedirs(recycle_dir, exist_ok=True)
                dest_video = TaskManager._resolve_dest_path(
                    recycle_dir, os.path.basename(temp_video))
                try:
                    shutil.move(temp_video, dest_video)
                except (OSError, shutil.Error):
                    dest_video = temp_video
                subtitle_paths = task.get("subtitle_files", [])
                new_sub_paths = {}
                for sub in subtitle_paths:
                    if sub and os.path.exists(sub):
                        dest_sub = TaskManager._resolve_dest_path(
                            recycle_dir, os.path.basename(sub))
                        try:
                            shutil.move(sub, dest_sub)
                            new_sub_paths[os.path.basename(sub)] = dest_sub
                        except (OSError, shutil.Error):
                            pass
                if new_sub_paths:
                    subs = db_get_subtitles(globals._global_task_manager.conn, task_id)
                    for sub in subs:
                        sub_basename = os.path.basename(
                            sub.get("source_path", "") or sub.get("target_path", ""))
                        if sub_basename in new_sub_paths:
                            db_update_subtitle(
                                globals._global_task_manager.conn, sub["id"],
                                target_path=new_sub_paths[sub_basename])
                db_update_task(globals._global_task_manager.conn, task_id,
                               status="SKIPPED",
                               skip_reason="用户忽略",
                               source_path=dest_video,
                               source_filename=os.path.basename(dest_video),
                               file_location="recycle",
                               video_path="")
            else:
                temp_dir = globals._config.get('temp_dir', '') if globals._config else ''
                if temp_video and temp_dir and str(temp_video).startswith(temp_dir) and os.path.exists(temp_video):
                    try:
                        os.remove(temp_video)
                    except OSError:
                        pass
                    for sub in (task.get("subtitle_files") or []):
                        sub_str = str(sub) if sub else ""
                        if sub_str and os.path.exists(sub_str) and temp_dir in sub_str:
                            try:
                                os.remove(sub_str)
                            except OSError:
                                pass
                db_update_subtitles_by_task(
                    globals._global_task_manager.conn, task_id,
                    status="FAILED", target_path="")
                db_update_task(globals._global_task_manager.conn, task_id,
                               status="SKIPPED",
                               skip_reason="用户忽略",
                               file_location="source")
        else:
            source_path = task.get("source_path", "")
            subtitle_paths = task.get("subtitle_files", [])
            if recycle_dir and source_path and os.path.exists(source_path):
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

        from media_importer.core.safety import validate_path_safety, validate_file_ext, ALLOWED_MEDIA_EXTS

        source_dir = globals._config.get("source_dir", "") if globals._config else ""
        allowed_dirs = [source_dir] if source_dir else []

        ok, msg = validate_path_safety(file_path, allowed_base_dirs=allowed_dirs)
        if not ok:
            json_response(self, 400, message=f"路径校验失败: {msg}")
            return

        ok, msg = validate_file_ext(file_path, ALLOWED_MEDIA_EXTS)
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
