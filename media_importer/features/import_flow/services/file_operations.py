import os
import stat
import uuid
from typing import Optional

from media_importer.features.import_flow.utils import PipelineReviewRequired
from media_importer.features.recycle import move_to_recycle
from media_importer.infrastructure.filesystem import (
    check_write_permission,
    hash_file,
    safe_delete,
    safe_move,
    validate_path_safety,
    verified_copy,
)

from .naming import (
    apply_filename_template,
    apply_subtitle_template,
    detect_subtitle_lang,
)


def move_to_import(video_path: str, subtitle_paths: list[str], import_dir: str,
                   scraped_info: dict, filename_templates: dict,
                   allowed_base_dirs: Optional[list] = None, overwrite: bool = False,
                   final_filename: str = "", recycle_dir: str = "",
                   task_id: str = "", expected_conflict: Optional[dict] = None,
                   import_roots: Optional[list] = None) -> dict:
    ok, msg = validate_path_safety(import_dir, allowed_base_dirs)
    if not ok:
        raise IOError(f"入库路径安全检查失败: {msg}")

    protected_import_roots = [
        os.path.realpath(root)
        for root in (import_roots or [import_dir])
        if root
    ]
    incoming_paths = [video_path, *(str(path) for path in subtitle_paths if path)]
    if any(
        os.path.commonpath((os.path.realpath(path), root)) == root
        for path in incoming_paths
        for root in protected_import_roots
    ):
        raise IOError("待入库视频或字幕不能来自目标片库；已停止操作以保护片库文件")

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

    final_video_filename = os.path.basename(final_filename) if final_filename else apply_filename_template(scraped_info, template, video_ext)
    dest_video = os.path.join(import_dir, final_video_filename)

    if overwrite:
        snapshot = expected_conflict or {}
        existing_path = os.path.realpath(str(snapshot.get("existing_path", "")))
        expected_fingerprint = str(snapshot.get("existing_fingerprint", ""))
        if (
            not existing_path
            or os.path.islink(existing_path)
            or not os.path.isfile(existing_path)
        ):
            snapshot.update({"status": "awaiting_user", "message": "片库现有文件已发生变化，请重新选择"})
            raise PipelineReviewRequired(snapshot["message"], snapshot)
        if not any(
            os.path.commonpath((existing_path, root)) == root
            for root in protected_import_roots
        ):
            raise IOError("确认替换的现有文件不在目标片库内，已停止操作")
        ok, msg = validate_path_safety(existing_path, allowed_base_dirs)
        if not ok:
            raise IOError(f"片库现有文件超出已授权目录: {msg}")
        if not expected_fingerprint or hash_file(existing_path) != expected_fingerprint:
            snapshot.update({
                "status": "awaiting_user",
                "existing_fingerprint": hash_file(existing_path),
                "existing_size": os.path.getsize(existing_path),
                "message": "片库现有文件已发生变化，已停止替换，请重新查看后确认",
            })
            raise PipelineReviewRequired(snapshot["message"], snapshot)
        if not recycle_dir or not os.path.isdir(recycle_dir):
            snapshot.update({"status": "awaiting_user", "message": "本地回收目录不可用，片库现有文件已保留"})
            raise PipelineReviewRequired(snapshot["message"], snapshot)

        dest_video = existing_path
        final_video_filename = os.path.basename(dest_video)
        replacement_id = uuid.uuid4().hex
        staged_video = dest_video + f".{replacement_id}.replacement.tmp"
        claimed_video = dest_video + f".{replacement_id}.replacement.original.tmp"
        incoming_stat = os.lstat(video_path)
        copied, copy_message = verified_copy(video_path, staged_video)
        if not copied:
            raise IOError(f"新文件准备失败，片库现有文件未改动: {copy_message}")

        claimed, claim_message = safe_move(existing_path, claimed_video, allowed_base_dirs)
        if not claimed:
            safe_delete(staged_video, allowed_base_dirs)
            snapshot.update({
                "status": "awaiting_user",
                "message": f"片库现有文件在替换前发生变化，已停止操作: {claim_message}",
            })
            raise PipelineReviewRequired(snapshot["message"], snapshot)

        claimed_fingerprint = hash_file(claimed_video)
        if claimed_fingerprint != expected_fingerprint:
            restored, restore_message = safe_move(claimed_video, existing_path, allowed_base_dirs)
            safe_delete(staged_video, allowed_base_dirs)
            snapshot.update({
                "status": "awaiting_user",
                "existing_fingerprint": claimed_fingerprint,
                "existing_size": os.path.getsize(existing_path if restored else claimed_video),
                "message": (
                    "片库现有文件在准备新文件期间发生变化，已恢复原位，请重新查看后确认"
                    if restored else
                    f"片库现有文件在准备期间发生变化，且原位置出现了其他文件；"
                    f"变化后的原文件保留在 {claimed_video}，请人工确认: {restore_message}"
                ),
            })
            if not restored:
                snapshot["preserved_path"] = claimed_video
            raise PipelineReviewRequired(snapshot["message"], snapshot)

        ok, recycled_path, recycle_message = move_to_recycle(
            claimed_video,
            recycle_dir,
            reason="confirmed_target_replace",
            task_id=task_id,
            import_roots=protected_import_roots,
            extra_meta={
                "original_path": existing_path,
                "original_fingerprint": expected_fingerprint,
                "replacement_fingerprint": hash_file(staged_video),
            },
        )
        if not ok:
            restored, restore_message = safe_move(claimed_video, existing_path, allowed_base_dirs)
            safe_delete(staged_video, allowed_base_dirs)
            if not restored:
                raise IOError(
                    f"片库现有文件回收失败，原文件保留在 {claimed_video}，"
                    f"自动恢复失败: {restore_message}; {recycle_message}"
                )
            raise IOError(f"片库现有文件回收失败，原文件已恢复且未执行替换: {recycle_message}")

        if hash_file(recycled_path) != expected_fingerprint:
            restored, restore_message = safe_move(recycled_path, dest_video, allowed_base_dirs)
            safe_delete(staged_video, allowed_base_dirs)
            if not restored:
                raise IOError(
                    f"回收后的原文件完整性校验失败，文件保留在 {recycled_path}，"
                    f"自动恢复也失败: {restore_message}"
                )
            raise IOError("回收后的原文件完整性校验失败，片库原文件已自动恢复")

        published, publish_message = safe_move(staged_video, dest_video, allowed_base_dirs)
        if not published:
            restored, restore_message = safe_move(recycled_path, dest_video, allowed_base_dirs)
            if not restored:
                raise IOError(
                    f"新文件发布失败，未覆盖当前目标；原文件保留在回收区 {recycled_path}: "
                    f"{publish_message}; 自动恢复失败: {restore_message}"
                )
            raise IOError("新文件发布失败，片库原文件已自动恢复且未发生覆盖")

        source_retained = True
        try:
            current_stat = os.lstat(video_path)
            if (
                stat.S_ISREG(current_stat.st_mode)
                and current_stat.st_dev == incoming_stat.st_dev
                and current_stat.st_ino == incoming_stat.st_ino
                and current_stat.st_size == incoming_stat.st_size
                and current_stat.st_mtime_ns == incoming_stat.st_mtime_ns
            ):
                deleted, _delete_message = safe_delete(video_path, allowed_base_dirs)
                source_retained = not deleted
        except FileNotFoundError:
            source_retained = False
        result = {
            "video": dest_video,
            "subtitles": [],
            "replaced": True,
            "source_retained": source_retained,
        }
        return _move_subtitles(result, subtitle_paths, import_dir, final_video_filename, allowed_base_dirs)

    if os.path.exists(dest_video):
        raise IOError("目标文件冲突尚未确认，已停止入库且未改动片库")

    ok, msg = safe_move(video_path, dest_video, allowed_base_dirs)
    if not ok:
        raise IOError(f"视频文件移动失败: {msg}")

    result = {'video': dest_video, 'subtitles': []}
    return _move_subtitles(result, subtitle_paths, import_dir, final_video_filename, allowed_base_dirs)


def _move_subtitles(result: dict, subtitle_paths: list[str], import_dir: str,
                    final_video_filename: str,
                    allowed_base_dirs: Optional[list] = None) -> dict:

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
