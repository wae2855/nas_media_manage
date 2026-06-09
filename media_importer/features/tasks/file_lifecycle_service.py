import os
from dataclasses import dataclass
from typing import Optional

from media_importer.features.tasks.repository import (
    update_subtitles_by_task as update_subtitles_by_task_record,
    update_task as update_task_record,
)


@dataclass
class TaskFileLifecycleResult:
    code: int
    data: Optional[dict] = None
    message: str = ""


def rename_task_file_for_api(task_manager, task_id: str, new_filename: str) -> TaskFileLifecycleResult:
    normalized_filename = (new_filename or "").strip()
    if not normalized_filename:
        return TaskFileLifecycleResult(code=400, message="new_filename 参数必填")
    if not _is_plain_filename(normalized_filename):
        return TaskFileLifecycleResult(code=400, message="new_filename 只能是文件名，不能包含路径")

    task = task_manager.get_task(task_id) if task_manager else None
    if task is None:
        return TaskFileLifecycleResult(code=404, message=f"Task not found: {task_id}")

    file_location = task.get("file_location", "source")
    if file_location == "deleted":
        return TaskFileLifecycleResult(code=400, message="文件已删除，无法重命名")

    current_path = _current_file_path(task, file_location)
    if not current_path or not os.path.exists(current_path):
        return TaskFileLifecycleResult(code=400, message=f"当前文件路径不存在: {current_path}")

    current_dir = os.path.dirname(current_path)
    new_path = os.path.join(current_dir, normalized_filename)
    if os.path.exists(new_path) and new_path != current_path:
        return TaskFileLifecycleResult(code=400, message=f"目标文件名已存在: {normalized_filename}")

    try:
        os.rename(current_path, new_path)
    except OSError as exc:
        return TaskFileLifecycleResult(code=500, message=f"重命名失败: {exc}")

    update_fields = _rename_update_fields(file_location, normalized_filename, new_path)
    update_task_record(task_manager.conn, task_id, **update_fields)
    updated_task = task_manager.get_task(task_id)
    return TaskFileLifecycleResult(
        code=200,
        data={"task": updated_task},
        message="文件重命名成功",
    )


def ignore_task_for_api(task_manager, config: dict, task_id: str) -> TaskFileLifecycleResult:
    task = task_manager.get_task(task_id) if task_manager else None
    if task is None:
        return TaskFileLifecycleResult(code=404, message=f"Task not found: {task_id}")

    current_status = task.get("status", "")
    current_stage = task.get("stage", "")
    allowed = (current_status == "FAILED") or (current_status == "PENDING" and current_stage == "AWAIT_REVIEW")
    if not allowed:
        return TaskFileLifecycleResult(code=400, message=f"当前状态不可忽略: {current_status}")

    source_policy = config.get("source_policy", {}) if config else {}
    recycle_dir = source_policy.get("recycle_dir", "") or source_policy.get("quarantine_dir", "")
    cleanup = source_policy.get("cleanup_source_after_done", True)
    file_location = task.get("file_location", "source")

    if file_location == "temp":
        _cleanup_temp_task_files(task, config)
        update_subtitles_by_task_record(
            task_manager.conn,
            task_id,
            status="FAILED",
            target_path="",
        )
        _ignore_temp_task(task_manager, task, task_id, cleanup, recycle_dir)
    else:
        _ignore_non_temp_task(task_manager, task, task_id, cleanup, recycle_dir)

    return TaskFileLifecycleResult(code=200, message="任务已忽略")


def _is_plain_filename(filename: str) -> bool:
    if filename in (".", ".."):
        return False
    if os.path.isabs(filename):
        return False
    return "/" not in filename and "\\" not in filename


def _current_file_path(task: dict, file_location: str) -> str:
    if file_location == "import":
        return task.get("import_video_path", "")
    if file_location == "temp":
        return task.get("video_path", "")
    return task.get("source_path", "")


def _rename_update_fields(file_location: str, new_filename: str, new_path: str) -> dict:
    update_fields = {"source_filename": new_filename}
    if file_location == "import":
        update_fields["import_video_path"] = new_path
        update_fields["final_filename"] = new_filename
    elif file_location == "temp":
        update_fields["video_path"] = new_path
    elif file_location in ("source", "recycle"):
        update_fields["source_path"] = new_path
    return update_fields


def _cleanup_temp_task_files(task: dict, config: dict):
    temp_dir = config.get("temp_dir", "") if config else ""
    _remove_temp_path(task.get("video_path", ""), temp_dir)
    for subtitle in task.get("subtitle_files") or []:
        _remove_temp_path(str(subtitle) if subtitle else "", temp_dir)


def _remove_temp_path(path: str, temp_dir: str):
    if not path or not temp_dir or not _is_path_under_dir(path, temp_dir):
        return
    if not os.path.exists(path):
        return
    try:
        os.remove(path)
    except OSError:
        pass


def _is_path_under_dir(path: str, base_dir: str) -> bool:
    path_abs = os.path.abspath(path)
    base_abs = os.path.abspath(base_dir)
    return path_abs.startswith(base_abs + os.sep)


def _ignore_temp_task(task_manager, task: dict, task_id: str, cleanup: bool, recycle_dir: str):
    source_path = task.get("source_path", "")
    subtitle_paths = task.get("subtitle_files", [])
    if cleanup and recycle_dir and source_path and os.path.exists(source_path):
        _move_task_files_to_recycle(task_manager, task_id, source_path, subtitle_paths, recycle_dir)
        update_task_record(
            task_manager.conn,
            task_id,
            status="SKIPPED",
            stage="DONE",
            skip_reason="用户忽略",
            file_location="recycle",
            video_path="",
            error_message=f"已移入回收站: {recycle_dir}",
        )
    else:
        update_task_record(
            task_manager.conn,
            task_id,
            status="SKIPPED",
            stage="DONE",
            skip_reason="用户忽略",
            file_location="source",
            video_path="",
        )


def _ignore_non_temp_task(task_manager, task: dict, task_id: str, cleanup: bool, recycle_dir: str):
    source_path = task.get("source_path", "")
    subtitle_paths = task.get("subtitle_files", [])
    if cleanup and recycle_dir and source_path and os.path.exists(source_path):
        _move_task_files_to_recycle(task_manager, task_id, source_path, subtitle_paths, recycle_dir)
        update_task_record(
            task_manager.conn,
            task_id,
            status="SKIPPED",
            stage="DONE",
            skip_reason="用户忽略",
            error_message=f"已移入回收站: {recycle_dir}",
        )
    else:
        update_task_record(
            task_manager.conn,
            task_id,
            status="SKIPPED",
            stage="DONE",
            skip_reason="用户忽略",
        )


def _move_task_files_to_recycle(
    task_manager,
    task_id: str,
    source_path: str,
    subtitle_paths,
    recycle_dir: str,
):
    task_manager.move_to_recycle_bin(
        task_id=task_id,
        source_path=source_path,
        subtitle_paths=subtitle_paths if isinstance(subtitle_paths, list) else [],
        recycle_dir=recycle_dir,
    )
