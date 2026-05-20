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


def remove_empty_parent_dir(file_path: str, source_root: str, allowed_base_dirs: list = None):
    if not source_root:
        return
    parent = os.path.dirname(os.path.normpath(file_path))
    if not parent or not parent.startswith(os.path.normpath(source_root).rstrip('/')):
        return
    if os.path.samefile(parent, source_root.rstrip('/')):
        return
    if not os.path.isdir(parent):
        return
    remaining = os.listdir(parent)
    if remaining:
        return
    try:
        os.rmdir(parent)
    except OSError:
        pass


def move_with_cross_device_fallback(src: str, dest: str) -> bool:
    ok, msg = safe_move(src, dest)
    return ok
