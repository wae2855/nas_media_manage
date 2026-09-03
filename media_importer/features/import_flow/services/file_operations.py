import os
import uuid
from typing import Optional

from media_importer.features.import_flow.utils import (
    PipelineReviewRequired,
)
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
    plan_subtitle_filenames,
)


def move_to_import(video_path: str, subtitle_paths: list[str], import_dir: str,
                   scraped_info: dict, filename_templates: dict,
                   allowed_base_dirs: Optional[list] = None, overwrite: bool = False,
                   final_filename: str = "", recycle_dir: str = "",
                   task_id: str = "", expected_conflict: Optional[dict] = None,
                   import_roots: Optional[list] = None,
                   phase_callback=None, journal_callback=None) -> dict:
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
    subtitle_template = filename_templates.get(
        "subtitle", "{video_filename}.{lang}.{ext}"
    )
    subtitle_plan = plan_subtitle_filenames(
        subtitle_paths,
        final_video_filename,
        subtitle_template,
    )
    for member in subtitle_plan:
        member["dest_path"] = os.path.join(import_dir, member["filename"])

    if not overwrite:
        return _publish_new_bundle(
            video_path=video_path,
            dest_video=dest_video,
            subtitle_plan=subtitle_plan,
            allowed_base_dirs=allowed_base_dirs,
            task_id=task_id,
            phase_callback=phase_callback,
            journal_callback=journal_callback,
            copy_source_members=True,
        )

    subtitle_conflicts = [
        member["dest_path"]
        for member in subtitle_plan
        if os.path.lexists(member["dest_path"])
    ]
    if subtitle_conflicts:
        snapshot = dict(expected_conflict or {})
        snapshot.update({
            "status": "awaiting_user",
            "subtitle_conflicts": subtitle_conflicts,
            "message": "目标片库已有同名字幕；为避免产生半完成作品，本次替换尚未执行",
        })
        raise PipelineReviewRequired(snapshot["message"], snapshot)

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
        copied, copy_message = verified_copy(
            video_path,
            staged_video,
            phase_callback=phase_callback,
        )
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

        publish_kwargs = {"phase_callback": phase_callback} if phase_callback else {}
        published, publish_message = safe_move(
            staged_video,
            dest_video,
            allowed_base_dirs,
            **publish_kwargs,
        )
        if not published:
            restored, restore_message = safe_move(recycled_path, dest_video, allowed_base_dirs)
            if not restored:
                raise IOError(
                    f"新文件发布失败，未覆盖当前目标；原文件保留在回收区 {recycled_path}: "
                    f"{publish_message}; 自动恢复失败: {restore_message}"
                )
            raise IOError("新文件发布失败，片库原文件已自动恢复且未发生覆盖")

        result = {
            "video": dest_video,
            "subtitles": [],
            "replaced": True,
            "source_retained": True,
        }
        return _move_subtitles(
            result,
            subtitle_paths,
            import_dir,
            final_video_filename,
            allowed_base_dirs,
            phase_callback,
            subtitle_template,
        )

    raise IOError("无法识别的入库发布模式")


def relocate_library_bundle(
    video_path: str,
    subtitle_paths: list[str],
    import_dir: str,
    final_filename: str,
    filename_templates: dict,
    *,
    library_roots: list[str],
    task_id: str,
    phase_callback=None,
    journal_callback=None,
) -> dict:
    """在已配置片库之间无覆盖地移动一个完整作品文件包。

    这是“重新整理”专用入口。来源和目标都必须位于目标片库，目标目录
    不存在时只能在仍然在线的片库根下创建。发布仍复用文件包事务：字幕
    先发布、影片最后发布，任何一步失败都会尝试退回原片库位置。
    """
    roots = [os.path.realpath(root) for root in library_roots if root and os.path.isdir(root)]
    if not roots:
        raise IOError("没有可用的目标片库，请先运行配置检查")

    sources = [video_path, *(path for path in subtitle_paths if path)]
    for source in sources:
        source_real = os.path.realpath(source)
        if os.path.islink(source) or not os.path.isfile(source):
            raise IOError(f"待整理文件不存在或不是普通文件: {source}")
        if not any(
            os.path.commonpath((source_real, root)) == root
            for root in roots
        ):
            raise IOError("待整理影片或字幕不在已配置片库内，已停止操作")

    target_real = os.path.realpath(import_dir)
    if not any(os.path.commonpath((target_real, root)) == root for root in roots):
        raise IOError("重新整理目标超出已配置片库，已停止操作")
    ok, message = validate_path_safety(import_dir, roots)
    if not ok:
        raise IOError(f"重新整理目标安全检查失败: {message}")
    os.makedirs(import_dir, exist_ok=True)
    ok, message = check_write_permission(import_dir)
    if not ok:
        raise IOError(f"重新整理目标不可写: {message}")

    final_video_filename = os.path.basename(str(final_filename or "").strip())
    if not final_video_filename:
        raise IOError("重新整理缺少最终影片文件名")
    dest_video = os.path.join(import_dir, final_video_filename)
    if os.path.realpath(video_path) == os.path.realpath(dest_video):
        raise IOError("影片已经位于当前规则目标，无需重新整理")

    subtitle_template = (filename_templates or {}).get(
        "subtitle", "{video_filename}.{lang}.{ext}"
    )
    subtitle_plan = plan_subtitle_filenames(
        subtitle_paths,
        final_video_filename,
        subtitle_template,
    )
    for member in subtitle_plan:
        member["dest_path"] = os.path.join(import_dir, member["filename"])

    return _publish_new_bundle(
        video_path=video_path,
        dest_video=dest_video,
        subtitle_plan=subtitle_plan,
        allowed_base_dirs=roots,
        task_id=task_id,
        phase_callback=phase_callback,
        journal_callback=journal_callback,
    )


def _publish_new_bundle(
    *,
    video_path: str,
    dest_video: str,
    subtitle_plan: list[dict],
    allowed_base_dirs: Optional[list],
    task_id: str,
    phase_callback=None,
    journal_callback=None,
    copy_source_members: bool = False,
) -> dict:
    """完整暂存所有成员，字幕先发布、视频最后发布。"""
    members = [
        {"kind": "video", "source_path": video_path, "dest_path": dest_video},
        *[
            {
                "kind": "subtitle",
                "source_path": member["source_path"],
                "dest_path": member["dest_path"],
            }
            for member in subtitle_plan
        ],
    ]
    seen_targets = set()
    for member in members:
        destination = member["dest_path"]
        if destination in seen_targets:
            raise IOError(f"文件包内出现重复目标名称: {os.path.basename(destination)}")
        seen_targets.add(destination)
        if os.path.lexists(destination):
            raise PipelineReviewRequired(
                "目标片库在发布前出现同名文件，文件包尚未写入",
                {
                    "is_duplicate": True,
                    "status": "awaiting_user",
                    "conflict_type": "target_bundle",
                    "existing_path": destination,
                    "existing_file": os.path.basename(destination),
                    "message": "目标片库在发布前出现同名文件，文件包尚未写入",
                },
            )

    operation_id = task_id or uuid.uuid4().hex
    for index, member in enumerate(members):
        member["stage_path"] = (
            member["dest_path"]
            + f".{operation_id}.{index + 1}.bundle.tmp"
        )
        if os.path.lexists(member["stage_path"]):
            raise IOError("发现无法确认归属的旧文件包暂存文件，已停止入库")

    for member in members:
        member["transfer_mode"] = "copy" if copy_source_members else "move"
        # Direct source-to-library transfer obtains this digest from the verified
        # copy itself, avoiding an extra full read of a multi-GB source file.
        member["fingerprint"] = (
            "" if copy_source_members else hash_file(member["source_path"])
        )
        member["state"] = "source"
    if journal_callback:
        journal_callback("PREPARED", members)

    staged: list[dict] = []
    published: list[dict] = []
    member_sizes = [os.path.getsize(member["source_path"]) for member in members]
    total_transfer_bytes = sum(member_sizes)
    completed_before = 0
    try:
        for index, member in enumerate(members):
            def member_phase(phase, completed, total, *, base=completed_before):
                if not phase_callback:
                    return
                if phase in {"resume_check", "transfer", "verify_source", "verify_target"}:
                    phase_callback(
                        phase,
                        min(total_transfer_bytes, base + completed),
                        total_transfer_bytes,
                    )
                else:
                    phase_callback(phase, completed, total)

            if copy_source_members:
                digest: list[str] = []
                moved, message = verified_copy(
                    member["source_path"],
                    member["stage_path"],
                    phase_callback=member_phase if phase_callback else None,
                    digest_callback=digest.append,
                )
                if moved and digest:
                    member["fingerprint"] = digest[0]
            else:
                moved, message = safe_move(
                    member["source_path"],
                    member["stage_path"],
                    allowed_base_dirs,
                    phase_callback=member_phase if phase_callback else None,
                )
            if not moved:
                raise IOError(f"文件包暂存失败: {message}")
            member["state"] = "staged"
            staged.append(member)
            if journal_callback:
                journal_callback("STAGING", members)
            completed_before += member_sizes[index]

        publish_order = [
            *[member for member in members if member["kind"] == "subtitle"],
            members[0],
        ]
        for member in publish_order:
            moved, message = safe_move(
                member["stage_path"],
                member["dest_path"],
                allowed_base_dirs,
                phase_callback=phase_callback,
            )
            if not moved:
                raise IOError(f"文件包发布失败: {message}")
            member["state"] = "published"
            published.append(member)
            if journal_callback:
                journal_callback(
                    "COMMITTED" if member["kind"] == "video" else "PUBLISHING",
                    members,
                )

        return {
            "video": dest_video,
            "subtitles": [member["dest_path"] for member in members[1:]],
            "bundle_committed": True,
        }
    except Exception as error:
        rollback_errors = []
        if copy_source_members:
            for member in members:
                partial = member["stage_path"] + ".copying"
                if not os.path.lexists(partial):
                    continue
                if os.path.islink(partial) or not os.path.isfile(partial):
                    rollback_errors.append(
                        f"任务复制残留类型异常，已保留现场: {partial}"
                    )
                    continue
                removed, message = safe_delete(partial, allowed_base_dirs)
                if not removed:
                    rollback_errors.append(message)
        for member in reversed(published):
            if copy_source_members:
                if (
                    not os.path.isfile(member["dest_path"])
                    or hash_file(member["dest_path"]) != member["fingerprint"]
                ):
                    rollback_errors.append(
                        f"任务发布文件发生变化，已保留现场: {member['dest_path']}"
                    )
                    continue
                restored, message = safe_move(
                    member["dest_path"],
                    member["stage_path"],
                    allowed_base_dirs,
                )
                if not restored:
                    rollback_errors.append(message)
                    continue
                removed, message = safe_delete(member["stage_path"], allowed_base_dirs)
                if not removed:
                    rollback_errors.append(message)
            else:
                restored, message = safe_move(
                    member["dest_path"],
                    member["source_path"],
                    allowed_base_dirs,
                )
                if not restored:
                    rollback_errors.append(message)
        for member in reversed(staged):
            if member in published or not os.path.lexists(member["stage_path"]):
                continue
            if copy_source_members:
                if (
                    not os.path.isfile(member["stage_path"])
                    or hash_file(member["stage_path"]) != member["fingerprint"]
                ):
                    rollback_errors.append(
                        f"任务暂存文件发生变化，已保留现场: {member['stage_path']}"
                    )
                    continue
                removed, message = safe_delete(member["stage_path"], allowed_base_dirs)
                if not removed:
                    rollback_errors.append(message)
            else:
                restored, message = safe_move(
                    member["stage_path"],
                    member["source_path"],
                    allowed_base_dirs,
                )
                if not restored:
                    rollback_errors.append(message)
        if rollback_errors:
            if journal_callback:
                journal_callback("RECOVERY_REQUIRED", members)
            raise IOError(
                f"{error}；本任务文件包回退不完整，请保留现场并检查: "
                + "；".join(rollback_errors)
            ) from error
        for member in members:
            member["state"] = "source"
        if journal_callback:
            journal_callback("ROLLED_BACK", members)
        raise


def _move_subtitles(result: dict, subtitle_paths: list[str], import_dir: str,
                    final_video_filename: str,
                    allowed_base_dirs: Optional[list] = None,
                    phase_callback=None,
                    subtitle_template: str = "{video_filename}.{lang}.{ext}") -> dict:

    plan = plan_subtitle_filenames(
        subtitle_paths,
        final_video_filename,
        subtitle_template,
    )
    for member in plan:
        sub_path = member["source_path"]
        final_sub_filename = member["filename"]
        dest_sub = os.path.join(import_dir, final_sub_filename)
        if os.path.exists(dest_sub):
            raise PipelineReviewRequired(
                "目标片库已有同名字幕，已停止入库且不会自动改名覆盖",
                {
                    "is_duplicate": True,
                    "status": "awaiting_user",
                    "conflict_type": "target_bundle",
                    "existing_path": dest_sub,
                    "existing_file": os.path.basename(dest_sub),
                },
            )
        ok, msg = verified_copy(
            sub_path,
            dest_sub,
            phase_callback=phase_callback,
        )
        if not ok:
            raise IOError(f"字幕文件复制失败: {msg}")
        result['subtitles'].append(dest_sub)

    return result


def move_with_cross_device_fallback(src: str, dest: str) -> bool:
    ok, msg = safe_move(src, dest)
    return ok
