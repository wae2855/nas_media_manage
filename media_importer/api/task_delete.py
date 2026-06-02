import os

from media_importer.api import globals
from media_importer.core.db import delete_task as db_delete_task
from media_importer.core.safety import move_to_recycle

from .utils import json_response


def delete_task(handler, task_id: str, delete_files: bool = False,
                globals_module=None, respond=None):
    state = globals_module or globals
    write_response = respond or json_response

    task = state._global_task_manager.get_task(task_id)
    if task is None:
        write_response(handler, 404, message=f"Task not found: {task_id}")
        return

    current_status = task.get("status", "")
    if current_status == "PROCESSING":
        write_response(handler, 400, message="任务正在处理中，无法删除，请等待处理完成")
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

    temp_dir = state._config.get("temp_dir", "") if state._config else ""
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
        source_policy = state._config.get("source_policy", {}) if state._config else {}
        recycle_dir = source_policy.get("recycle_dir", "") or source_policy.get("quarantine_dir", "")
        source_dir = state._config.get("source_dir", "") if state._config else ""
        import_dirs = []
        for rule in (state._config.get("path_rules", []) if state._config else []):
            tpl = rule.get("template", "")
            if tpl:
                import_dirs.append(tpl)

        recycled_files = []

        if file_location == "source":
            sp = task.get("source_path", "")
            if sp:
                if os.path.exists(sp):
                    ok, _, _ = move_to_recycle(
                        sp, recycle_dir, reason="task_delete",
                        task_id=task_id, source_dir=source_dir,
                        import_roots=import_dirs)
                    if ok:
                        recycled_files.append(os.path.basename(sp))
                    else:
                        missing_files.append(os.path.basename(sp))
                else:
                    missing_files.append(os.path.basename(sp))
            for sub in (task.get("subtitle_files") or []):
                sub_str = str(sub) if sub else ""
                if sub_str:
                    if os.path.exists(sub_str):
                        ok, _, _ = move_to_recycle(
                            sub_str, recycle_dir, reason="task_delete",
                            task_id=task_id, source_dir=source_dir,
                            import_roots=import_dirs)
                        if ok:
                            recycled_files.append(os.path.basename(sub_str))
                    else:
                        missing_files.append(os.path.basename(sub_str))

        elif file_location == "temp":
            pass

        elif file_location == "import":
            ivp = task.get("import_video_path", "")
            if ivp:
                if os.path.exists(ivp):
                    ok, _, _ = move_to_recycle(
                        ivp, recycle_dir, reason="task_delete",
                        task_id=task_id, source_dir=source_dir,
                        import_roots=import_dirs)
                    if ok:
                        recycled_files.append(os.path.basename(ivp))
                    else:
                        missing_files.append(os.path.basename(ivp))
                else:
                    missing_files.append(os.path.basename(ivp))
            for sub in (task.get("subtitle_files") or []):
                sub_str = str(sub) if sub else ""
                if sub_str:
                    if os.path.exists(sub_str):
                        ok, _, _ = move_to_recycle(
                            sub_str, recycle_dir, reason="task_delete",
                            task_id=task_id, source_dir=source_dir,
                            import_roots=import_dirs)
                        if ok:
                            recycled_files.append(os.path.basename(sub_str))
                    else:
                        missing_files.append(os.path.basename(sub_str))

        elif file_location == "recycle":
            pass

        deleted_files.extend(recycled_files)

    db_delete_task(state._global_task_manager.conn, task_id)

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

    write_response(handler, 200, data=result, message="，".join(msg_parts))
