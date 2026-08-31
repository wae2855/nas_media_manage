import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from media_importer.features.configuration import ConfigView
from media_importer.infrastructure.filesystem import hash_file

from .dedup_rules import check_duplicate


@dataclass
class DedupDecision:
    action: str
    result: dict = field(default_factory=dict)
    message: str = ""
    final_filename: str = ""


class DedupService:
    def __init__(self, config: dict, cleanup_service: Optional[object] = None):
        self.config = ConfigView.from_dict(config)

    def check_task(self, task: dict) -> DedupDecision:
        """只读检测本任务目标目录，绝不在检测阶段处置片库文件。"""
        import_path = os.path.realpath(str(task.get("import_path", "")))
        final_filename = os.path.basename(str(task.get("final_filename", "")))
        if not import_path or not os.path.isdir(import_path):
            return DedupDecision(action="continue", result={"is_duplicate": False})

        strategy = "confirm"
        dedup_result = {"is_duplicate": False, "status": "clear"}
        scraped = task.get("scrape_result", {})
        video_path = task.get("video_path", "")

        exact_path = os.path.join(import_path, final_filename) if final_filename else ""
        if exact_path and os.path.isfile(exact_path):
            dedup_result = {
                "is_duplicate": True,
                "existing_file": os.path.basename(exact_path),
                "existing_path": exact_path,
                "conflict_type": "target_path",
            }
        elif self.config.dedup.enabled:
            result = check_duplicate(import_path, scraped, strategy, video_path)
            if result["is_duplicate"]:
                dedup_result = result
                dedup_result["conflict_type"] = "same_work"

        if not dedup_result["is_duplicate"]:
            return DedupDecision(action="continue", result=dedup_result)

        existing_path = os.path.realpath(str(dedup_result.get("existing_path", "")))
        dedup_result.update({
            "status": "awaiting_user",
            "existing_path": existing_path,
            "existing_file": os.path.basename(existing_path),
            "existing_fingerprint": hash_file(existing_path),
            "existing_size": os.path.getsize(existing_path),
            "existing_resolution": _resolution_of(existing_path),
            "new_path": video_path,
            "new_file": os.path.basename(video_path),
            "new_fingerprint": hash_file(video_path) if os.path.isfile(video_path) else "",
            "new_size": os.path.getsize(video_path) if os.path.isfile(video_path) else 0,
            "new_resolution": str(scraped.get("resolution") or _resolution_of(video_path)),
            "expected_target_path": exact_path,
            "suggested_filename": _available_copy_name(import_path, final_filename or os.path.basename(video_path)),
            "detected_at": datetime.now().isoformat(),
            "message": "片库中已存在同一影片，现有文件未发生任何改动",
        })
        return DedupDecision(
            action="review",
            result=dedup_result,
            message=dedup_result["message"],
        )


def _resolution_of(path: str) -> str:
    name = os.path.basename(path).lower()
    for value in ("4320p", "2160p", "1440p", "1080p", "720p", "480p", "360p"):
        if value in name:
            return value
    return "未知"


def _available_copy_name(directory: str, filename: str) -> str:
    stem, ext = os.path.splitext(filename)
    counter = 1
    while True:
        candidate = f"{stem}_保留{counter}{ext}"
        if not os.path.exists(os.path.join(directory, candidate)):
            return candidate
        counter += 1
