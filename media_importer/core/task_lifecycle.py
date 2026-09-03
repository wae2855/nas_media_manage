"""兼容 shim：生命周期函数已迁 features/tasks（Phase 2 S1）。

旧导入路径 media_importer.core.task_lifecycle 保持可用；
新代码请用 media_importer.features.tasks。
"""
from media_importer.features.tasks.task_lifecycle_compat import (  # noqa: F401
    current_video_path,
    mark_cancelled,
    mark_confirmed,
    mark_confirming,
    mark_failed,
    mark_imported,
    mark_needs_review,
    mark_processing_step,
    mark_skipped,
    reset_for_retry,
    start_processing,
)
from media_importer.features.tasks.transitions import (  # noqa: F401
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
    TRANSITIONS,
    VALID_STAGES,
    VALID_STATUS,
    TransitionError,
    apply,
    can_apply,
)
