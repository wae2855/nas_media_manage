from dataclasses import dataclass, field

from media_importer.features.tasks.repository import get_subtitles_by_task


@dataclass
class TaskDetailResult:
    code: int
    data: dict = field(default_factory=dict)
    message: str = ""


def get_task_for_api(task_manager, task_id: str) -> TaskDetailResult:
    if task_manager is None:
        return TaskDetailResult(code=500, message="TaskManager not initialized")

    task = task_manager.get_task(task_id)
    if task is None:
        return TaskDetailResult(code=404, message=f"Task not found: {task_id}")

    public_task = dict(task)
    public_task.pop("bundle_manifest", None)
    return TaskDetailResult(code=200, data={"task": public_task})


def get_task_subtitles_for_api(task_manager, task_id: str) -> TaskDetailResult:
    if task_manager is None:
        return TaskDetailResult(code=500, message="TaskManager not initialized")

    subtitles = get_subtitles_by_task(task_manager.conn, task_id)
    return TaskDetailResult(
        code=200,
        data={"subtitles": subtitles, "total": len(subtitles)},
    )


def get_task_stats_for_api(task_manager) -> TaskDetailResult:
    if task_manager is None:
        return TaskDetailResult(code=500, message="TaskManager not initialized")

    return TaskDetailResult(
        code=200,
        data={"by_status": task_manager.count_by_status()},
    )
