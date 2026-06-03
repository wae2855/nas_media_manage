from dataclasses import dataclass

from media_importer.core.db import VALID_STATUSES

from .repository import list_tasks as db_list_tasks


@dataclass
class TaskListResult:
    code: int
    data: dict = None
    message: str = ""
    format_mode: str = "json"


def list_tasks_for_api(query: dict, task_manager, logger=None) -> TaskListResult:
    status = query.get("status", [None])[0]
    limit = int(query.get("limit", [20])[0])
    offset = int(query.get("offset", [0])[0])
    page = query.get("page", [None])[0]
    format_mode = query.get("format", ["json"])[0].lower()

    if status:
        status = status.strip().upper()
    if status and status != "ALL" and status not in VALID_STATUSES:
        if logger:
            logger.warning(
                f"Invalid status filter: {status}, VALID_STATUSES={VALID_STATUSES}"
            )
        return TaskListResult(code=400, message=f"Invalid status: {status}")

    if status and status == "ALL":
        status = None

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
        status=status,
    )
    counts = task_manager.count_by_status()
    active_count = sum(
        counts.get(status_name, 0)
        for status_name in ("PENDING", "PROCESSING", "FAILED", "CONFIRMING")
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
