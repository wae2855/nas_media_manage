from datetime import datetime


# --- 任务终态（status） ---
STATUS_PENDING = "PENDING"
STATUS_FAILED = "FAILED"
STATUS_SKIPPED = "SKIPPED"
STATUS_SUCCESS = "SUCCESS"
STATUS_CANCELLED = "CANCELLED"

# 旧状态常量保留为向后兼容别名
STATUS_PROCESSING = "PENDING"       # 旧 PROCESSING → 现在由 stage=RUNNING 表达
STATUS_CONFIRMING = "PENDING"       # 旧 CONFIRMING → 现在由 stage=AWAIT_REVIEW 表达
STATUS_NEEDS_REVIEW = "PENDING"     # 旧 NEEDS_REVIEW → 现在由 stage=AWAIT_REVIEW 表达

# --- 处理环节（stage，仅 status=PENDING 时有意义） ---
STAGE_QUEUED = "QUEUED"
STAGE_RUNNING = "RUNNING"
STAGE_AWAIT_REVIEW = "AWAIT_REVIEW"
STAGE_DONE = "DONE"

VALID_STAGES = [STAGE_QUEUED, STAGE_RUNNING, STAGE_AWAIT_REVIEW, STAGE_DONE]

CONFIRM_NONE = "NONE"
CONFIRM_PENDING = "PENDING"
CONFIRM_CONFIRMED = "CONFIRMED"

FILE_LOCATION_SOURCE = "source"
FILE_LOCATION_TEMP = "temp"
FILE_LOCATION_IMPORT = "import"
FILE_LOCATION_RECYCLE = "recycle"

_NO_FIELD = object()


def _now() -> str:
    return datetime.now().isoformat()


def _raw(task):
    return getattr(task, "raw", task)


def _apply(task, **fields) -> dict:
    data = _raw(task)
    update_fields = {}
    for key, value in fields.items():
        if value is _NO_FIELD:
            continue
        data[key] = value
        update_fields[key] = value
    return update_fields


def current_video_path(task) -> str:
    data = _raw(task)
    return data.get("video_path") or data.get("source_path", "")


def start_processing(task, *, started_at: str = None) -> dict:
    return _apply(
        task,
        status=STATUS_PENDING,
        stage=STAGE_RUNNING,
        started_at=started_at or _now(),
    )


def mark_processing_step(task, *, current_step: int, step_name: str,
                         percentage: int) -> dict:
    return _apply(
        task,
        status=STATUS_PENDING,
        stage=STAGE_RUNNING,
        current_step=current_step,
        step_name=step_name,
        percentage=percentage,
    )


def mark_temp_ready(task, *, video_path: str = None) -> dict:
    return _apply(
        task,
        file_location=FILE_LOCATION_TEMP,
        video_path=video_path if video_path is not None else current_video_path(task),
    )


def mark_confirmed(task, *, confirmed_at: str = None) -> dict:
    return _apply(
        task,
        confirm_status=CONFIRM_CONFIRMED,
        confirmed_at=confirmed_at or _now(),
    )


def mark_confirming(task, reason=_NO_FIELD, *, video_path: str = None) -> dict:
    return _apply(
        task,
        status=STATUS_PENDING,
        stage=STAGE_AWAIT_REVIEW,
        confirm_status=CONFIRM_PENDING,
        video_path=video_path if video_path is not None else current_video_path(task),
        file_location=FILE_LOCATION_TEMP,
        error_message=reason,
    )


def mark_needs_review(task, reason: str, *, video_path: str = None) -> dict:
    return _apply(
        task,
        status=STATUS_PENDING,
        stage=STAGE_AWAIT_REVIEW,
        error_message=reason,
        video_path=video_path if video_path is not None else current_video_path(task),
        file_location=FILE_LOCATION_TEMP,
    )


def mark_failed(task, error_message: str, *, file_location: str = FILE_LOCATION_SOURCE,
                video_path="", completed: bool = True) -> dict:
    return _apply(
        task,
        status=STATUS_FAILED,
        stage=STAGE_DONE,
        error_message=error_message,
        completed_at=_now() if completed else _NO_FIELD,
        file_location=file_location,
        video_path=_NO_FIELD if video_path is None else video_path,
    )


def mark_skipped(task, reason: str, *, file_location: str = FILE_LOCATION_SOURCE,
                 video_path="") -> dict:
    return _apply(
        task,
        status=STATUS_SKIPPED,
        stage=STAGE_DONE,
        skip_reason=reason,
        completed_at=_now(),
        file_location=file_location,
        video_path=_NO_FIELD if video_path is None else video_path,
    )


def mark_imported(task, *, import_video_path: str = None) -> dict:
    return _apply(
        task,
        status=STATUS_SUCCESS,
        stage=STAGE_DONE,
        completed_at=_now(),
        import_success=1,
        file_location=FILE_LOCATION_IMPORT,
        import_video_path=import_video_path
        if import_video_path is not None else _raw(task).get("import_video_path", ""),
    )


def reset_for_retry(task) -> dict:
    data = _raw(task)
    return _apply(
        task,
        status=STATUS_PENDING,
        stage=STAGE_QUEUED,
        retry_count=data.get("retry_count", 0) + 1,
        error_code=0,
        error_message="",
        current_step=0,
        step_name="",
        percentage=0,
        video_path="",
        import_video_path="",
        import_path="",
        final_filename="",
        classify_result="",
        file_location=FILE_LOCATION_SOURCE,
    )
