#!/usr/bin/env python3
import os
import shutil
import re
from safety import validate_path_safety, safe_delete, safe_move, check_write_permission, ALLOWED_MEDIA_EXTS
from classifier import render_template


def apply_filename_template(scraped_info: dict, template: str, video_ext: str) -> str:
    filename = render_template(template, scraped_info, extra_vars={'ext': video_ext})
    filename = filename.rstrip('/')
    if '{ext}' not in template:
        if not filename.endswith(video_ext):
            filename = filename + video_ext
    return filename


def apply_subtitle_template(video_basename: str, lang: str, subtitle_ext: str) -> str:
    video_name_without_ext = os.path.splitext(video_basename)[0]
    return f"{video_name_without_ext}.{lang}{subtitle_ext}"


def move_to_import(video_path: str, subtitle_paths: list[str], import_dir: str,
                   scraped_info: dict, filename_templates: dict,
                   allowed_base_dirs: list = None) -> dict:
    ok, msg = check_write_permission(import_dir)
    if not ok:
        raise IOError(f"入库目录不可写: {msg}")

    ok, msg = validate_path_safety(import_dir, allowed_base_dirs)
    if not ok:
        raise IOError(f"入库路径安全检查失败: {msg}")

    os.makedirs(import_dir, exist_ok=True)

    video_ext = os.path.splitext(video_path)[1]

    if scraped_info.get('type') == 'tv':
        template = filename_templates.get('tv', '{title_cn}.{title_en}.{year}.S{season}E{episode}.{ext}')
    else:
        template = filename_templates.get('movie', '{title_cn}.{title_en}.{year}.{resolution}.{quality}.{ext}')

    final_video_filename = apply_filename_template(scraped_info, template, video_ext)
    dest_video = os.path.join(import_dir, final_video_filename)

    if os.path.exists(dest_video):
        raise IOError(
            f"目标已存在同名文件: {final_video_filename}\n"
            f"路径: {dest_video}\n"
            f"提示: 当前关闭了智能同名检测，无法自动处理冲突。\n"
            f"请手动处理已存在的文件，或开启智能同名检测后使用替换/重命名等策略。"
        )

    ok, msg = safe_move(video_path, dest_video, allowed_base_dirs)
    if not ok:
        raise IOError(f"视频文件移动失败: {msg}")

    result = {
        'video': dest_video,
        'subtitles': []
    }

    for sub_path in subtitle_paths:
        sub_filename = os.path.basename(sub_path)
        lang = detect_subtitle_lang(sub_filename)
        subtitle_ext = os.path.splitext(sub_path)[1]
        final_sub_filename = apply_subtitle_template(final_video_filename, lang, subtitle_ext)
        dest_sub = os.path.join(import_dir, final_sub_filename)
        ok, msg = safe_move(sub_path, dest_sub, allowed_base_dirs)
        if not ok:
            raise IOError(f"字幕文件移动失败: {msg}")
        result['subtitles'].append(dest_sub)

    return result


def detect_subtitle_lang(filename: str) -> str:
    name_lower = filename.lower()
    if '.zh.' in name_lower or '.chs.' in name_lower or 'chinese' in name_lower:
        return 'zh'
    elif '.en.' in name_lower or '.eng.' in name_lower or 'english' in name_lower:
        return 'en'
    elif '.ja.' in name_lower or '.jpn.' in name_lower or 'japanese' in name_lower:
        return 'ja'
    elif '.ko.' in name_lower or '.kor.' in name_lower or 'korean' in name_lower:
        return 'ko'
    return 'unknown'


def delete_source_files(source_paths: list[str], allowed_base_dirs: list = None):
    for path in source_paths:
        ok, msg = safe_delete(path, allowed_base_dirs)
        if not ok:
            pass


def find_companion_files(video_path: str, subtitle_paths: list, video_extensions: list, subtitle_extensions: list) -> list:
    video_dir = os.path.dirname(video_path)
    video_basename = os.path.splitext(os.path.basename(video_path))[0]
    known_files = set()
    known_files.add(os.path.basename(video_path))
    for sp in subtitle_paths:
        known_files.add(os.path.basename(sp))

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
                                   allowed_base_dirs: list = None):
    files_to_delete = [video_path]
    files_to_delete.extend(subtitle_paths)
    companions = find_companion_files(video_path, subtitle_paths, video_extensions, subtitle_extensions)
    files_to_delete.extend(companions)
    delete_source_files(files_to_delete, allowed_base_dirs)
    return len(companions)


def cleanup_source_non_media(source_dir: str, video_extensions: list, subtitle_extensions: list):
    if not source_dir or not os.path.isdir(source_dir):
        return 0, 0
    media_exts = set(ext.lower() for ext in video_extensions) | set(ext.lower() for ext in subtitle_extensions)
    deleted_files = 0
    deleted_dirs = 0

    for root, dirs, files in os.walk(source_dir, topdown=False):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in media_exts:
                file_path = os.path.join(root, f)
                try:
                    os.remove(file_path)
                    deleted_files += 1
                except OSError:
                    pass
        if root != os.path.normpath(source_dir):
            try:
                remaining = os.listdir(root)
                if not remaining:
                    os.rmdir(root)
                    deleted_dirs += 1
            except OSError:
                pass

    return deleted_files, deleted_dirs


def remove_empty_parent_dir(file_path: str, source_root: str, allowed_base_dirs: list = None,
                            video_extensions: list = None, subtitle_extensions: list = None):
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


def move_with_cross_device_fallback(src: str, dest: str) -> bool:
    ok, msg = safe_move(src, dest)
    return ok
