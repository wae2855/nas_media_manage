import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from media_importer.features.configuration import ConfigView
from media_importer.features.source_files import SourceCleanupResult, SourceCleanupService
from media_importer.infrastructure.db import (
    get_subtitles_by_task as db_get_subtitles,
)
from media_importer.infrastructure.db import (
    update_subtitle as db_update_subtitle,
)

from .file_operations import move_to_import
from .paths import allowed_dirs_for_import


@dataclass
class ImportResult:
    video_path: str
    subtitle_files: list = field(default_factory=list)
    source_cleanup: SourceCleanupResult = field(default_factory=SourceCleanupResult)


class ImportService:
    def __init__(self, config: dict, conn=None,
                 cleanup_service: Optional[SourceCleanupService] = None):
        self.config = ConfigView.from_dict(config)
        self.conn = conn
        self.cleanup_service = cleanup_service or SourceCleanupService(config)

    def import_task(self, task: dict, original_source_video: str,
                    original_source_subtitles: list, *,
                    overwrite: bool = False,
                    conflict_snapshot: Optional[dict] = None,
                    phase_callback=None) -> ImportResult:
        source_video_path = task.get("source_path") or original_source_video
        if not source_video_path:
            raise IOError("来源影片路径缺失，无法从头执行入库")
        allowed_dirs, import_roots = allowed_dirs_for_import(
            self.config,
            str(task.get("import_path", "")),
        )
        if not import_roots:
            raise IOError("入库路径无法唯一归属于已配置的目标片库")
        move_result = move_to_import(
            source_video_path,
            task.get("subtitle_files", []),
            task.get("import_path", ""),
            task.get("scrape_result", {}),
            self.config.filename_template_dict(),
            allowed_base_dirs=allowed_dirs,
            overwrite=overwrite,
            final_filename=task.get("final_filename", ""),
            recycle_dir=self.config.source_policy.recycle_dir,
            task_id=task.get("task_id", ""),
            expected_conflict=conflict_snapshot,
            import_roots=import_roots,
            phase_callback=phase_callback,
            journal_callback=self._bundle_journal(task.get("task_id", "")),
        )

        task["video_path"] = move_result.get("video", source_video_path)
        task["subtitle_files"] = move_result.get("subtitles", [])
        task["import_video_path"] = move_result.get("video", "")

        source_cleanup = self.cleanup_service.cleanup_source_after_import(
            task,
            original_source_video,
            original_source_subtitles,
        )
        self._update_subtitles(task.get("task_id", ""), move_result.get("subtitles", []))

        return ImportResult(
            video_path=task["import_video_path"],
            subtitle_files=task["subtitle_files"],
            source_cleanup=source_cleanup,
        )

    def _bundle_journal(self, task_id: str):
        if not self.conn or not task_id:
            return None

        def persist(state: str, members: list[dict]):
            from media_importer.infrastructure.db import update_task

            update_task(
                self.conn,
                task_id,
                bundle_state=state,
                bundle_manifest=members,
                bundle_committed=1 if state == "COMMITTED" else 0,
            )

        return persist

    def _update_subtitles(self, task_id: str, import_subtitles: list):
        if not self.conn or not task_id:
            return
        subtitles = db_get_subtitles(self.conn, task_id)
        now = datetime.now().isoformat()
        by_filename = {
            os.path.basename(path): path for path in import_subtitles if path
        }
        for subtitle in subtitles:
            import_path = by_filename.get(subtitle.get("planned_filename", ""), "")
            if not import_path:
                db_update_subtitle(
                    self.conn,
                    subtitle["id"],
                    status="FAILED",
                    error_message="入库结果中未找到计划的字幕文件",
                )
                continue
            db_update_subtitle(
                self.conn,
                subtitle["id"],
                status="SUCCESS",
                import_path=import_path,
                confirm_status="CONFIRMED",
                completed_at=now,
            )
