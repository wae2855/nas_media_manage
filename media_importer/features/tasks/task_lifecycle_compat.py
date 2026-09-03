"""任务生命周期字段构造（兼容层）。

Phase 2（REQ-20260822-000004）起，状态转换规则唯一事实源是
`media_importer.features.tasks.transitions`；本模块（task_lifecycle_compat）的 mark_* 只是
对 transitions.apply 的薄封装，保留既有调用方签名。
新增代码请直接使用 transitions.apply / can_apply。
"""
from typing import Optional

from .transitions import (  # noqa: F401
    ACTIVE_STATES,
    ALL_STATES,
    CONFIRM_CONFIRMED,
    CONFIRM_NONE,
    CONFIRM_PENDING,
    FILE_LOCATION_IMPORT,
    FILE_LOCATION_RECYCLE,
    FILE_LOCATION_SOURCE,
    STAGE_AWAIT_REVIEW,
    STAGE_DONE,
    STAGE_QUEUED,
    STAGE_RUNNING,
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SKIPPED,
    STATUS_SUCCESS,
    TERMINAL_STATES,
    VALID_STAGES,
    VALID_STATUS,
    TransitionError,
    can_apply,
)
from .transitions import (
    apply as _transition,
)


def _now() -> str:
    from .transitions import _now as _t
    return _t()


def current_video_path(task) -> str:
    data = getattr(task, "raw", task)
    return data.get("video_path") or data.get("source_path", "")


def start_processing(task, *, started_at: Optional[str] = None) -> dict:
    return _transition(task, "start", started_at=started_at)


def mark_processing_step(task, *, current_step: int, step_name: str,
                         percentage: int, **extra) -> dict:
    return _transition(task, "step", current_step=current_step, step_name=step_name,
                       percentage=percentage, **extra)


def mark_confirmed(task, *, confirmed_at: Optional[str] = None) -> dict:
    return _transition(task, "confirm_mark", confirmed_at=confirmed_at)


def mark_confirming(task, reason=None, *, video_path: Optional[str] = None) -> dict:
    return _transition(task, "need_confirm",
                       reason="" if reason is None else reason, video_path=video_path)


def mark_needs_review(task, reason: str, *, video_path: Optional[str] = None) -> dict:
    return _transition(task, "need_review", reason=reason, video_path=video_path)


def mark_failed(task, error_message: str, *,
                file_location: Optional[str] = None,
                video_path=None, completed: bool = True) -> dict:
    # file_location 参数保留兼容：显式传入时覆盖（历史调用方语义），
    # 缺省时由诚实规则按文件实际位置计算
    # video_path：默认 ""（清空）；显式 None 表示"保留不动"（不写该字段）
    ctx = {"error_message": error_message, "completed": completed}
    if video_path is not None:
        ctx["video_path"] = video_path
    fields = _transition(task, "fail", **ctx)
    if file_location is not None:
        fields["file_location"] = file_location
    return fields


def mark_skipped(task, reason: str, *, file_location: Optional[str] = None,
                 video_path="") -> dict:
    ctx = {"reason": reason, "video_path": video_path}
    if file_location is not None:
        ctx["file_location"] = file_location
    return _transition(task, "skip", **ctx)


def mark_cancelled(task, reason: str = "用户取消", *,
                   file_location: Optional[str] = None,
                   video_path=None) -> dict:
    fields = _transition(task, "cancel", reason=reason)
    if file_location is not None:
        fields["file_location"] = file_location
    if video_path is not None:
        fields["video_path"] = video_path
    return fields


def mark_imported(task, *, import_video_path: Optional[str] = None) -> dict:
    from .transitions import _state
    action = "import_ok_confirmed" if _state(task) == (STATUS_PENDING, STAGE_AWAIT_REVIEW) else "import_ok"
    return _transition(task, action, import_video_path=import_video_path)


def reset_for_retry(task) -> dict:
    return _transition(task, "retry")
