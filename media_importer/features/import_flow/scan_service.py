#!/usr/bin/env python3
import os
import re
import time
from typing import List

from media_importer.features.configuration import ConfigView
from media_importer.features.source_files.media_candidates import MediaCandidatePolicy


class FileScanner:

    def __init__(self, config: dict, task_manager=None):
        self.config = config
        view = ConfigView.from_dict(config)
        self.task_manager = task_manager
        self.scan_source = view.scanner.scan_source
        self.skip_existing = view.scanner.skip_existing
        self.sort_by = view.scanner.sort_by
        self.sort_reverse = view.scanner.sort_reverse
        self.group_delay_sec = view.scanner.group_delay_sec
        self.video_extensions = view.paths.video_extensions
        self.subtitle_extensions = view.paths.subtitle_extensions
        self.candidate_policy = MediaCandidatePolicy(config)
        self.last_ignored_candidates: list[dict] = []

    def scan_path(self, directory: str) -> List[dict]:
        if not os.path.isdir(directory):
            return []
        all_files = []
        for root, dirs, files in os.walk(directory):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in sorted(files):
                fpath = os.path.join(root, f)
                if not os.path.isfile(fpath):
                    continue
                all_files.append(fpath)
        return self._group_videos(all_files, source_root=directory)

    def _group_videos(
        self,
        all_files: List[str],
        *,
        source_root: str = "",
    ) -> List[dict]:
        discovered_video_paths = sorted({
            f for f in all_files
            if f.lower().endswith(self.video_extensions)
        })
        decisions = self.candidate_policy.classify_tree(
            source_root or os.path.commonpath(discovered_video_paths or [os.curdir]),
            discovered_video_paths,
        )
        self.last_ignored_candidates = [
            {
                "path": path,
                "disposition": decision.disposition,
                "reason": decision.reason,
                "evidence": decision.evidence,
            }
            for path, decision in decisions.items()
            if not decision.accepted
        ]
        video_paths = sorted(
            path for path in discovered_video_paths
            if decisions.get(os.path.realpath(path), None) is None
            or decisions[os.path.realpath(path)].accepted
        )
        subtitle_paths = sorted({
            f for f in all_files
            if f.lower().endswith(self.subtitle_extensions)
        })

        groups = {
            vf: {"video": vf, "subtitles": []}
            for vf in video_paths
        }
        for subtitle_path in subtitle_paths:
            candidates = [
                video_path
                for video_path in video_paths
                if self._subtitle_matches(video_path, subtitle_path)
            ]
            if not candidates:
                continue
            # 同名视频同时存在时，优先同目录，其次选择目录距离最近的一项。
            candidates.sort(
                key=lambda video_path: (
                    os.path.dirname(video_path) != os.path.dirname(subtitle_path),
                    self._directory_distance(video_path, subtitle_path),
                    video_path.casefold(),
                )
            )
            groups[candidates[0]]["subtitles"].append(subtitle_path)

        result = []
        for _video_path, info in groups.items():
            vpath = info["video"]
            vfile = os.path.basename(vpath)
            try:
                fsize = os.path.getsize(vpath)
                fsize_mb = round(fsize / (1024 * 1024), 4)
            except OSError:
                fsize_mb = 0
            subtitles = sorted(info["subtitles"], key=lambda path: path.casefold())
            video_dir = os.path.dirname(vpath)
            result.append({
                "video_path": vpath,
                "video_file": vfile,
                "video_dir": video_dir,
                "file_size_mb": fsize_mb,
                "subtitle_files": subtitles,
            })

        if self.sort_by == "filename":
            result.sort(key=lambda x: x["video_file"], reverse=self.sort_reverse)
        elif self.sort_by == "size":
            result.sort(key=lambda x: x["file_size_mb"], reverse=self.sort_reverse)
        return result

    def _subtitle_matches(self, video_path: str, subtitle_path: str) -> bool:
        video_dir = os.path.realpath(os.path.dirname(video_path))
        subtitle_dir = os.path.realpath(os.path.dirname(subtitle_path))
        if subtitle_dir != video_dir:
            parent_name = os.path.basename(subtitle_dir).casefold()
            if parent_name not in {"sub", "subs", "subtitle", "subtitles", "字幕"}:
                return False
            if os.path.realpath(os.path.dirname(subtitle_dir)) != video_dir:
                return False

        video_stem = os.path.splitext(os.path.basename(video_path))[0]
        subtitle_stem = os.path.splitext(os.path.basename(subtitle_path))[0]
        return self._subtitle_key(subtitle_stem) == self._subtitle_key(video_stem)

    @staticmethod
    def _subtitle_key(stem: str) -> str:
        value = stem.casefold()
        suffixes = (
            "forced", "default", "sdh", "cc", "commentary", "chs", "cht",
            "chi", "zh-cn", "zh-tw", "zh", "cn", "sc", "tc", "eng", "en",
            "jpn", "ja", "kor", "ko", "简体", "繁体", "中文", "英文", "中英",
        )
        token_pattern = "|".join(re.escape(token) for token in suffixes)
        value = re.sub(
            rf"(?:[. _-]+(?:{token_pattern}))(?:[. _-]*\d+)?$",
            "",
            value,
            flags=re.IGNORECASE,
        )
        return re.sub(r"[. _-]+", " ", value).strip()

    @staticmethod
    def _directory_distance(video_path: str, subtitle_path: str) -> int:
        video_parts = os.path.dirname(video_path).split(os.sep)
        subtitle_parts = os.path.dirname(subtitle_path).split(os.sep)
        shared = 0
        for left, right in zip(video_parts, subtitle_parts, strict=False):
            if left != right:
                break
            shared += 1
        return (len(video_parts) - shared) + (len(subtitle_parts) - shared)

    def scan_and_group(self, directory: str) -> List[dict]:
        return self.scan_path(directory)

    def scan_and_filter(self, source_dir: str) -> List[dict]:
        groups = self.scan_and_group(source_dir)
        if not self.task_manager:
            return groups
        filtered = []
        for g in groups:
            fingerprint = ""
            if os.path.isfile(g["video_path"]):
                from media_importer.infrastructure.filesystem import make_fingerprint
                fingerprint = make_fingerprint(g["video_path"])

            dedup = self.task_manager.check_source_duplicate(
                g["video_path"], source_fingerprint=fingerprint
            )

            if dedup["action"] == "SKIP":
                if dedup.get("task_id"):
                    self.task_manager.update_task({
                        "task_id": dedup["task_id"],
                        "last_seen_at": time.strftime(
                            "%Y-%m-%dT%H:%M:%S", time.localtime()
                        ),
                    })
                continue

            if dedup["action"] == "RENAME_DETECTED":
                if dedup.get("task_id"):
                    self.task_manager.update_task({
                        "task_id": dedup["task_id"],
                        "source_path": g["video_path"],
                        "source_filename": os.path.basename(g["video_path"]),
                        "source_fingerprint": fingerprint,
                        "last_seen_at": time.strftime(
                            "%Y-%m-%dT%H:%M:%S", time.localtime()
                        ),
                    })
                continue

            if dedup["action"] == "UPDATE_MTIME":
                if dedup.get("task_id"):
                    self.task_manager.update_task({
                        "task_id": dedup["task_id"],
                        "source_fingerprint": fingerprint,
                        "source_mtime": time.strftime(
                            "%Y-%m-%dT%H:%M:%S", time.localtime()
                        ),
                        "last_seen_at": time.strftime(
                            "%Y-%m-%dT%H:%M:%S", time.localtime()
                        ),
                    })
                continue

            g["source_fingerprint"] = fingerprint
            g["source_file_size"] = os.path.getsize(g["video_path"]) if os.path.isfile(g["video_path"]) else 0
            g["source_mtime"] = time.strftime(
                "%Y-%m-%dT%H:%M:%S", time.localtime(
                    os.path.getmtime(g["video_path"])
                )
            ) if os.path.isfile(g["video_path"]) else ""

            filtered.append(g)
        return filtered

    def _clean_name(self, name: str) -> str:
        name = re.sub(
            r"(?i)(\.\w{2,4})$", "", name
        )
        name = re.sub(
            r"(?i)(1080[pi]|720[pi]|2160[pi]|4k|bluray|web[ -]?dl|hdtv|x264|x265|hevc|aac|dd5[.]?1|ac3)",
            "", name
        )
        name = re.sub(r"[.\s_\-]+", " ", name).strip()
        return name.lower()


def scan_source_dir(source_dir: str, config: dict, task_manager=None) -> list:
    scanner = FileScanner(config, task_manager=task_manager)
    return scanner.scan_and_filter(source_dir)
