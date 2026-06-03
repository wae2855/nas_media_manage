import os
from dataclasses import dataclass
from typing import Optional

from media_importer.features.tasks.repository import update_task as update_task_record


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
