from dataclasses import dataclass
from typing import Optional


@dataclass
class TaskReviewActionResult:
    code: int
    data: Optional[dict] = None
    message: str = ""


def confirm_task_for_api(pipeline, task_manager, task_id: str) -> TaskReviewActionResult:
    if pipeline is None:
        return TaskReviewActionResult(code=500, message="Pipeline not initialized")

    try:
        ok = pipeline.confirm_task(task_id)
        if ok:
            return TaskReviewActionResult(code=200, message="任务确认入库成功")

        task = task_manager.get_task(task_id) if task_manager else None
        error_message = task.get("error_message", "") if task else ""
        return TaskReviewActionResult(
            code=500,
            message="确认入库失败" + (f": {error_message}" if error_message else ""),
        )
    except Exception as exc:
        return TaskReviewActionResult(code=400, message=str(exc))


def reclassify_task_for_api(pipeline, task_id: str, dimensions: dict) -> TaskReviewActionResult:
    if pipeline is None:
        return TaskReviewActionResult(code=500, message="Pipeline not initialized")
    if not dimensions:
        return TaskReviewActionResult(code=400, message="缺少 dimensions 参数")

    try:
        task = pipeline.reclassify_task(task_id, dimensions)
        return TaskReviewActionResult(
            code=200,
            data={"task": task},
            message="重新分类完成",
        )
    except Exception as exc:
        return TaskReviewActionResult(code=400, message=str(exc))


def confirm_all_tasks_for_api(
    pipeline,
    task_manager,
    status: str = "CONFIRMING",
    limit: int = 1000,
) -> TaskReviewActionResult:
    if pipeline is None:
        return TaskReviewActionResult(code=500, message="Pipeline not initialized")
    if task_manager is None:
        return TaskReviewActionResult(code=500, message="TaskManager not initialized")

    confirming_tasks = task_manager.list_tasks(status=status, limit=limit)
    results = []
    for task in confirming_tasks:
        task_id = task.get("task_id", "")
        try:
            ok = pipeline.confirm_task(task_id)
            results.append({"task_id": task_id, "success": ok})
        except Exception as exc:
            results.append({"task_id": task_id, "success": False, "error": str(exc)})

    success_count = sum(1 for result in results if result["success"])
    failed_count = len(results) - success_count
    return TaskReviewActionResult(
        code=200,
        data={
            "results": results,
            "total": len(results),
            "success": success_count,
            "failed": failed_count,
        },
        message=f"批量确认完成: 成功 {success_count}, 失败 {failed_count}",
    )
