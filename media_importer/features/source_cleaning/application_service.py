from dataclasses import dataclass
from typing import Callable, Optional

from media_importer.infrastructure.db import list_all_tasks

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
    config = config or {}
    cleaner_config = config.get("source_cleaner", {}) or {}
    if cleaner_config.get("enabled") is not True:
        return SourceCleanerExecutionResult(ok=False, message="源目录智能清理未启用，本次未执行任何文件操作")

    source_policy = config.get("source_policy", {}) or {}
    source_mode = source_policy.get("mode")
    if source_mode not in {"preserve_all", "preserve_media", "recycle_source_unit"}:
        if source_policy.get("cleanup_source_after_done") is True:
            source_mode = "recycle_source_unit"
        else:
            source_mode = "preserve_media"
    if source_mode != "preserve_media":
        return SourceCleanerExecutionResult(
            ok=False,
            message="当前源文件处理模式不允许智能清理，本次未执行任何文件操作",
        )

    from media_importer.features.configuration.storage_topology import (
        topology_error_messages,
    )

    conflicts = topology_error_messages(config)
    if conflicts:
        return SourceCleanerExecutionResult(
            ok=False,
            message="目录边界不安全，已阻止源目录清理：" + conflicts[0],
        )

    recycle_dir = source_policy.get("recycle_dir", "")
    if recycle_dir and permission_check is not None:
        result = permission_check(recycle_dir, need_write=True)
        if not result.get("ok"):
            return SourceCleanerExecutionResult(
                ok=False,
                message=f"回收站目录权限不足: {result.get('message', '')}",
            )

    from media_importer.features.configuration.storage_readiness import (
        inspect_storage_readiness,
    )

    readiness = inspect_storage_readiness(config)
    if set(readiness.get("blocking", [])).intersection({"source", "recycle"}):
        return SourceCleanerExecutionResult(
            ok=False,
            message="源目录或回收目录的挂载身份、权限或空间已变化，本次未执行任何文件操作",
        )

    cleaner = SourceCleaner(config)
    record = cleaner.execute(
        task_paths=collect_task_paths(conn),
        merge_strategy=merge_strategy or "",
    )
    save_cleaner_record(conn, record)
    return SourceCleanerExecutionResult(ok=True, record=record)
