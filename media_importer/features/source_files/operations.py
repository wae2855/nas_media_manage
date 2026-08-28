import os
from typing import Optional

from media_importer.infrastructure.filesystem import safe_delete


def delete_source_files(source_paths: list[str], allowed_base_dirs: Optional[list] = None):
    for path in source_paths:
        ok, _ = safe_delete(path, allowed_base_dirs)
        if not ok:
            pass


def find_companion_files(video_path: str, subtitle_paths: list,
                         video_extensions: list, subtitle_extensions: list) -> list:
    video_dir = os.path.dirname(video_path)
    video_basename = os.path.splitext(os.path.basename(video_path))[0]
    known_files = {os.path.basename(video_path)}
    for subtitle_path in subtitle_paths:
        known_files.add(os.path.basename(subtitle_path))

    companion_files = []
    if not os.path.isdir(video_dir):
        return companion_files

    for filename in os.listdir(video_dir):
        if filename in known_files:
            continue
        file_ext = os.path.splitext(filename)[1].lower()
        if file_ext in video_extensions or file_ext in subtitle_extensions:
            continue
        if filename.startswith(video_basename):
            companion_files.append(os.path.join(video_dir, filename))

    return companion_files


def delete_source_with_companions(video_path: str, subtitle_paths: list,
                                  video_extensions: list, subtitle_extensions: list,
                                  allowed_base_dirs: Optional[list] = None):
    files_to_delete = [video_path]
    files_to_delete.extend(subtitle_paths)
    companions = find_companion_files(
        video_path,
        subtitle_paths,
        video_extensions,
        subtitle_extensions,
    )
    files_to_delete.extend(companions)
    delete_source_files(files_to_delete, allowed_base_dirs)
    return len(companions)


def cleanup_source_non_media(source_dir: str, video_extensions: list, subtitle_extensions: list,
                             allowed_base_dirs: Optional[list] = None):
    if not source_dir or not os.path.isdir(source_dir):
        return 0, 0
    media_exts = set(ext.lower() for ext in video_extensions) | set(
        ext.lower() for ext in subtitle_extensions
    )
    deleted_files = 0
    deleted_dirs = 0

    for root, _dirs, files in os.walk(source_dir, topdown=False):
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in media_exts:
                file_path = os.path.join(root, filename)
                ok, _ = safe_delete(file_path, allowed_base_dirs or [source_dir])
                if ok:
                    deleted_files += 1
        if root != os.path.normpath(source_dir):
            try:
                remaining = os.listdir(root)
                if not remaining:
                    os.rmdir(root)
                    deleted_dirs += 1
            except OSError:
                pass

    return deleted_files, deleted_dirs


def remove_empty_parent_dir(file_path: str, source_root: str, allowed_base_dirs: Optional[list] = None,
                            video_extensions: Optional[list] = None, subtitle_extensions: Optional[list] = None):
    if not source_root:
        return
    source_root_norm = os.path.normpath(source_root).rstrip('/')
    current = os.path.dirname(os.path.normpath(file_path))

    while current and current != source_root_norm:
        if not current.startswith(source_root_norm):
            break
        if not os.path.isdir(current):
            break
        try:
            remaining = os.listdir(current)
        except OSError:
            break
        if not remaining:
            try:
                os.rmdir(current)
            except OSError:
                break
            current = os.path.dirname(current)
            continue
        break
