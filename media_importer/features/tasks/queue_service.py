import threading
from dataclasses import dataclass
from typing import Callable, Optional

from media_importer.core.db import VALID_STATUSES


@dataclass
class TaskQueueActionResult:
    code: int
    data: Optional[dict] = None
    message: str = ""


def clear_tasks_for_api(task_manager, status: Optional[str], stage: Optional[str] = None, logger=None) -> TaskQueueActionResult:
    if task_manager is None:
        return TaskQueueActionResult(code=500, message="TaskManager not initialized")

    normalized_status = status
    if normalized_status:
        normalized_status = str(normalized_status).strip().upper()
    if normalized_status and normalized_status != "ALL" and normalized_status not in VALID_STATUSES:
        if logger:
            logger.warning(
                f"Invalid status filter: {normalized_status}, VALID_STATUSES={VALID_STATUSES}"
            )
        return TaskQueueActionResult(code=400, message=f"Invalid status: {normalized_status}")

    if normalized_status == "ALL":
        normalized_status = None

    task_manager.clear_tasks(status=normalized_status, stage=stage)
    return TaskQueueActionResult(
        code=200,
        data={"status": normalized_status or "all", "stage": stage},
        message="Tasks cleared",
    )


def retry_task_for_api(
    task_manager,
    pipeline,
    task_id: str,
    logger=None,
    thread_factory: Callable = threading.Thread,
) -> TaskQueueActionResult:
    if task_manager is None:
        return TaskQueueActionResult(code=500, message="TaskManager not initialized")

    task = task_manager.retry_task(task_id)
    if task is None:
        return TaskQueueActionResult(code=400, message=f"任务不存在或当前状态不可重试: {task_id}")

    if pipeline and not pipeline.is_paused():

        def run_retry():
            try:
                pipeline.process_one(task)
            except Exception as exc:
                if logger:
                    logger.error(f"重试任务执行异常: {exc}")

        thread = thread_factory(target=run_retry, daemon=True)
        thread.start()

    return TaskQueueActionResult(
        code=200,
        data={"task": task},
        message="任务已重试并开始执行",
    )


def retry_all_failed_for_api(
    task_manager,
    pipeline,
    logger=None,
    thread_factory: Callable = threading.Thread,
) -> TaskQueueActionResult:
    if task_manager is None:
        return TaskQueueActionResult(code=500, message="TaskManager not initialized")

    retried = task_manager.retry_all_failed()

    if retried and pipeline and not pipeline.is_paused():

        def run_retry_all():
            try:
                pipeline.run_all()
            except Exception as exc:
                if logger:
                    logger.error(f"批量重试执行异常: {exc}")

        thread = thread_factory(target=run_retry_all, daemon=True)
        thread.start()

    return TaskQueueActionResult(
        code=200,
        data={
            "retried_count": len(retried),
            "task_ids": [task.get("task_id", "") for task in retried],
        },
        message=f"已重试 {len(retried)} 个失败任务并开始执行",
    )


def pause_queue_for_api(pipeline, metrics) -> TaskQueueActionResult:
    if pipeline:
        pipeline.pause()
    if metrics:
        metrics.set_queue_paused(True)
    return TaskQueueActionResult(code=200, message="Queue paused")


def resume_queue_for_api(pipeline, metrics) -> TaskQueueActionResult:
    if pipeline:
        pipeline.resume()
    if metrics:
        metrics.set_queue_paused(False)
    return TaskQueueActionResult(code=200, message="Queue resumed")


def get_queue_status_for_api(pipeline, task_manager) -> TaskQueueActionResult:
    paused = pipeline.is_paused() if pipeline else False
    counts = task_manager.count_by_status() if task_manager else {}
    return TaskQueueActionResult(
        code=200,
        data={
            "paused": paused,
            "by_status": counts,
        },
    )
