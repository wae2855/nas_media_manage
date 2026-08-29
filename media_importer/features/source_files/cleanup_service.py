import os
from dataclasses import dataclass

from media_importer.features.configuration import ConfigView
from media_importer.features.recycle import move_to_recycle
from media_importer.features.source_files.config_paths import (
    allowed_dirs_from_config,
    import_roots_from_config,
)
from media_importer.features.source_files.operations import delete_source_files


@dataclass
class SourceCleanupResult:
    moved_count: int = 0
    deleted_count: int = 0
    message: str = ""


class SourceCleanupService:
    def __init__(self, config: dict):
        self.config = ConfigView.from_dict(config)

    def allowed_dirs(self) -> list:
        return allowed_dirs_from_config(self.config)  # type: ignore[arg-type]

    def import_roots(self) -> list:
        return import_roots_from_config(self.config)  # type: ignore[arg-type]

    def recycle_existing_import(self, path: str, *, reason: str, task_id: str):
        recycle_dir = self.config.source_policy.recycle_dir
        source_dir = self.config.paths.source_dir
        return move_to_recycle(
            path,
            recycle_dir,
            reason=reason,
            task_id=task_id,
            source_dir=source_dir,
            import_roots=self.import_roots(),
        )

    def cleanup_source_after_import(self, task: dict, original_video: str,
                                    original_subtitles: list) -> SourceCleanupResult:
        source_dir = self.config.paths.source_dir
        if not source_dir or not original_video:
            return SourceCleanupResult()

        if self.config.source_policy.mode == "recycle_source_unit":
            return SourceCleanupResult(message="等待同一源单元内全部任务成功后统一回收")
        filename = os.path.basename(original_video)
        if self.config.source_policy.mode == "preserve_media":
            return SourceCleanupResult(message=f"源媒体保留；仅按智能清理策略处理垃圾文件: {filename}")
        return SourceCleanupResult(message=f"源文件保留（不做任何源目录写入）: {filename}")

    def cleanup_temp_file(self, temp_video_path: str) -> SourceCleanupResult:
        temp_dir = self.config.paths.temp_dir
        if not temp_video_path or not temp_dir:
            return SourceCleanupResult()
        if not str(temp_video_path).startswith(temp_dir):
            return SourceCleanupResult()
        delete_source_files([temp_video_path], allowed_base_dirs=self.allowed_dirs())
        return SourceCleanupResult(
            deleted_count=1,
            message=f"已清理临时文件: {os.path.basename(temp_video_path)}",
        )

    def recycle_source_after_skip(self, task: dict, original_video: str,
                                  original_subtitles: list) -> SourceCleanupResult:
        filename = os.path.basename(original_video)
        if self.config.source_policy.mode == "recycle_source_unit":
            return SourceCleanupResult(message=f"源单元任务未全部成功，源文件保持不变: {filename}")
        return SourceCleanupResult(message=f"任务未成功，源文件保留并保持不变: {filename}")
