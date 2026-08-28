import os
from dataclasses import dataclass

from media_importer.features.configuration import ConfigView
from media_importer.features.recycle import move_to_recycle, move_to_recycle_with_companions
from media_importer.features.source_files.config_paths import (
    allowed_dirs_from_config,
    import_roots_from_config,
)
from media_importer.features.source_files.operations import (
    delete_source_files,
    remove_empty_parent_dir,
)


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

        if self.config.source_policy.cleanup_source_after_done is not True:
            filename = os.path.basename(original_video)
            return SourceCleanupResult(message=f"源文件保留（配置: cleanup_source_after_done=false）: {filename}")

        recycle_dir = self.config.source_policy.recycle_dir
        if not recycle_dir:
            return SourceCleanupResult()

        video_exts = list(self.config.paths.video_extensions)
        sub_exts = list(self.config.paths.subtitle_extensions)
        count = move_to_recycle_with_companions(
            original_video,
            original_subtitles,
            video_exts,
            sub_exts,
            recycle_dir,
            reason="source_cleanup",
            task_id=task.get("task_id", ""),
            source_dir=source_dir,
            import_roots=self.import_roots(),
            allowed_base_dirs=self.allowed_dirs(),
        )
        remove_empty_parent_dir(original_video, source_dir)
        message = f"已将源文件移入回收站: {os.path.basename(original_video)}"
        if count > 1:
            message += f" (含 {count - 1} 个附属文件)"
        return SourceCleanupResult(moved_count=count, message=message)

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
        source_dir = self.config.paths.source_dir
        if self.config.source_policy.cleanup_source_after_done is not True:
            filename = os.path.basename(original_video)
            return SourceCleanupResult(
                message=(
                    "源文件保留（配置: cleanup_source_after_done=false）: "
                    f"{filename}"
                )
            )

        recycle_dir = self.config.source_policy.recycle_dir
        if not source_dir or not recycle_dir or not original_video:
            return SourceCleanupResult()
        if not str(original_video).startswith(source_dir):
            return SourceCleanupResult()

        video_exts = list(self.config.paths.video_extensions)
        sub_exts = list(self.config.paths.subtitle_extensions)
        count = move_to_recycle_with_companions(
            original_video,
            original_subtitles,
            video_exts,
            sub_exts,
            recycle_dir,
            reason="pipeline_skip",
            task_id=task.get("task_id", ""),
            source_dir=source_dir,
            import_roots=self.import_roots(),
            allowed_base_dirs=self.allowed_dirs(),
        )
        remove_empty_parent_dir(original_video, source_dir)
        message = f"已将跳过任务源文件移入回收站: {os.path.basename(original_video)}"
        if count > 1:
            message += f" (含 {count - 1} 个附属文件)"
        return SourceCleanupResult(moved_count=count, message=message)
