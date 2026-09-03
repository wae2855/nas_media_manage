import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from media_importer.features.configuration import ConfigView
from media_importer.infrastructure.filesystem import hash_file

from ..utils import PipelineReviewRequired
from .dedup_rules import check_duplicate
from .naming import plan_subtitle_filenames


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
        subtitle_paths = task.get("subtitle_source_files") or task.get("subtitle_files") or []
        subtitle_plan = plan_subtitle_filenames(
            [str(path) for path in subtitle_paths if path],
            final_filename or os.path.basename(video_path),
            self.config.filename_templates.subtitle,
        )
        subtitle_conflicts = [
            os.path.join(import_path, item["filename"])
            for item in subtitle_plan
            if os.path.isfile(os.path.join(import_path, item["filename"]))
        ]
        if exact_path and os.path.isfile(exact_path):
            dedup_result = {
                "is_duplicate": True,
                "existing_file": os.path.basename(exact_path),
                "existing_path": exact_path,
                "conflict_type": "target_path",
            }
        elif subtitle_conflicts:
            dedup_result = {
                "is_duplicate": True,
                "existing_file": os.path.basename(subtitle_conflicts[0]),
                "existing_path": subtitle_conflicts[0],
                "conflict_type": "target_bundle",
                "subtitle_conflicts": subtitle_conflicts,
                "replace_allowed": False,
            }
        elif self.config.dedup.enabled:
            result = check_duplicate(import_path, scraped, strategy, video_path)
            if result["is_duplicate"]:
                dedup_result = result
                dedup_result["conflict_type"] = "same_work"

        if not dedup_result["is_duplicate"]:
            return DedupDecision(action="continue", result=dedup_result)

        # 现有替换流程已经保证“旧视频先入本地回收区”，但带字幕作品还需要
        # 对视频和字幕做完整的替换事务。该事务未完成前不展示替换按钮，避免
        # 视频已换、字幕未发布的半完成作品；用户仍可保留现有或另存一份。
        if subtitle_plan:
            dedup_result.update({
                "replace_allowed": False,
                "replace_block_reason": "incoming_subtitle_bundle",
            })
        if task.get("task_kind") == "REORGANIZE":
            dedup_result.update({
                "replace_allowed": False,
                "replace_block_reason": "reorganization_preserves_existing",
            })

        existing_path = os.path.realpath(str(dedup_result.get("existing_path", "")))
        existing_stat = os.stat(existing_path)
        new_stat = os.stat(video_path) if os.path.isfile(video_path) else None
        dedup_result.update({
            "status": "awaiting_user",
            "existing_path": existing_path,
            "existing_file": os.path.basename(existing_path),
            # 首次冲突展示只记录轻量文件快照，避免打开任务详情时读取整部影片。
            # 只有用户明确选择“替换”后，才会计算完整指纹。
            "existing_fingerprint": "",
            "existing_stat": _stat_snapshot(existing_stat),
            "existing_size": os.path.getsize(existing_path),
            "existing_resolution": _resolution_of(existing_path),
            "new_path": video_path,
            "new_file": os.path.basename(video_path),
            "new_fingerprint": "",
            "new_stat": _stat_snapshot(new_stat) if new_stat else {},
            "new_size": os.path.getsize(video_path) if os.path.isfile(video_path) else 0,
            "new_resolution": str(scraped.get("resolution") or _resolution_of(video_path)),
            "expected_target_path": exact_path,
            "suggested_filename": _available_copy_name(import_path, final_filename or os.path.basename(video_path)),
            "detected_at": datetime.now().isoformat(),
            "message": (
                "片库中已存在同一影片；本次还包含字幕，为保护作品完整性，"
                "暂不开放整包替换，可保留现有或另存一份"
                if dedup_result.get("replace_allowed") is False and subtitle_plan
                else "片库中已存在同一影片，现有文件未发生任何改动"
            ),
        })
        return DedupDecision(
            action="review",
            result=dedup_result,
            message=dedup_result["message"],
        )

    def prepare_replace(self, task: dict, conflict: dict) -> dict:
        """用户明确替换后绑定当前片库文件的完整指纹。

        冲突展示阶段只做 stat 快照；这里先确认规则仍指向同一个片库、文件身份
        未变化，再读取完整内容。后续发布前和占位后仍会各复核一次完整指纹。
        """
        snapshot = dict(conflict or {})
        if snapshot.get("replace_allowed") is False:
            snapshot.update({
                "status": "awaiting_user",
                "resolved_action": "",
                "message": snapshot.get("message")
                or "该作品包含字幕，当前不支持整包替换，请保留现有或另存一份",
            })
            raise PipelineReviewRequired(snapshot["message"], snapshot)
        existing_path = os.path.realpath(str(snapshot.get("existing_path", "")))
        import_path = os.path.realpath(str(task.get("import_path", "")))

        try:
            within_current_target = (
                bool(existing_path)
                and bool(import_path)
                and os.path.commonpath((existing_path, import_path)) == import_path
            )
        except ValueError:
            within_current_target = False
        if not within_current_target:
            snapshot.update({
                "status": "awaiting_user",
                "resolved_action": "",
                "existing_fingerprint": "",
                "message": "规则对应的目标片库已变化，请重新查看冲突后再决定",
            })
            raise PipelineReviewRequired(snapshot["message"], snapshot)

        if os.path.islink(existing_path) or not os.path.isfile(existing_path):
            snapshot.update({
                "status": "awaiting_user",
                "resolved_action": "",
                "existing_fingerprint": "",
                "message": "片库现有文件已发生变化，请重新查看后再决定",
            })
            raise PipelineReviewRequired(snapshot["message"], snapshot)

        current_stat = os.stat(existing_path)
        recorded_stat = snapshot.get("existing_stat") or {}
        if recorded_stat and not _same_stat(recorded_stat, current_stat):
            snapshot.update({
                "status": "awaiting_user",
                "resolved_action": "",
                "existing_fingerprint": "",
                "existing_stat": _stat_snapshot(current_stat),
                "existing_size": current_stat.st_size,
                "message": "片库现有文件已发生变化，已停止替换，请重新查看后确认",
            })
            raise PipelineReviewRequired(snapshot["message"], snapshot)

        snapshot.update({
            "existing_fingerprint": hash_file(existing_path),
            "existing_stat": _stat_snapshot(current_stat),
            "existing_size": current_stat.st_size,
            "prepared_at": datetime.now().isoformat(),
        })
        return snapshot


def _stat_snapshot(file_stat: os.stat_result) -> dict:
    return {
        "device": file_stat.st_dev,
        "inode": file_stat.st_ino,
        "size": file_stat.st_size,
        "mtime_ns": file_stat.st_mtime_ns,
    }


def _same_stat(recorded: dict, current: os.stat_result) -> bool:
    expected = _stat_snapshot(current)
    return all(recorded.get(key) == value for key, value in expected.items())


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
