import os
from dataclasses import dataclass, field
from datetime import datetime

from media_importer.core.db import (
    get_subtitles_by_task as db_get_subtitles,
    update_subtitle as db_update_subtitle,
)
from media_importer.storage.file_mover import move_to_import
from .paths import allowed_dirs_from_config
from .source_cleanup import SourceCleanupResult, SourceCleanupService


@dataclass
class ImportResult:
    video_path: str
    subtitle_files: list = field(default_factory=list)
    source_cleanup: SourceCleanupResult = field(default_factory=SourceCleanupResult)
    temp_cleanup: SourceCleanupResult = field(default_factory=SourceCleanupResult)


class ImportService:
    def __init__(self, config: dict, conn=None,
                 cleanup_service: SourceCleanupService = None):
        self.config = config
        self.conn = conn
        self.cleanup_service = cleanup_service or SourceCleanupService(config)

    def import_task(self, task: dict, original_source_video: str,
                    original_source_subtitles: list, *,
                    restore_confirm_temp_name: bool = False,
                    overwrite: bool = False) -> ImportResult:
        if restore_confirm_temp_name:
            self.restore_confirm_temp_name(task)

        temp_video_path = task.get("video_path", "")
        move_result = move_to_import(
            temp_video_path,
            task.get("subtitle_files", []),
            task.get("import_path", ""),
            task.get("scrape_result", {}),
            self.config.get("filename_templates", {}),
            allowed_base_dirs=allowed_dirs_from_config(self.config),
            overwrite=overwrite,
        )

        task["video_path"] = move_result.get("video", temp_video_path)
        task["subtitle_files"] = move_result.get("subtitles", [])
        task["import_video_path"] = move_result.get("video", "")

        source_cleanup = self.cleanup_service.cleanup_source_after_import(
            task,
            original_source_video,
            original_source_subtitles,
        )
        temp_cleanup = self.cleanup_service.cleanup_temp_file(temp_video_path)

        self._update_subtitles(task.get("task_id", ""), move_result.get("subtitles", []))

        return ImportResult(
            video_path=task["import_video_path"],
            subtitle_files=task["subtitle_files"],
            source_cleanup=source_cleanup,
            temp_cleanup=temp_cleanup,
        )

    def restore_confirm_temp_name(self, task: dict):
        if not self.config.get("manual_review", {}).get("enabled", False):
            return
        temp_video_path = task.get("video_path", "")
        for extension in (".temp", ".tmp"):
            if temp_video_path.endswith(extension):
                new_path = temp_video_path[:-len(extension)]
                if os.path.exists(temp_video_path):
                    os.rename(temp_video_path, new_path)
                    task["video_path"] = new_path
                return

    def _update_subtitles(self, task_id: str, import_subtitles: list):
        if not self.conn or not task_id:
            return
        subtitles = db_get_subtitles(self.conn, task_id)
        now = datetime.now().isoformat()
        for index, subtitle in enumerate(subtitles):
            import_path = import_subtitles[index] if index < len(import_subtitles) else ""
            db_update_subtitle(
                self.conn,
                subtitle["id"],
                status="SUCCESS",
                import_path=import_path,
                confirm_status="CONFIRMED",
                completed_at=now,
            )
