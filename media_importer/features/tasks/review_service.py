from dataclasses import dataclass
from typing import Optional

from media_importer.core.db.dimension_repo import get_enabled_dimensions


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


def reclassify_task_for_api(pipeline, task_id: str, dimensions: dict,
                            task_manager=None) -> TaskReviewActionResult:
    if pipeline is None:
        return TaskReviewActionResult(code=500, message="Pipeline not initialized")
    if not dimensions:
        return TaskReviewActionResult(code=400, message="缺少 dimensions 参数")

    # 校验维度启用状态：拒绝已禁用的维度名
    if task_manager is not None and hasattr(task_manager, 'conn'):
        enabled = {d["name"] for d in get_enabled_dimensions(task_manager.conn)}
        invalid = set(dimensions.keys()) - enabled
        if invalid:
            return TaskReviewActionResult(
                code=400,
                message=f"维度已禁用，无法修改: {', '.join(sorted(invalid))}",
            )

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
    status: str = "PENDING",
    stage: str = "AWAIT_REVIEW",
    limit: int = 1000,
) -> TaskReviewActionResult:
    if pipeline is None:
        return TaskReviewActionResult(code=500, message="Pipeline not initialized")
    if task_manager is None:
        return TaskReviewActionResult(code=500, message="TaskManager not initialized")

    confirming_tasks = task_manager.list_tasks(status=status, limit=limit, stage=stage)
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