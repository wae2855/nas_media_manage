#!/usr/bin/env python3
import os
import re
import time
from typing import List, Optional, Tuple

from media_importer.features.configuration import ConfigView


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
        return self._group_videos(all_files)

    def _group_videos(self, all_files: List[str]) -> List[dict]:
        video_files = []
        subtitle_file_sets = []
        seen = set()
        video_set = {
            f for f in all_files
            if f.lower().endswith(self.video_extensions)
        }
        subtitle_set = {
            f for f in all_files
            if f.lower().endswith(self.subtitle_extensions)
        }

        groups = {}
        for vf in video_set:
            basename_no_ext = os.path.splitext(os.path.basename(vf))[0]
            clean_name = self._clean_name(basename_no_ext)
            if clean_name not in groups:
                groups[clean_name] = {"video": vf, "subtitles": []}
            else:
                groups[clean_name]["video"] = vf
            matched_subs = []
            for sf in subtitle_set:
                sf_basename = os.path.basename(sf)
                if clean_name in sf_basename or basename_no_ext in sf_basename:
                    matched_subs.append(sf)
            for ms in matched_subs:
                groups[clean_name]["subtitles"].append(ms)
                subtitle_set.discard(ms)

        remaining_subs = list(subtitle_set)
        for vf in video_set:
            vdir = os.path.dirname(vf)
            vbase = os.path.splitext(os.path.basename(vf))[0]
            for sf in remaining_subs:
                if sf.startswith(vdir) and vbase in sf:
                    groups.setdefault(
                        self._clean_name(vbase),
                        {"video": vf, "subtitles": []}
                    )["subtitles"].append(sf)
                    subtitle_set.discard(sf)

        result = []
        for clean_name, info in groups.items():
            vpath = info["video"]
            vfile = os.path.basename(vpath)
            try:
                fsize = os.path.getsize(vpath)
                fsize_mb = round(fsize / (1024 * 1024), 4)
            except OSError:
                fsize_mb = 0
            subtitles = info["subtitles"]
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
                from media_importer.core.safety import make_fingerprint
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
