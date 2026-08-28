from dataclasses import dataclass, field

from media_importer.infrastructure.db import VALID_STATUSES

from .repository import list_tasks as db_list_tasks


@dataclass
class TaskListResult:
    code: int
    data: dict = field(default_factory=dict)
    message: str = ""
    format_mode: str = "json"


def list_tasks_for_api(query: dict, task_manager, logger=None) -> TaskListResult:
    raw_statuses: list = query.get("status", [])
    statuses: list = [s.strip().upper() for s in raw_statuses if s and s.strip().upper() != "ALL"]
    stage = query.get("stage", [None])[0]
    limit = int(query.get("limit", [20])[0])
    offset = int(query.get("offset", [0])[0])
    page = query.get("page", [None])[0]
    format_mode = query.get("format", ["json"])[0].lower()

    for s in statuses:
        if s not in VALID_STATUSES:
            if logger:
                logger.warning(
                    f"Invalid status filter: {s}, VALID_STATUSES={VALID_STATUSES}"
                )
            return TaskListResult(code=400, message=f"Invalid status: {s}")

    if stage:
        stage = stage.strip().upper()

    if page is not None:
        page_num = int(page)
        page_size = limit
    else:
        page_num = (offset // limit) + 1 if limit > 0 else 1
        page_size = limit

    rows, total, total_pages = db_list_tasks(
        task_manager.conn,
        page=page_num,
        page_size=page_size,
        statuses=statuses if statuses else None,  # type: ignore[arg-type]
        stage=stage,
    )
    counts = task_manager.count_by_status()
    active_count = sum(
        counts.get(status_name, 0)
        for status_name in ("PENDING", "FAILED")
    )

    return TaskListResult(
        code=200,
        data={
            "tasks": rows,
            "total": total,
            "total_pages": total_pages,
            "page": page_num,
            "page_size": page_size,
            "active_count": active_count,
            "by_status": counts,
        },
        format_mode=format_mode,
    )
