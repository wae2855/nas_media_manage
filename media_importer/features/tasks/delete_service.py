import os
from dataclasses import dataclass, field

from media_importer.features.recycle import move_to_recycle
from media_importer.features.tasks.repository import delete_task as delete_task_record


@dataclass
class DeleteTaskResult:
    status_code: int
    message: str
    data: dict = field(default_factory=dict)


def delete_task(task_manager, config: dict, task_id: str, delete_files: bool = False) -> DeleteTaskResult:
    task = task_manager.get_task(task_id)
    if task is None:
        return DeleteTaskResult(404, f"Task not found: {task_id}")

    current_status = task.get("status", "")
    current_stage = task.get("stage", "")
    if current_status == "PENDING" and current_stage == "RUNNING":
        return DeleteTaskResult(400, "任务正在处理中，无法删除，请等待处理完成")

    deleted_files = []
    missing_files = []
    file_location = task.get("file_location", "source")

    deleted_files.extend(_cleanup_temp_files(task, config, file_location, missing_files))

    if delete_files:
        deleted_files.extend(
            _recycle_task_files(task, config, task_id, file_location, missing_files)
        )

    delete_task_record(task_manager.conn, task_id)

    result = {"deleted": task_id, "file_location": file_location}
    message_parts = ["任务已删除"]

    if deleted_files:
        result["deleted_files"] = deleted_files
        message_parts.append(f"已删除 {len(deleted_files)} 个{_location_label(file_location)}")

    if missing_files and delete_files:
        result["missing_files"] = missing_files
        message_parts.append(f"{len(missing_files)} 个文件已不存在")

    return DeleteTaskResult(200, "，".join(message_parts), result)


def _cleanup_temp_files(task: dict, config: dict, file_location: str, missing_files: list) -> list:
    if file_location != "temp":
        return []

    temp_files = []
    video_path = task.get("video_path", "")
    if video_path:
        _append_existing_or_missing(video_path, temp_files, missing_files)

    for subtitle in task.get("subtitle_files") or []:
        subtitle_path = str(subtitle) if subtitle else ""
        if subtitle_path:
            _append_existing_or_missing(subtitle_path, temp_files, missing_files)

    deleted_files = []
    temp_dir = config.get("temp_dir", "") if config else ""
    for path in temp_files:
        try:
            path_abs = os.path.abspath(path)
            if temp_dir and path_abs.startswith(os.path.abspath(temp_dir) + os.sep):
                if os.path.exists(path):
                    os.remove(path)
                    deleted_files.append(os.path.basename(path))
                else:
                    missing_files.append(os.path.basename(path))
        except OSError:
            pass
    return deleted_files


def _recycle_task_files(task: dict, config: dict, task_id: str, file_location: str, missing_files: list) -> list:
    source_policy = config.get("source_policy", {}) if config else {}
    recycle_dir = source_policy.get("recycle_dir", "") or source_policy.get("quarantine_dir", "")
    source_dir = config.get("source_dir", "") if config else ""
    import_dirs = [
        rule.get("template", "")
        for rule in (config.get("path_rules", []) if config else [])
        if rule.get("template", "")
    ]

    if file_location == "source":
        paths = [task.get("source_path", "")]
        paths.extend(str(sub) if sub else "" for sub in (task.get("subtitle_files") or []))
        return _recycle_existing_paths(paths, recycle_dir, task_id, source_dir, import_dirs, missing_files)

    if file_location == "import":
        paths = [task.get("import_video_path", "")]
        paths.extend(str(sub) if sub else "" for sub in (task.get("subtitle_files") or []))
        return _recycle_existing_paths(paths, recycle_dir, task_id, source_dir, import_dirs, missing_files)

    return []


def _recycle_existing_paths(paths: list, recycle_dir: str, task_id: str, source_dir: str,
                            import_dirs: list, missing_files: list) -> list:
    recycled_files = []
    for path in paths:
        if not path:
            continue
        if os.path.exists(path):
            ok, _, _ = move_to_recycle(
                path,
                recycle_dir,
                reason="task_delete",
                task_id=task_id,
                source_dir=source_dir,
                import_roots=import_dirs,
            )
            if ok:
                recycled_files.append(os.path.basename(path))
            else:
                missing_files.append(os.path.basename(path))
        else:
            missing_files.append(os.path.basename(path))
    return recycled_files


def _append_existing_or_missing(path: str, existing: list, missing: list):
    if os.path.exists(path):
        existing.append(path)
    else:
        missing.append(os.path.basename(path))


def _location_label(file_location: str) -> str:
    return {
        "source": "源文件",
        "recycle": "回收站文件",
        "import": "入库文件",
        "temp": "中转文件",
    }.get(file_location, "文件")
