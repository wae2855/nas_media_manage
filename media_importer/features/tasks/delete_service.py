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

    current_status = str(task.get("status", "")).upper()
    if current_status == "PENDING":
        return DeleteTaskResult(
            400,
            "任务尚未结束，请先使用“结束处理”决定新资源如何处理",
        )

    if delete_files:
        from media_importer.features.tasks.disposition_service import (
            LOCAL_RECYCLE,
            request_task_disposition,
        )

        disposed = request_task_disposition(
            task_manager,
            config,
            task_id,
            source_disposition=LOCAL_RECYCLE,
        )
        if disposed.code != 200:
            return DeleteTaskResult(disposed.code, disposed.message, disposed.data)
        task = task_manager.get_task(task_id) or task

    deleted_files = []
    missing_files = []
    file_location = task.get("file_location", "source")

    if delete_files and (
        file_location == "import" or _task_references_library_file(task, config)
    ):
        return DeleteTaskResult(
            400,
            "片库文件受保护：删除任务只能删除记录，不能删除或移走片库文件",
        )

    delete_task_record(task_manager.conn, task_id)

    result = {"deleted": task_id, "file_location": file_location}
    message_parts = [
        "任务记录已删除，片库文件未改动"
        if delete_files
        else "任务记录已删除，来源与片库文件均未因删除记录而改动"
    ]

    if deleted_files:
        result["deleted_files"] = deleted_files
        message_parts.append(f"已删除 {len(deleted_files)} 个{_location_label(file_location)}")

    if missing_files and delete_files:
        result["missing_files"] = missing_files
        message_parts.append(f"{len(missing_files)} 个文件已不存在")

    return DeleteTaskResult(200, "，".join(message_parts), result)


def _recycle_task_files(task: dict, config: dict, task_id: str, file_location: str, missing_files: list) -> list:
    source_policy = config.get("source_policy", {}) if config else {}
    recycle_dir = source_policy.get("recycle_dir", "") or source_policy.get("quarantine_dir", "")
    source_dir = config.get("source_dir", "") if config else ""
    from media_importer.features.configuration.storage_topology import (
        configured_library_roots,
    )

    import_dirs = configured_library_roots(config or {})

    if file_location == "source":
        paths = [task.get("source_path", "")]
        paths.extend(str(sub) if sub else "" for sub in (task.get("subtitle_files") or []))
        return _recycle_existing_paths(paths, recycle_dir, task_id, source_dir, import_dirs, missing_files)

    return []


def _task_references_library_file(task: dict, config: dict) -> bool:
    from media_importer.features.configuration.storage_topology import path_in_library

    paths = [
        task.get("source_path", ""),
        task.get("video_path", ""),
        task.get("import_video_path", ""),
    ]
    paths.extend(str(item) for item in (task.get("subtitle_files") or []) if item)
    return any(path and path_in_library(config or {}, path) for path in paths)


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


def _location_label(file_location: str) -> str:
    return {
        "source": "源文件",
        "recycle": "回收站文件",
        "import": "入库文件",
    }.get(file_location, "文件")
