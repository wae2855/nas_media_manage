"""Safely relocate a completed fallback library bundle into a formal rule target."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime

from media_importer.features.configuration import configured_library_roots
from media_importer.features.organization_state import (
    ORGANIZATION_FALLBACK_PENDING,
    ORGANIZATION_ORGANIZED,
    TASK_KIND_REORGANIZE,
)
from media_importer.infrastructure.db import (
    get_subtitles_by_task,
    get_task,
    update_subtitle,
    update_task,
)

from .file_operations import relocate_library_bundle


@dataclass
class ReorganizationResult:
    video_path: str
    subtitle_files: list[str] = field(default_factory=list)


class ReorganizationService:
    def __init__(self, config: dict, conn):
        self.config = config or {}
        self.conn = conn

    def reorganize_task(self, task: dict, *, phase_callback=None) -> ReorganizationResult:
        if task.get("task_kind") != TASK_KIND_REORGANIZE:
            raise IOError("当前任务不是重新整理任务")
        parent_id = str(task.get("parent_task_id") or "")
        parent = get_task(self.conn, parent_id) if parent_id else None
        if (
            not parent
            or parent.get("status") != "SUCCESS"
            or not parent.get("import_success")
            or parent.get("organization_status") != ORGANIZATION_FALLBACK_PENDING
        ):
            raise IOError("原入库任务已变化，无法继续重新整理，请刷新后重试")

        subtitle_rows = get_subtitles_by_task(self.conn, task["task_id"])
        subtitle_paths = [
            str(row.get("source_path") or "")
            for row in subtitle_rows
            if str(row.get("source_path") or "")
        ]
        move_result = relocate_library_bundle(
            str(task.get("video_path") or task.get("source_path") or ""),
            subtitle_paths,
            str(task.get("import_path") or ""),
            str(task.get("final_filename") or ""),
            self.config.get("filename_templates", {}) or {},
            library_roots=configured_library_roots(self.config),
            task_id=str(task.get("task_id") or ""),
            phase_callback=phase_callback,
            journal_callback=self._bundle_journal(task["task_id"]),
        )

        imported_subtitles = move_result.get("subtitles", [])
        by_name = {os.path.basename(path): path for path in imported_subtitles}
        now = datetime.now().isoformat()
        for row in subtitle_rows:
            import_path = by_name.get(str(row.get("planned_filename") or ""), "")
            if not import_path:
                raise IOError("重新整理结果中缺少计划字幕，已保留文件包现场")
            update_subtitle(
                self.conn,
                row["id"],
                status="SUCCESS",
                import_path=import_path,
                target_path=import_path,
                confirm_status="CONFIRMED",
                completed_at=now,
            )

        video_path = str(move_result.get("video") or "")
        task.update({
            "video_path": video_path,
            "import_video_path": video_path,
            "subtitle_files": imported_subtitles,
            "file_location": "import",
        })
        update_task(
            self.conn,
            parent_id,
            organization_status=ORGANIZATION_ORGANIZED,
            reorganized_by_task_id=task["task_id"],
        )
        return ReorganizationResult(video_path, imported_subtitles)

    def _bundle_journal(self, task_id: str):
        def persist(state: str, members: list[dict]):
            update_task(
                self.conn,
                task_id,
                bundle_state=state,
                bundle_manifest=members,
                bundle_committed=1 if state == "COMMITTED" else 0,
            )

        return persist


__all__ = ["ReorganizationResult", "ReorganizationService"]
