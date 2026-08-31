"""Safety gates for changing runtime directory roles."""

from __future__ import annotations

import os


def validate_temp_directory_change(
    old_path: str,
    new_path: str,
    task_manager=None,
) -> list[str]:
    """Refuse a temp-root switch while recoverable state may still use it."""
    old_root = os.path.abspath(old_path) if old_path else ""
    new_root = os.path.abspath(new_path) if new_path else ""
    if not old_root or old_root == new_root:
        return []

    if task_manager and task_manager.has_running_tasks():
        return ["当前有任务正在处理，任务完成后才能更改中转目录"]

    if task_manager and hasattr(task_manager, "list_all_tasks"):
        recoverable = [
            task for task in task_manager.list_all_tasks(limit=10000)
            if str(task.get("file_location") or "") == "temp"
            and str(task.get("status") or "").upper() in {"PENDING", "FAILED"}
        ]
        if recoverable:
            return [
                f"还有 {len(recoverable)} 个任务依赖旧中转目录，请先完成、重试或处理这些任务"
            ]

    if os.path.isdir(old_root):
        try:
            if next(os.scandir(old_root), None) is not None:
                return ["旧中转目录仍有文件，请确认任务已处理完并清空目录后再更改"]
        except OSError as exc:
            return [f"无法确认旧中转目录是否为空：{exc}"]
    return []
