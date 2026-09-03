# ruff: noqa: E402,F401
from .config_loader import load_config, mask_sensitive, validate_config, validate_dimension_values
from .config_validator import check_path, test_llm_api
from .config_validator import validate_config as full_validate_config
from .config_view import (
    ConfigView,
    DedupConfig,
    FilenameTemplateConfig,
    ManualReviewConfig,
    MetadataProviderConfig,
    PathConfig,
    ScannerConfig,
    SourceCleanerConfig,
    SourcePolicyConfig,
)


def __getattr__(name):
    """task_manager/task_lifecycle 延迟重导出（Phase 2 S1）：
    避免 core/__init__ 在 infrastructure.db 导入链上过早触发 features.tasks 包初始化。
    """
    if name == "TaskManager":
        from media_importer.core.task_manager import TaskManager
        return TaskManager
    if name == "VALID_STATUSES":
        from media_importer.core.task_manager import VALID_STATUSES
        return VALID_STATUSES
    _lifecycle_names = {
        "STATUS_PENDING", "STATUS_FAILED", "STATUS_SKIPPED", "STATUS_SUCCESS",
        "STATUS_CANCELLED", "STAGE_QUEUED", "STAGE_RUNNING", "STAGE_AWAIT_REVIEW",
        "STAGE_DONE", "FILE_LOCATION_SOURCE",
        "FILE_LOCATION_IMPORT", "FILE_LOCATION_RECYCLE",
    }
    if name in _lifecycle_names:
        from media_importer.features.tasks import transitions as _t
        return getattr(_t, name)
    raise AttributeError(f"module 'media_importer.core' has no attribute {name!r}")

from .db import (
    clear_tasks,
    count_all_tasks,
    count_by_status,
    count_subtitles_by_task,
    create_subtitles,
    create_task,
    delete_task,
    disable_dimension,
    enable_dimension,
    find_by_source_path,
    find_failed_too_many,
    get_all_dimensions,
    get_dimension,
    get_enabled_dimensions,
    get_next_pending,
    get_subtitles_by_task,
    get_task,
    has_running_tasks,
    init_db,
    list_all_tasks,
    list_tasks,
    reset_dimension,
    update_dimension,
    update_subtitle,
    update_subtitles_by_task,
    update_task,
)
from .logger import get_logger
from .metrics import Metrics, get_metrics
