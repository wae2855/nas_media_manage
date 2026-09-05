"""State-aware task exit and exact source-package disposition."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime

from media_importer.features.configuration.storage_topology import (
    configured_library_roots,
    path_in_library,
    path_within,
)
from media_importer.features.operation_locks import serialize_source_disposition
from media_importer.features.recycle import move_to_recycle
from media_importer.features.source_files.permanent_delete import (
    permanently_delete_source_members,
)
from media_importer.infrastructure.db import (
    get_subtitles_by_task,
    update_subtitle,
    update_subtitles_by_task,
    update_task,
)

KEEP = "keep"
LOCAL_RECYCLE = "local_recycle"
PERMANENT_DELETE = "permanent_delete"
VALID_SOURCE_DISPOSITIONS = frozenset({KEEP, LOCAL_RECYCLE, PERMANENT_DELETE})


@dataclass(frozen=True)
class TaskDispositionResult:
    code: int
    message: str
    data: dict = field(default_factory=dict)


@serialize_source_disposition(
    lambda task_manager, _config, task_id, **_kwargs: (
        ((task_manager.get_task(task_id) if task_manager else None) or {}).get("source_unit_id")
        or f"task:{task_id}"
    )
)
def request_task_disposition(
    task_manager,
    config: dict,
    task_id: str,
    *,
    source_disposition: str = KEEP,
) -> TaskDispositionResult:
    """End a task and explicitly decide what happens to its source package."""

    if task_manager is None:
        return TaskDispositionResult(500, "任务服务尚未就绪")
    disposition = str(source_disposition or KEEP).strip().lower()
    if disposition not in VALID_SOURCE_DISPOSITIONS:
        return TaskDispositionResult(400, "来源处理方式无效")

    task = task_manager.get_task(task_id)
    if task is None:
        return TaskDispositionResult(404, f"任务不存在: {task_id}")

    source_unit_id = str(task.get("source_unit_id") or "")
    if source_unit_id:
        from media_importer.infrastructure.db import get_source_unit

        unit = get_source_unit(task_manager.conn, source_unit_id)
        if unit and unit.get("state") in {"RECYCLING", "DELETING", "RECYCLED", "DELETED"}:
            return TaskDispositionResult(
                409,
                "该来源单元正在统一处理或已处理完成，不能再改为保留/重试；请刷新任务查看最终结果",
            )

    protected = _protected_task_reason(task, config, disposition)
    if protected:
        return TaskDispositionResult(400, protected)

    status = str(task.get("status", "")).upper()
    stage = str(task.get("stage", "")).upper()
    if status == "SUCCESS":
        return TaskDispositionResult(
            400,
            "影片已经入库完成；这里不能处理片库文件，如需隐藏历史请使用“删除记录”",
        )

    if status == "PENDING" and stage == "RUNNING":
        if task.get("bundle_committed") or task.get("import_success"):
            return TaskDispositionResult(
                409,
                "影片文件包已经提交到片库，现阶段不能停止；系统会完成安全收尾",
            )
        requested_at = datetime.now().isoformat()
        updated = update_task(
            task_manager.conn,
            task_id,
            cancel_requested=1,
            stop_requested_at=requested_at,
            requested_source_disposition=disposition,
            outcome_code="STOP_REQUESTED",
            source_disposition="pending",
            source_disposition_message="等待当前安全步骤停止后处理来源",
            error_message="用户已请求停止，正在等待安全检查点",
        )
        return TaskDispositionResult(
            202,
            "停止请求已提交；系统会在安全检查点停止，再按你的选择处理新资源",
            {"task": updated, "pending": True},
        )

    if status == "PENDING" and stage not in {"QUEUED", "AWAIT_REVIEW"}:
        return TaskDispositionResult(400, f"当前任务状态暂时不能结束: {status}/{stage}")

    return _complete_disposition(
        task_manager,
        config,
        task,
        disposition,
        from_running=False,
    )


def complete_requested_stop(task_manager, config: dict, task_id: str) -> TaskDispositionResult:
    """Called by the worker after it unwinds to a safe pre-commit point."""

    task = task_manager.get_task(task_id) if task_manager else None
    if task is None:
        return TaskDispositionResult(404, f"任务不存在: {task_id}")
    if not task.get("cancel_requested"):
        return TaskDispositionResult(409, "任务没有待完成的停止请求")
    if task.get("bundle_committed") or task.get("import_success"):
        updated = update_task(
            task_manager.conn,
            task_id,
            cancel_requested=0,
            requested_source_disposition="",
            outcome_code="STOP_REJECTED_COMMITTED",
            source_disposition="keep",
            source_disposition_message="片库文件包已提交，已继续完成安全收尾",
            error_message="",
        )
        return TaskDispositionResult(
            409,
            "片库文件包已经提交，停止请求未执行，任务将继续完成",
            {"task": updated},
        )
    disposition = str(task.get("requested_source_disposition") or KEEP)
    return _complete_disposition(
        task_manager,
        config,
        task,
        disposition,
        from_running=True,
    )


def task_stop_requested(task_manager, task_id: str) -> bool:
    task = task_manager.get_task(task_id) if task_manager else None
    if not task or not task.get("cancel_requested"):
        return False
    return not bool(task.get("bundle_committed") or task.get("import_success"))


def _complete_disposition(
    task_manager,
    config: dict,
    task: dict,
    disposition: str,
    *,
    from_running: bool,
) -> TaskDispositionResult:
    task_id = str(task.get("task_id", ""))
    status = str(task.get("status", "")).upper()
    stage = str(task.get("stage", "")).upper()

    source_result = _dispose_source_package(task_manager, config, task, disposition)
    target_status = status
    outcome = "SOURCE_DISPOSITION_UPDATED"
    if status == "PENDING" and stage == "QUEUED":
        target_status = "CANCELLED"
        outcome = "USER_CANCELLED"
    elif from_running:
        target_status = "CANCELLED"
        outcome = "USER_STOPPED"
    elif status == "PENDING" and stage == "AWAIT_REVIEW":
        target_status = "SKIPPED"
        outcome = "USER_ABANDONED"
    elif status == "FAILED":
        target_status = "SKIPPED"
        outcome = "USER_ABANDONED_AFTER_FAILURE"
    elif status in {"SKIPPED", "CANCELLED"}:
        outcome = "SOURCE_DISPOSITION_UPDATED"

    source_state = source_result["state"]
    message = source_result["message"]
    fields = {
        "status": target_status,
        "stage": "DONE",
        "cancel_requested": 0,
        "requested_source_disposition": "",
        "outcome_code": outcome,
        "source_disposition": source_state,
        "source_disposition_message": message,
        "completed_at": task.get("completed_at") or datetime.now().isoformat(),
        "skip_reason": _outcome_label(outcome, source_state),
        "error_message": message if source_state == "failed" else "",
    }
    if source_state == "recycled":
        fields["file_location"] = "recycle"
    elif source_state in {"deleted", "missing"}:
        fields["file_location"] = "deleted"
        fields["video_path"] = ""
    else:
        fields["file_location"] = "source"
    updated = update_task(task_manager.conn, task_id, **fields)
    if source_state in {"recycled", "deleted", "missing"}:
        update_subtitles_by_task(task_manager.conn, task_id, status="SKIPPED")

    code = 200 if source_state != "failed" else 409
    user_message = _result_message(outcome, source_state, message)
    return TaskDispositionResult(
        code,
        user_message,
        {
            "task": updated,
            "source_disposition": source_state,
            "source_message": message,
        },
    )


def _dispose_source_package(task_manager, config: dict, task: dict, disposition: str) -> dict:
    if disposition == KEEP:
        return {"state": "kept", "message": "新资源保留在来源目录，片库文件未改动"}

    try:
        members = _source_members(task_manager, task, config)
    except ValueError as exc:
        return {"state": "failed", "message": f"来源边界检查未通过，已保留文件：{exc}"}
    existing = [path for path in members if os.path.exists(path)]
    if not existing:
        return {"state": "missing", "message": "来源文件已不存在；片库文件未改动"}

    if disposition == PERMANENT_DELETE:
        policy = config.get("source_policy", {}) or {}
        if (
            policy.get("disposal_mode") != PERMANENT_DELETE
            or policy.get("mode") == "preserve_all"
        ):
            return {
                "state": "failed",
                "message": "永久删除未在文件来源配置中启用，已保留全部来源文件",
            }
        source_root = str(config.get("source_dir", "") or "")
        ledger_dir = os.path.join(
            str(config.get("_data_dir") or source_root),
            "source_delete_ledgers",
        )
        result = permanently_delete_source_members(
            existing,
            source_root=source_root,
            operation_id=f"task-dispose-{task.get('task_id', '')}",
            ledger_dir=ledger_dir,
            protected_roots=configured_library_roots(config),
        )
        return {
            "state": "deleted" if result.ok else "failed",
            "message": result.message,
        }

    policy = config.get("source_policy", {}) or {}
    recycle_dir = str(policy.get("recycle_dir") or policy.get("quarantine_dir") or "")
    source_root = str(config.get("source_dir", "") or "")
    moved: dict[str, str] = {}
    failures = []
    for path in existing:
        ok, target, message = move_to_recycle(
            path,
            recycle_dir,
            reason="task_abandoned_source",
            task_id=str(task.get("task_id", "")),
            source_dir=source_root,
            import_roots=configured_library_roots(config),
        )
        if ok:
            moved[path] = target
        else:
            failures.append(message or f"无法回收 {os.path.basename(path)}")
    _update_recycled_member_paths(task_manager, task, moved)
    if failures:
        return {
            "state": "failed",
            "message": "部分来源未能移入回收区，任务记录已保留：" + "；".join(failures),
        }
    return {
        "state": "recycled",
        "message": f"本次新资源共 {len(moved)} 个文件已移入本地回收区，可恢复",
    }


def _source_members(task_manager, task: dict, config: dict) -> list[str]:
    source_root = str(config.get("source_dir", "") or "")
    raw = [str(task.get("source_path", "") or "")]
    raw.extend(
        str(row.get("source_path", "") or "")
        for row in get_subtitles_by_task(task_manager.conn, str(task.get("task_id", "")))
    )
    result = []
    seen = set()
    for path in raw:
        if not path or path in seen:
            continue
        seen.add(path)
        if not source_root or not path_within(path, source_root, allow_root=False):
            raise ValueError(f"来源成员不在当前来源目录内: {path}")
        if path_in_library(config, path):
            raise ValueError("来源成员落入目标片库，禁止处理")
        if os.path.islink(path):
            raise ValueError(f"来源成员是符号链接，禁止处理: {path}")
        result.append(path)
    return result


def _update_recycled_member_paths(task_manager, task: dict, moved: dict[str, str]) -> None:
    task_id = str(task.get("task_id", ""))
    video_source = str(task.get("source_path", "") or "")
    if video_source in moved:
        update_task(
            task_manager.conn,
            task_id,
            source_path=moved[video_source],
            source_filename=os.path.basename(moved[video_source]),
        )
    for row in get_subtitles_by_task(task_manager.conn, task_id):
        source = str(row.get("source_path", "") or "")
        if source in moved:
            update_subtitle(
                task_manager.conn,
                row["id"],
                target_path=moved[source],
                status="SKIPPED",
            )


def _protected_task_reason(task: dict, config: dict, disposition: str) -> str:
    if disposition == KEEP:
        return ""
    if task.get("task_kind") == "REORGANIZE":
        return "重新整理任务使用片库现有文件；只能结束任务，不能处理来源文件"
    source_path = str(task.get("source_path", "") or "")
    if source_path and path_in_library(config, source_path):
        return "片库文件受保护：当前任务来源位于目标片库，不能通过结束任务处理文件"
    return ""


def _outcome_label(outcome: str, source_state: str) -> str:
    labels = {
        "USER_CANCELLED": "用户取消排队任务",
        "USER_STOPPED": "用户安全停止任务",
        "USER_ABANDONED": "用户放弃本次整理",
        "USER_ABANDONED_AFTER_FAILURE": "用户不再处理失败任务",
        "SOURCE_DISPOSITION_UPDATED": "来源处理结果已更新",
    }
    suffix = {
        "kept": "新资源已保留",
        "recycled": "新资源已进入本地回收区",
        "deleted": "新资源已永久删除",
        "missing": "新资源已不存在",
        "failed": "来源处理未完成",
    }.get(source_state, source_state)
    return f"{labels.get(outcome, '任务已结束')}；{suffix}"


def _result_message(outcome: str, source_state: str, detail: str) -> str:
    if source_state == "failed":
        return f"任务已停止，但来源处理未完成：{detail}"
    prefix = {
        "USER_CANCELLED": "排队任务已取消",
        "USER_STOPPED": "任务已安全停止",
        "USER_ABANDONED": "本次整理已放弃",
        "USER_ABANDONED_AFTER_FAILURE": "失败任务已结束",
    }.get(outcome, "来源处理已更新")
    return f"{prefix}；{detail}"
