import os
from dataclasses import dataclass, field

from media_importer.core.config_view import ConfigView
from media_importer.storage.dedup_checker import check_duplicate
from .paths import import_roots_from_config
from .source_cleanup import SourceCleanupService


@dataclass
class DedupDecision:
    action: str
    result: dict = field(default_factory=dict)
    message: str = ""
    final_filename: str = ""


class DedupService:
    def __init__(self, config: dict, cleanup_service: SourceCleanupService = None):
        self.config = ConfigView.from_dict(config)
        self.cleanup_service = cleanup_service or SourceCleanupService(config)

    def import_roots(self) -> list:
        return import_roots_from_config(self.config)

    def check_task(self, task: dict) -> DedupDecision:
        if not self.config.dedup.enabled:
            return DedupDecision(
                action="continue",
                result={"is_duplicate": False, "enabled": False},
                message="智能同名检测已关闭，跳过跨目录扫描",
            )

        strategy = self.config.dedup.strategy
        dedup_result = {"is_duplicate": False}
        scraped = task.get("scrape_result", {})
        video_path = task.get("video_path", "")

        for search_dir in self.import_roots():
            if not os.path.isdir(search_dir):
                continue
            result = check_duplicate(search_dir, scraped, strategy, video_path)
            if result["is_duplicate"]:
                dedup_result = result
                break

        if not dedup_result["is_duplicate"]:
            return DedupDecision(action="continue", result=dedup_result)

        if strategy == "skip":
            return DedupDecision(
                action="skip",
                result=dedup_result,
                message=dedup_result.get(
                    "skip_message",
                    f"同名文件已存在: {dedup_result.get('existing_file', 'unknown')}",
                ),
            )

        if strategy == "rename":
            return DedupDecision(
                action="rename",
                result=dedup_result,
                final_filename=os.path.basename(dedup_result["suggested_filename"]),
            )

        if strategy == "replace":
            self._recycle_duplicate(task, dedup_result, "dedup_replace")
            return DedupDecision(action="replace", result=dedup_result)

        if strategy == "quality":
            if dedup_result.get("quality_decision") == "replace":
                self._recycle_duplicate(task, dedup_result, "quality_replace")
                return DedupDecision(action="replace", result=dedup_result)
            return DedupDecision(
                action="skip",
                result=dedup_result,
                message=dedup_result.get("skip_message", "质量优先: 保留已存在文件"),
            )

        return DedupDecision(action="continue", result=dedup_result)

    def _recycle_duplicate(self, task: dict, dedup_result: dict, reason: str):
        existing_path = dedup_result.get("existing_path", "")
        if not existing_path or not os.path.exists(existing_path):
            return
        ok, dest, message = self.cleanup_service.recycle_existing_import(
            existing_path,
            reason=reason,
            task_id=task.get("task_id", ""),
        )
        if not ok:
            raise OSError(message)
