import os
from typing import Optional

from media_importer.features.recycle import move_to_recycle
from media_importer.infrastructure.filesystem import (
    check_write_permission,
    safe_delete,
    safe_move,
    validate_path_safety,
)

from .naming import (
    apply_filename_template,
    apply_subtitle_template,
    detect_subtitle_lang,
)


def move_to_import(video_path: str, subtitle_paths: list[str], import_dir: str,
                   scraped_info: dict, filename_templates: dict,
                   allowed_base_dirs: Optional[list] = None, overwrite: bool = False) -> dict:
    ok, msg = validate_path_safety(import_dir, allowed_base_dirs)
    if not ok:
        raise IOError(f"入库路径安全检查失败: {msg}")

    if allowed_base_dirs:
        import_real = os.path.realpath(import_dir)
        existing_roots = [
            os.path.realpath(root)
            for root in allowed_base_dirs
            if root and os.path.isdir(root)
        ]
        if not any(
            os.path.commonpath([import_real, root]) == root
            for root in existing_roots
        ):
            raise IOError("入库根目录不存在或挂载已失效，拒绝自动创建同名路径")

    os.makedirs(import_dir, exist_ok=True)
    ok, msg = check_write_permission(import_dir)
    if not ok:
        raise IOError(f"入库目录不可写: {msg}")

    video_ext = os.path.splitext(video_path)[1]

    if scraped_info.get('media_type') == 'tv':
        template = filename_templates.get('tv', '{title_cn}.{title_en}.{year}.S{season}E{episode}.{ext}')
    else:
        template = filename_templates.get('movie', '{title_cn}.{title_en}.{year}.{resolution}.{quality}.{ext}')

    final_video_filename = apply_filename_template(scraped_info, template, video_ext)
    dest_video = os.path.join(import_dir, final_video_filename)

    if os.path.exists(dest_video):
        if overwrite:
            recycle_dir = ""
            ok, _, msg = move_to_recycle(dest_video, recycle_dir, reason="import_overwrite")
            if not ok:
                ok, msg = safe_delete(dest_video, allowed_base_dirs)
                if not ok:
                    raise IOError(f"目标文件回收失败且无法安全删除: {msg}")
        else:
            # S3 幂等：同指纹（大小+mtime）视为同一文件重复导入 → 幂等成功
            from media_importer.infrastructure.filesystem import make_fingerprint
            try:
                if make_fingerprint(dest_video) == make_fingerprint(video_path):
                    result = {
                        'video': dest_video,
                        'subtitles': [],
                        'idempotent': True,
                        'message': f"目标已存在同指纹文件，幂等跳过: {final_video_filename}",
                    }
                    # 源 temp 文件按源策略清理
                    return result
            except Exception:
                pass  # 指纹失败回退到冲突报错
            raise IOError(
                f"目标已存在同名文件（指纹不同）: {final_video_filename}\n"
                f"路径: {dest_video}\n"
                f"提示: 同名去重检测未拦截到此冲突。\n"
                f"请手动处理已存在的文件，或检查 duplicate_handling 配置。"
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
        # 防御：同语言多字幕目标同名时追加序号，避免字幕冲突阻断入库
        if os.path.exists(dest_sub):
            base, ext = os.path.splitext(final_sub_filename)
            seq = 1
            while os.path.exists(os.path.join(import_dir, f"{base}.{seq}{ext}")):
                seq += 1
            dest_sub = os.path.join(import_dir, f"{base}.{seq}{ext}")
        ok, msg = safe_move(sub_path, dest_sub, allowed_base_dirs)
        if not ok:
            raise IOError(f"字幕文件移动失败: {msg}")
        result['subtitles'].append(dest_sub)

    return result


def move_with_cross_device_fallback(src: str, dest: str) -> bool:
    ok, msg = safe_move(src, dest)
    return ok
