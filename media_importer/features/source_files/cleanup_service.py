import os
from dataclasses import dataclass

from media_importer.features.configuration import ConfigView
from media_importer.features.recycle import move_to_recycle
from media_importer.features.source_files.config_paths import (
    allowed_dirs_from_config,
    import_roots_from_config,
)


@dataclass
class SourceCleanupResult:
    moved_count: int = 0
    deleted_count: int = 0
    message: str = ""


class SourceCleanupService:
    def __init__(self, config: dict):
        self.raw_config = config or {}
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

    def recycle_source_after_skip(self, task: dict, original_video: str,
                                  original_subtitles: list) -> SourceCleanupResult:
        filename = os.path.basename(original_video)
        if self.config.source_policy.mode == "recycle_source_unit":
            return SourceCleanupResult(message=f"源单元任务未全部成功，源文件保持不变: {filename}")
        return SourceCleanupResult(message=f"任务未成功，源文件保留并保持不变: {filename}")
