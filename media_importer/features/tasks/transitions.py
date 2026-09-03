"""任务状态转换唯一事实源（Phase 2 / REQ-20260822-000004）。

设计（proposal: 2026-08-23-state-machine-redesign.md S1）：
- 转换表 TRANSITIONS 定义每个动作的合法源状态与目标状态；
- apply() 统一校验 + 生成字段，非法转换抛 TransitionError；
- file_location 诚实规则：任务只记录来源、片库或回收区，不暴露内部暂存；
- 全部状态写入（含 mark_* 兼容层）必须经本模块；负向测试由转换表自动生成。

ADR-0022：retry 总是从原始来源重启，不保留步骤或大文件断点。
"""
from __future__ import annotations

from datetime import datetime

# 状态常量（与 core/task_lifecycle 保持单一值集）
STATUS_PENDING = "PENDING"
STATUS_FAILED = "FAILED"
STATUS_SKIPPED = "SKIPPED"
STATUS_SUCCESS = "SUCCESS"
STATUS_CANCELLED = "CANCELLED"

STAGE_QUEUED = "QUEUED"
STAGE_RUNNING = "RUNNING"
STAGE_AWAIT_REVIEW = "AWAIT_REVIEW"
STAGE_DONE = "DONE"

FILE_LOCATION_SOURCE = "source"
FILE_LOCATION_IMPORT = "import"
FILE_LOCATION_RECYCLE = "recycle"

CONFIRM_NONE = "NONE"
CONFIRM_PENDING = "PENDING"
CONFIRM_CONFIRMED = "CONFIRMED"

# 活动态集合（非终结）
VALID_STAGES = frozenset({STAGE_QUEUED, STAGE_RUNNING, STAGE_AWAIT_REVIEW, STAGE_DONE})
VALID_STATUS = frozenset({
    STATUS_PENDING, STATUS_FAILED, STATUS_SKIPPED, STATUS_SUCCESS, STATUS_CANCELLED,
})

ACTIVE_STATES = frozenset({
    (STATUS_PENDING, STAGE_QUEUED),
    (STATUS_PENDING, STAGE_RUNNING),
    (STATUS_PENDING, STAGE_AWAIT_REVIEW),
})
# 终结态集合
TERMINAL_STATES = frozenset({
    (STATUS_SUCCESS, STAGE_DONE),
    (STATUS_FAILED, STAGE_DONE),
    (STATUS_SKIPPED, STAGE_DONE),
    (STATUS_CANCELLED, STAGE_DONE),
})
ALL_STATES = ACTIVE_STATES | TERMINAL_STATES


class TransitionError(Exception):
    """非法状态转换（动作与当前 status/stage 不匹配）。"""


def _now() -> str:
    return datetime.now().isoformat()


def _state(task) -> tuple:
    data = getattr(task, "raw", task)
    return (data.get("status", ""), data.get("stage", ""))


# ---------------------------------------------------------------------------
# 转换表：action -> (允许源状态, 目标状态)
# 前置合法性检查的唯一事实源；负向测试由此自动生成。
# ---------------------------------------------------------------------------
TRANSITIONS: dict = {
    # QUEUED -> RUNNING（runner 开始处理）
    "start": (frozenset({(STATUS_PENDING, STAGE_QUEUED)}), (STATUS_PENDING, STAGE_RUNNING)),
    # RUNNING 内部推进（进度更新，不改状态机位置）
    "step": (frozenset({(STATUS_PENDING, STAGE_RUNNING)}), (STATUS_PENDING, STAGE_RUNNING)),
    # RUNNING -> AWAIT_REVIEW（需人工确认/审核）
    "need_confirm": (frozenset({(STATUS_PENDING, STAGE_RUNNING)}), (STATUS_PENDING, STAGE_AWAIT_REVIEW)),
    "need_review": (frozenset({(STATUS_PENDING, STAGE_RUNNING)}), (STATUS_PENDING, STAGE_AWAIT_REVIEW)),
    # AWAIT_REVIEW 内部注记（确认状态字段，不改 stage）
    "confirm_mark": (frozenset({(STATUS_PENDING, STAGE_AWAIT_REVIEW)}), (STATUS_PENDING, STAGE_AWAIT_REVIEW)),
    # 确认占用（S3 CAS claim：AWAIT_REVIEW → RUNNING 导入中，防并发双确认）
    "confirm_start": (frozenset({(STATUS_PENDING, STAGE_AWAIT_REVIEW)}), (STATUS_PENDING, STAGE_RUNNING)),
    # 入库成功（主流程 RUNNING 结束 / 确认流 AWAIT_REVIEW 结束）
    "import_ok": (frozenset({(STATUS_PENDING, STAGE_RUNNING)}), (STATUS_SUCCESS, STAGE_DONE)),
    "import_ok_confirmed": (frozenset({(STATUS_PENDING, STAGE_AWAIT_REVIEW)}), (STATUS_SUCCESS, STAGE_DONE)),
    # 失败（活动态 → FAILED；源状态任意活动态）
    "fail": (ACTIVE_STATES, (STATUS_FAILED, STAGE_DONE)),
    # 跳过（RUNNING 中去重 skip 等）
    "skip": (frozenset({(STATUS_PENDING, STAGE_RUNNING)}), (STATUS_SKIPPED, STAGE_DONE)),
    # 用户忽略（FAILED 或 AWAIT_REVIEW → SKIPPED）
    "ignore": (
        frozenset({(STATUS_FAILED, STAGE_DONE), (STATUS_PENDING, STAGE_AWAIT_REVIEW)}),
        (STATUS_SKIPPED, STAGE_DONE),
    ),
    # 用户取消（仅排队中）
    "cancel": (frozenset({(STATUS_PENDING, STAGE_QUEUED)}), (STATUS_CANCELLED, STAGE_DONE)),
    # 重试复活（FAILED/SKIPPED/CANCELLED/AWAIT_REVIEW → QUEUED）
    # 注：S3 决策——retry-all 默认仅 FAILED；SKIPPED/CANCELLED 需显式复活
    "retry": (
        frozenset({
            (STATUS_FAILED, STAGE_DONE),
            (STATUS_SKIPPED, STAGE_DONE),
            (STATUS_CANCELLED, STAGE_DONE),
            (STATUS_PENDING, STAGE_AWAIT_REVIEW),
        }),
        (STATUS_PENDING, STAGE_QUEUED),
    ),
}

# 允许终态→终态的例外（ignore: FAILED→SKIPPED 已在表内）
_ACTIONS = tuple(TRANSITIONS.keys())


def _check_source(action: str, source: tuple) -> None:
    spec = TRANSITIONS.get(action)
    if spec is None:
        raise TransitionError(f"未知动作: {action}")
    allowed, _target = spec
    if source not in allowed:
        raise TransitionError(
            f"非法转换: 动作 {action} 不允许在状态 {source}（允许: {sorted(allowed) or '无'}）"
        )


# ---------------------------------------------------------------------------
# apply：统一转换入口
# ---------------------------------------------------------------------------
def apply(task, action: str, **ctx) -> dict:
    """校验动作合法性并返回待写入字段（不落库，由调用方 db_update_task）。

    与旧 _apply 一致：同时就地更新 task（TaskContext 流水线步骤间共享 raw dict，
    后续步骤依赖就地可见的 video_path 等字段）。

    ctx 常用键：
    - error_message / skip_reason / reason：文案
    - video_path：当前文件路径（用于 file_location 诚实计算）
    - 其余键原样透传为字段
    """
    data = getattr(task, "raw", task)
    _check_source(action, _state(task))
    fields = _dispatch(task, data, action, ctx)
    data.update(fields)  # 就地更新（流水线内共享）
    return fields


def _dispatch(task, data, action: str, ctx: dict) -> dict:
    if action == "start":
        return {"status": STATUS_PENDING, "stage": STAGE_RUNNING,
                "started_at": ctx.get("started_at") or _now(),
                **_pass(ctx, "current_step", "step_name", "percentage")}

    if action == "step":
        return {"status": STATUS_PENDING, "stage": STAGE_RUNNING,
                **_pass(ctx, "current_step", "step_name", "percentage", "bytes_copied", "total_bytes")}

    if action in ("need_confirm", "need_review"):
        video_path = ctx.get("video_path") or data.get("video_path") or data.get("source_path", "")
        location = data.get("file_location") or FILE_LOCATION_SOURCE
        fields = {
            "status": STATUS_PENDING, "stage": STAGE_AWAIT_REVIEW,
            "video_path": video_path,
            "file_location": location,
        }
        if action == "need_confirm":
            fields["confirm_status"] = ctx.get("confirm_status", "PENDING")
            # 无理由时不覆盖既有 error_message（旧 mark_confirming 默认 _NO_FIELD 语义）
            reason = ctx.get("reason")
            if reason not in (None, ""):
                fields["error_message"] = reason
        else:
            fields["error_message"] = ctx.get("reason") or ctx.get("error_message") or ""
        return fields

    if action == "confirm_mark":
        return {"confirm_status": "CONFIRMED", "confirmed_at": ctx.get("confirmed_at") or _now()}

    if action == "confirm_start":
        return {"confirm_status": "CONFIRMED",
                "confirmed_at": ctx.get("confirmed_at") or _now(),
                "stage": STAGE_RUNNING}

    if action in ("import_ok", "import_ok_confirmed"):
        return {
            "status": STATUS_SUCCESS, "stage": STAGE_DONE,
            "completed_at": _now(), "import_success": 1,
            "file_location": FILE_LOCATION_IMPORT,
            "import_video_path": ctx.get("import_video_path") or data.get("import_video_path", ""),
        }

    if action == "fail":
        # 内部目标暂存不是业务文件位置；失败只保留已有业务位置。
        # video_path 语义：显式传值（含 ""）=写入该值；缺省/None=保留不动（不写字段，location 按当前值计算）
        video_path = ctx.get("video_path")
        if video_path is None:
            location = data.get("file_location") or FILE_LOCATION_SOURCE
            fields = {
                "status": STATUS_FAILED, "stage": STAGE_DONE,
                "error_message": ctx.get("error_message", ""),
                "file_location": location,
            }
        else:
            location = data.get("file_location") or FILE_LOCATION_SOURCE
            fields = {
                "status": STATUS_FAILED, "stage": STAGE_DONE,
                "error_message": ctx.get("error_message", ""),
                "file_location": location,
                "video_path": video_path,
            }
        if ctx.get("completed", True):
            fields["completed_at"] = _now()
        return fields

    if action == "skip":
        video_path = ctx.get("video_path", "")
        location = ctx.get("file_location") or data.get("file_location") or FILE_LOCATION_SOURCE
        return {
            "status": STATUS_SKIPPED, "stage": STAGE_DONE,
            "skip_reason": ctx.get("reason", ""),
            "completed_at": _now(),
            "file_location": location,
            "video_path": video_path,
        }

    if action == "ignore":
        return {
            "status": STATUS_SKIPPED, "stage": STAGE_DONE,
            "skip_reason": ctx.get("reason", "用户忽略"),
            "completed_at": _now(),
            **_pass(ctx, "file_location", "video_path"),
        }

    if action == "cancel":
        return {
            "status": STATUS_CANCELLED, "stage": STAGE_DONE,
            "error_message": ctx.get("reason", "用户取消"),
            "completed_at": _now(),
            "file_location": FILE_LOCATION_SOURCE,
            "video_path": "",
        }

    if action == "retry":
        is_reorganization = data.get("task_kind") == "REORGANIZE"
        return {
            "status": STATUS_PENDING, "stage": STAGE_QUEUED,
            "retry_count": data.get("retry_count", 0) + 1,
            "error_code": 0, "error_message": "",
            "current_step": 0, "step_name": "", "percentage": 0,
            "video_path": data.get("source_path", ""),
            "import_video_path": "", "import_path": "",
            "final_filename": "", "classify_result": "",
            "file_location": FILE_LOCATION_IMPORT if is_reorganization else FILE_LOCATION_SOURCE,
            "scrape_result": {}, "scrape_dimensions": {},
            "dedup_result": {}, "dedup_existing_file": "",
            "match_concerns": [], "used_fallback": 0,
            "confirm_status": CONFIRM_NONE, "confirmed_at": "",
            "bytes_copied": 0, "total_bytes": 0,
            "progress_item_name": "", "progress_item_kind": "",
            "progress_item_index": 0, "progress_item_total": 0,
            "bundle_state": "", "bundle_manifest": [], "bundle_committed": 0,
            "confirmed_override": 0, "confirmed_title": "", "override_source": "",
            "cancel_requested": 0, "stop_requested_at": "",
            "requested_source_disposition": "", "outcome_code": "",
            "source_disposition": "", "source_disposition_message": "",
        }

    raise TransitionError(f"动作 {action} 未实现")  # pragma: no cover


def _pass(ctx: dict, *keys: str) -> dict:
    return {k: ctx[k] for k in keys if k in ctx}


def can_apply(task, action: str) -> bool:
    """只判断不执行（供 API 层预检与测试）。"""
    try:
        _check_source(action, _state(task))
        return True
    except TransitionError:
        return False
