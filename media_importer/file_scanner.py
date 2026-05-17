#!/usr/bin/env python3
import os
import fnmatch
from pathlib import Path


def match_filename_pattern(filename, patterns):
    for pattern in patterns:
        if fnmatch.fnmatch(filename, pattern):
            return True
    return False


def find_video_files(source_dir, extensions, ignore_patterns, max_depth):
    video_files = []
    source_path = Path(source_dir)

    if not source_path.exists():
        return video_files

    for root, dirs, files in os.walk(source_dir):
        current_depth = len(Path(root).relative_to(source_path).parts)

        if current_depth > max_depth:
            dirs[:] = []
            continue

        for filename in files:
            if match_filename_pattern(filename, ignore_patterns):
                continue

            file_ext = os.path.splitext(filename)[1].lower()
            if file_ext in extensions:
                video_files.append(os.path.join(root, filename))

    return sorted(video_files)


def find_subtitle_files(video_path, subtitle_extensions):
    video_dir = os.path.dirname(video_path)
    video_name = os.path.splitext(os.path.basename(video_path))[0]

    subtitles = []

    if not os.path.exists(video_dir):
        return subtitles

    for filename in os.listdir(video_dir):
        file_ext = os.path.splitext(filename)[1].lower()
        if file_ext not in subtitle_extensions:
            continue

        if filename.startswith(video_name):
            subtitles.append(os.path.join(video_dir, filename))

    return sorted(subtitles)


def scan_source_dir(source_dir: str, config: dict) -> list:
    source_dir_config = config.get('source_dir_scan', {})
    recursive = source_dir_config.get('recursive', True)
    max_depth = source_dir_config.get('max_depth', 5) if recursive else 0
    ignore_patterns = source_dir_config.get('ignore_patterns', ['*.tmp', '.DS_Store'])

    video_extensions = [ext.lower() for ext in config.get('video_extensions', ['.mkv', '.mp4', '.avi'])]
    subtitle_extensions = [ext.lower() for ext in config.get('subtitle_extensions', ['.srt', '.ass', '.ssa'])]

    video_files = find_video_files(source_dir, video_extensions, ignore_patterns, max_depth)

    groups = []
    for video_path in video_files:
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        subtitles = find_subtitle_files(video_path, subtitle_extensions)

        groups.append({
            'video': video_path,
            'subtitles': subtitles,
            'group_name': video_name
        })

    return groups
