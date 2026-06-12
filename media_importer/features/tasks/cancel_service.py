from dataclasses import dataclass
from typing import Optional


@dataclass
class TaskCancelResult:
    code: int
    data: Optional[dict] = None
    message: str = ""


def cancel_task_for_api(task_manager, task_id: str, reason: str = "用户取消", logger=None) -> TaskCancelResult:
    if not task_manager:
        return TaskCancelResult(code=500, message="TaskManager unavailable")

    result = task_manager.cancel_task(task_id, reason=reason)
    if result is None:
        return TaskCancelResult(code=404, message=f"Task not found: {task_id}")
    if isinstance(result, dict) and result.get("error"):
        if logger:
            logger.warning(result["error"])
        return TaskCancelResult(code=400, message=result["error"])
    return TaskCancelResult(
        code=200,
        data={"task": result},
        message="任务已取消",
    )
