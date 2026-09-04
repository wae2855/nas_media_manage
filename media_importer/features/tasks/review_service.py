import threading
from dataclasses import dataclass
from typing import Optional

from media_importer.infrastructure.db import get_enabled_dimensions

from .series_batch_service import (
    discover_series_batch,
    queue_manual_provider_binding,
)


@dataclass
class TaskReviewActionResult:
    code: int
    data: Optional[dict] = None
    message: str = ""


_confirm_jobs: set[str] = set()
_confirm_jobs_lock = threading.Lock()


def apply_scrape_candidate_for_api(
    pipeline,
    task_id: str,
    selection: dict,
    *,
    task_manager=None,
    related_task_ids: Optional[list[str]] = None,
    thread_factory=threading.Thread,
) -> TaskReviewActionResult:
    if pipeline is None:
        return TaskReviewActionResult(code=500, message="Pipeline not initialized")
    required = ("provider_type", "item_id", "media_type")
    missing = [name for name in required if not str(selection.get(name, "")).strip()]
    if missing:
        return TaskReviewActionResult(
            code=400,
            message="缺少候选参数: " + ", ".join(missing),
        )
    if related_task_ids is not None and not isinstance(related_task_ids, list):
        return TaskReviewActionResult(code=400, message="related_task_ids 必须是数组")
    requested = list(
        dict.fromkeys(str(item) for item in (related_task_ids or []) if item)
    )
    if len(requested) > 50:
        return TaskReviewActionResult(code=400, message="单次最多套用 50 个任务")
    try:
        if task_manager is None:
            return TaskReviewActionResult(code=500, message="TaskManager not initialized")
        anchor = task_manager.get_task(task_id)
        if (
            not anchor
            or anchor.get("status") != "PENDING"
            or anchor.get("stage") != "AWAIT_REVIEW"
        ):
            return TaskReviewActionResult(
                code=400,
                message="只有等待人工确认的任务可以重新选择作品资料",
            )
        if anchor.get("task_kind") == "REORGANIZE":
            updated = pipeline.apply_scrape_candidate(task_id, **selection)
            return TaskReviewActionResult(
                code=200,
                data={
                    "task": updated,
                    "queued": [],
                    "bound_queued": [],
                    "processing_unchanged": [],
                    "skipped": [],
                    "failed": [],
                },
                message="作品资料已更新，请确认重新整理",
            )

        preview = (
            discover_series_batch(task_manager, task_id, selection)
            if str(selection.get("media_type")) == "tv"
            else {"tasks": [], "excluded": []}
        )
        preview_by_id = {
            str(item["task_id"]): item
            for item in preview["tasks"]
        }
        allowed = {
            item_id
            for item_id, item in preview_by_id.items()
            if item.get("selectable")
        }
        requested_set = set(requested)
        target_ids = [task_id]
        target_ids.extend(
            item["task_id"]
            for item in preview["tasks"]
            if item["task_id"] != task_id
            and item["task_id"] in requested_set
            and item.get("selectable")
        )
        skipped = [
            {"task_id": item, "reason": "not_in_safe_series_batch"}
            for item in requested
            if item not in allowed
        ]

        from media_importer.features.tasks.search_service import load_provider_candidate

        load_provider_candidate(
            pipeline.config,
            task_manager.conn,
            provider_type=str(selection["provider_type"]),
            item_id=str(selection["item_id"]),
            media_type=str(selection["media_type"]),
            language=str(selection.get("language", "") or "") or None,
        )
        queued = []
        bound_queued = []
        processing_unchanged = [
            {"task_id": item["task_id"], "reason": "processing_unchanged"}
            for item in preview["tasks"]
            if item.get("handling") == "processing_unchanged"
        ]
        failed = []
        anchor_task = None
        for target_id in target_ids:
            try:
                item = preview_by_id.get(target_id)
                if item:
                    season = item.get("season")
                    episode = item.get("episode")
                else:
                    result = anchor.get("scrape_result") or {}
                    dimensions = anchor.get("scrape_dimensions") or {}
                    season = result.get("season", dimensions.get("season"))
                    episode = result.get("episode", dimensions.get("episode"))
                task, outcome = queue_manual_provider_binding(
                    task_manager,
                    target_id,
                    selection,
                    season=season,
                    episode=episode,
                )
                if task is None:
                    if outcome == "processing_unchanged":
                        processing_unchanged.append(
                            {"task_id": target_id, "reason": outcome}
                        )
                    else:
                        failed.append({"task_id": target_id, "error": outcome})
                    continue
                target = {"task_id": target_id}
                if outcome == "bound_queued":
                    bound_queued.append(target)
                else:
                    queued.append(target)
                if target_id == task_id:
                    anchor_task = task
            except Exception as exc:
                failed.append({"task_id": target_id, "error": str(exc)})
        if anchor_task is None:
            return TaskReviewActionResult(
                code=400,
                data={
                    "queued": queued,
                    "bound_queued": bound_queued,
                    "processing_unchanged": processing_unchanged,
                    "skipped": skipped,
                    "failed": failed,
                },
                message="当前任务未能加入处理队列，请刷新后重试",
            )
        _start_manual_binding_processing(
            pipeline,
            task_manager,
            [item["task_id"] for item in queued + bound_queued],
            thread_factory=thread_factory,
        )
        return TaskReviewActionResult(
            code=200,
            data={
                "task": anchor_task,
                "queued": queued,
                "bound_queued": bound_queued,
                "processing_unchanged": processing_unchanged,
                "skipped": skipped,
                "failed": failed,
            },
            message=(
                f"已按人工选择继续处理：排队 {len(queued)} 项，"
                f"排队继承 {len(bound_queued)} 项，处理中未改写 "
                f"{len(processing_unchanged)} 项，跳过 {len(skipped)} 项，"
                f"失败 {len(failed)} 项"
            ),
        )
    except Exception as exc:
        return TaskReviewActionResult(code=400, message=str(exc))


def _start_manual_binding_processing(
    pipeline,
    task_manager,
    task_ids: list[str],
    *,
    thread_factory=threading.Thread,
) -> None:
    """Start selected queued tasks without bypassing the shared task slot or CAS."""

    process_one = getattr(pipeline, "process_one", None)
    if not callable(process_one) or not task_ids:
        return
    is_paused = getattr(pipeline, "is_paused", None)
    if callable(is_paused) and is_paused():
        return

    def run_selected() -> None:
        for queued_task_id in task_ids:
            task = task_manager.get_task(queued_task_id)
            if (
                not task
                or task.get("status") != "PENDING"
                or task.get("stage") != "QUEUED"
            ):
                continue
            process_one(task)

    thread_factory(target=run_selected, daemon=True).start()


def preview_series_batch_for_api(
    task_manager,
    task_id: str,
    selection: dict,
) -> TaskReviewActionResult:
    required = ("provider_type", "item_id", "media_type")
    missing = [name for name in required if not str(selection.get(name, "")).strip()]
    if missing:
        return TaskReviewActionResult(
            code=400,
            message="缺少候选参数: " + ", ".join(missing),
        )
    try:
        preview = discover_series_batch(task_manager, task_id, selection)
        return TaskReviewActionResult(code=200, data=preview)
    except Exception as exc:
        return TaskReviewActionResult(code=400, message=str(exc))


def confirm_task_for_api(pipeline, task_manager, task_id: str,
                         confirmed_title: Optional[str] = None,
                         override_source: Optional[str] = None,
                         conflict_action: Optional[str] = None,
                         fallback_acknowledged: bool = False) -> TaskReviewActionResult:
    if pipeline is None:
        return TaskReviewActionResult(code=500, message="Pipeline not initialized")

    try:
        confirm_kwargs = {
            "confirmed_title": confirmed_title,
            "override_source": override_source,
            "conflict_action": conflict_action,
        }
        if fallback_acknowledged:
            confirm_kwargs["fallback_acknowledged"] = True
        ok = pipeline.confirm_task(task_id, **confirm_kwargs)
        if ok:
            current = task_manager.get_task(task_id) if task_manager else None
            conflict = (current or {}).get("dedup_result") or {}
            if (
                (current or {}).get("stage") == "AWAIT_REVIEW"
                and conflict.get("is_duplicate")
                and conflict.get("status") == "awaiting_user"
            ):
                return TaskReviewActionResult(
                    code=200,
                    data={"requires_conflict_review": True},
                    message="发现片库中已有同一影片，现有文件未改动，请逐项选择处理方式",
                )
            return TaskReviewActionResult(code=200, message="任务确认入库成功")

        task = task_manager.get_task(task_id) if task_manager else None
        error_message = task.get("error_message", "") if task else ""
        return TaskReviewActionResult(
            code=500,
            message="确认入库失败" + (f": {error_message}" if error_message else ""),
        )
    except Exception as exc:
        return TaskReviewActionResult(code=400, message=str(exc))


def queue_confirm_task_for_api(
    pipeline,
    task_manager,
    task_id: str,
    confirmed_title: Optional[str] = None,
    override_source: Optional[str] = None,
    conflict_action: Optional[str] = None,
    source_disposition: Optional[str] = None,
    fallback_acknowledged: bool = False,
) -> TaskReviewActionResult:
    """快速返回，由服务端线程继续确认后的长文件流程。"""
    if pipeline is None:
        return TaskReviewActionResult(code=500, message="Pipeline not initialized")
    if task_manager is None:
        return TaskReviewActionResult(code=500, message="TaskManager not initialized")

    task = task_manager.get_task(task_id)
    if not task or task.get("status") != "PENDING" or task.get("stage") != "AWAIT_REVIEW":
        return TaskReviewActionResult(code=400, message="任务已不在等待确认状态，请刷新后重试")
    if task.get("task_kind") == "REORGANIZE" and task.get("used_fallback"):
        return TaskReviewActionResult(
            code=400,
            message="重新整理任务仍未匹配正式入库规则，请调整维度或重新刮削",
        )
    if task.get("used_fallback") and not fallback_acknowledged:
        return TaskReviewActionResult(
            code=400,
            message="该影片将进入待整理区，请先明确确认后再继续",
        )
    conflict = task.get("dedup_result") or {}
    has_conflict = bool(
        conflict.get("is_duplicate")
        and conflict.get("status") == "awaiting_user"
    )
    allowed_actions = {"keep_existing", "keep_both", "replace_existing"}
    if has_conflict and conflict_action not in allowed_actions:
        return TaskReviewActionResult(code=400, message="片库冲突必须先选择处理方式")
    if conflict_action == "replace_existing" and conflict.get("replace_allowed") is False:
        return TaskReviewActionResult(
            code=400,
            message="当前文件包包含字幕冲突，请选择保留片库文件或两个都保留",
        )
    if source_disposition and conflict_action != "keep_existing":
        return TaskReviewActionResult(
            code=400,
            message="只有选择保留片库现有文件时，才能同时处理本次新资源",
        )
    if source_disposition not in {None, "", "keep", "local_recycle", "permanent_delete"}:
        return TaskReviewActionResult(code=400, message="来源处理方式无效")

    with _confirm_jobs_lock:
        if task_id in _confirm_jobs:
            return TaskReviewActionResult(
                code=202,
                data={"queued": True, "task_id": task_id},
                message="任务已在后台处理中，请勿重复提交",
            )
        _confirm_jobs.add(task_id)

    def run_confirm_job():
        try:
            confirm_kwargs = {
                "confirmed_title": confirmed_title,
                "override_source": override_source,
                "conflict_action": conflict_action,
            }
            if source_disposition:
                confirm_kwargs["source_disposition"] = source_disposition
            if fallback_acknowledged:
                confirm_kwargs["fallback_acknowledged"] = True
            pipeline.confirm_task(task_id, **confirm_kwargs)
        finally:
            with _confirm_jobs_lock:
                _confirm_jobs.discard(task_id)

    try:
        threading.Thread(
            target=run_confirm_job,
            name=f"confirm-{task_id}",
            daemon=True,
        ).start()
    except Exception as exc:
        with _confirm_jobs_lock:
            _confirm_jobs.discard(task_id)
        return TaskReviewActionResult(code=500, message=f"后台任务启动失败: {exc}")

    return TaskReviewActionResult(
        code=202,
        data={"queued": True, "task_id": task_id},
        message="已加入后台队列，关闭页面也会继续处理",
    )


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


def preview_task_for_api(pipeline, task_id: str, updates: dict, task_manager=None) -> TaskReviewActionResult:
    if pipeline is None:
        return TaskReviewActionResult(code=500, message="Pipeline not initialized")
    if not updates:
        return TaskReviewActionResult(code=400, message="缺少更新参数")

    if task_manager is not None and hasattr(task_manager, 'conn'):
        if "dimensions" in updates:
            from media_importer.infrastructure.db import get_enabled_dimensions
            enabled = {d["name"] for d in get_enabled_dimensions(task_manager.conn)}
            invalid = set(updates["dimensions"].keys()) - enabled
            if invalid:
                return TaskReviewActionResult(
                    code=400,
                    message=f"维度已禁用，无法修改: {', '.join(sorted(invalid))}",
                )

    try:
        task = pipeline.preview_task(task_id, updates)
        return TaskReviewActionResult(
            code=200,
            data={"task": task},
            message="预览更新完成",
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
    conflict_skipped = 0
    for task in confirming_tasks:
        task_id = task.get("task_id", "")
        dedup_result = task.get("dedup_result") or {}
        requires_individual_review = bool(
            dedup_result.get("is_duplicate")
            and dedup_result.get("status") == "awaiting_user"
        ) or bool(task.get("used_fallback")) or task.get("task_kind") == "REORGANIZE"
        if requires_individual_review:
            conflict_skipped += 1
            results.append({
                "task_id": task_id,
                "success": False,
                "skipped": True,
                "error": "该任务必须打开详情逐项确认",
            })
            continue
        try:
            ok = pipeline.confirm_task(task_id, confirmed_title="", override_source="")
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
            "conflict_skipped": conflict_skipped,
        },
        message=f"批量确认完成: 成功 {success_count}, 未处理片库冲突 {conflict_skipped}, 其他失败 {failed_count - conflict_skipped}",
    )
