from dataclasses import dataclass
from typing import Callable, Optional

from media_importer.core.db.task_repo import list_all_tasks

from .cleaner import SourceCleaner
from .records import get_cleaner_records, get_cleaner_status, save_cleaner_record


@dataclass
class SourceCleanerExecutionResult:
    ok: bool
    message: str = ""
    record: Optional[dict] = None


def collect_task_paths(conn, limit: int = 5000) -> set:
    tasks = list_all_tasks(conn, limit=limit)
    paths = set()
    for task in tasks:
        for key in ("source_path", "video_path", "import_video_path"):
            path = task.get(key, "")
            if path:
                paths.add(path)
        for subtitle in task.get("subtitle_files", []):
            if isinstance(subtitle, str):
                paths.add(subtitle)
            elif isinstance(subtitle, dict):
                path = subtitle.get("target_path") or subtitle.get("source_path", "")
                if path:
                    paths.add(path)
    return paths


def preview_source_cleaning(config: dict, conn) -> dict:
    cleaner = SourceCleaner(config)
    items = cleaner.preview(collect_task_paths(conn))
    return {"items": items, "total": len(items)}


def ai_preview_source_cleaning(config: dict, conn) -> dict:
    cleaner = SourceCleaner(config)
    return cleaner.ai_preview(collect_task_paths(conn))


def list_source_cleaner_records(conn, limit: int = 20, offset: int = 0) -> list:
    return get_cleaner_records(conn, limit=limit, offset=offset)


def get_source_cleaner_status(config: dict, conn) -> dict:
    status = get_cleaner_status(conn)
    cleaner_config = config.get("source_cleaner", {})
    status["enabled"] = cleaner_config.get("enabled", False)
    status["cleanup_mode"] = cleaner_config.get("cleanup_mode", "media_only")
    status["ai_enabled"] = cleaner_config.get("ai_enabled", False)
    status["merge_strategy"] = cleaner_config.get("merge_strategy", "intersection")
    status["schedule"] = cleaner_config.get("schedule", "0 3 * * *")
    return status


def execute_source_cleaning(
    config: dict,
    conn,
    merge_strategy: Optional[str] = None,
    permission_check: Optional[Callable[..., dict]] = None,
) -> SourceCleanerExecutionResult:
    recycle_dir = config.get("source_policy", {}).get("recycle_dir", "")
    if recycle_dir and permission_check is not None:
        result = permission_check(recycle_dir, need_write=True)
        if not result.get("ok"):
            return SourceCleanerExecutionResult(
                ok=False,
                message=f"回收站目录权限不足: {result.get('message', '')}",
            )

    cleaner = SourceCleaner(config)
    record = cleaner.execute(
        task_paths=collect_task_paths(conn),
        merge_strategy=merge_strategy,
    )
    save_cleaner_record(conn, record)
    return SourceCleanerExecutionResult(ok=True, record=record)
