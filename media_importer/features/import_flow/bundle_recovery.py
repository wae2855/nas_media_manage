import os
import re
from dataclasses import dataclass
from datetime import datetime

from media_importer.features.configuration.storage_topology import (
    path_in_library,
    path_within,
)
from media_importer.features.import_flow.services.paths import (
    allowed_dirs_from_config,
    import_roots_from_config,
)
from media_importer.features.organization_state import (
    ORGANIZATION_ORGANIZED,
    TASK_KIND_REORGANIZE,
)
from media_importer.features.tasks import mark_failed, mark_imported
from media_importer.infrastructure.db import (
    get_subtitles_by_task,
    update_subtitle,
    update_task,
)
from media_importer.infrastructure.filesystem import hash_file, safe_delete, safe_move

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RECOVERABLE_STATES = {
    "PREPARED",
    "STAGING",
    "PUBLISHING",
    "COMMITTED",
    "RECOVERY_REQUIRED",
}


@dataclass(frozen=True)
class BundleRecoveryResult:
    state: str
    message: str


def recover_interrupted_bundle(task: dict, config: dict, conn) -> BundleRecoveryResult | None:
    """按持久化成员清单恢复中断文件包；只操作本任务且指纹吻合的路径。"""
    state = str(task.get("bundle_state") or "")
    manifest = task.get("bundle_manifest")
    # 正常完成的任务保留 COMMITTED 日志用于审计，不能在每次服务启动时
    # 再次执行状态迁移；RECOVERY_REQUIRED 也必须等待人工处理，避免循环改写现场。
    if (
        str(task.get("status") or "") == "SUCCESS"
        and int(task.get("import_success") or 0) == 1
    ) or (
        str(task.get("status") or "") == "FAILED"
        and state == "RECOVERY_REQUIRED"
    ):
        return None
    if state not in _RECOVERABLE_STATES or not isinstance(manifest, list) or not manifest:
        return None

    try:
        members = _validated_manifest(task, manifest, config)
    except ValueError as error:
        return _mark_recovery_required(task, conn, str(error))

    video = next(member for member in members if member["kind"] == "video")
    video_is_published = os.path.lexists(video["dest_path"])
    journal_says_committed = state == "COMMITTED" or int(task.get("bundle_committed") or 0) == 1

    if video_is_published or journal_says_committed:
        if all(_matches(member["dest_path"], member["fingerprint"]) for member in members):
            return _recover_committed(task, members, conn)
        return _mark_recovery_required(
            task,
            conn,
            "服务重启后发现影片提交标记存在，但文件包成员不完整或内容已变化；"
            "片库文件均已保留，请人工检查后处理",
            committed=True,
        )

    import_roots = import_roots_from_config(config)
    allowed_dirs = (
        import_roots
        if task.get("task_kind") == TASK_KIND_REORGANIZE
        else allowed_dirs_from_config(config)
    )
    for member in reversed(members):
        source_path = member["source_path"]
        fingerprint = member["fingerprint"]
        if member["transfer_mode"] == "copy":
            copy_error = _rollback_copied_member(member, import_roots)
            if copy_error:
                return _mark_recovery_required(task, conn, copy_error)
            continue
        candidates = [
            path
            for path in (member["stage_path"], member["dest_path"])
            if os.path.lexists(path)
        ]
        if os.path.lexists(source_path):
            if not _matches(source_path, fingerprint) or candidates:
                return _mark_recovery_required(
                    task,
                    conn,
                    f"文件包成员出现重复或内容变化，已停止自动回退: {os.path.basename(source_path)}",
                )
            continue
        if len(candidates) != 1 or not _matches(candidates[0], fingerprint):
            return _mark_recovery_required(
                task,
                conn,
                f"无法唯一确认文件包成员位置，已停止自动回退: {os.path.basename(source_path)}",
            )
        restored, message = safe_move(candidates[0], source_path, allowed_dirs)
        if not restored:
            return _mark_recovery_required(
                task,
                conn,
                f"文件包成员回退失败，现场已保留: {message}",
            )

    is_reorganization = task.get("task_kind") == TASK_KIND_REORGANIZE
    fields = mark_failed(
        task,
        (
            "服务在重新整理提交前中断；影片和字幕已完整退回原片库位置，请点击重试"
            if is_reorganization
            else "服务在入库完成前中断；来源文件保持不变，片库临时内容已清理，请重新整理"
        ),
        file_location="import" if is_reorganization else "source",
        video_path=video["source_path"],
    )
    fields.update({
        "bundle_state": "ROLLED_BACK",
        "bundle_manifest": members,
        "bundle_committed": 0,
        "current_step": 0,
        "percentage": 0,
    })
    update_task(conn, task["task_id"], **fields)
    return BundleRecoveryResult("ROLLED_BACK", fields["error_message"])


def _validated_manifest(task: dict, manifest: list, config: dict) -> list[dict]:
    task_id = str(task.get("task_id") or "")
    import_roots = import_roots_from_config(config)
    is_reorganization = task.get("task_kind") == TASK_KIND_REORGANIZE
    source_dir = str(config.get("source_dir") or "")
    if not task_id or not import_roots:
        raise ValueError("文件包恢复所需的任务编号或目标片库配置不完整")

    members = []
    video_count = 0
    seen_destinations = set()
    for raw in manifest:
        if not isinstance(raw, dict):
            raise ValueError("文件包恢复清单格式无效")
        kind = str(raw.get("kind") or "")
        source_path = os.path.realpath(str(raw.get("source_path") or ""))
        stage_path = os.path.realpath(str(raw.get("stage_path") or ""))
        dest_path = os.path.realpath(str(raw.get("dest_path") or ""))
        fingerprint = str(raw.get("fingerprint") or "").lower()
        transfer_mode = str(raw.get("transfer_mode") or "move").lower()
        if (
            kind not in {"video", "subtitle"}
            or transfer_mode not in {"copy", "move"}
            or (fingerprint and not _SHA256_RE.fullmatch(fingerprint))
            or (not fingerprint and transfer_mode != "copy")
        ):
            raise ValueError("文件包恢复清单的成员类型或指纹无效")
        if kind == "video":
            video_count += 1
        if is_reorganization:
            if not any(
                path_within(source_path, root, allow_root=False)
                for root in import_roots
            ):
                raise ValueError("重新整理恢复清单的来源超出已配置片库")
        elif transfer_mode == "copy":
            if (
                not source_dir
                or not path_within(source_path, source_dir, allow_root=False)
                or path_in_library(config, source_path)
            ):
                raise ValueError("文件包恢复清单的原始来源超出允许范围")
        else:
            raise ValueError("普通入库恢复清单只能从原始来源复制")
        if is_reorganization and transfer_mode != "move":
            raise ValueError("重新整理恢复清单只能在片库之间安全移动")
        if not any(path_within(dest_path, root, allow_root=False) for root in import_roots):
            raise ValueError("文件包恢复清单的目标超出已配置片库")
        expected_prefix = f"{dest_path}.{task_id}."
        if not stage_path.startswith(expected_prefix) or not stage_path.endswith(".bundle.tmp"):
            raise ValueError("文件包恢复清单的暂存路径不属于本任务")
        if dest_path in seen_destinations:
            raise ValueError("文件包恢复清单包含重复目标")
        seen_destinations.add(dest_path)
        members.append({
            "kind": kind,
            "source_path": source_path,
            "stage_path": stage_path,
            "dest_path": dest_path,
            "fingerprint": fingerprint,
            "transfer_mode": transfer_mode,
            "state": str(raw.get("state") or ""),
        })
    if video_count != 1:
        raise ValueError("文件包恢复清单必须且只能包含一个影片文件")
    return members


def _rollback_copied_member(member: dict, import_roots: list[str]) -> str:
    """Remove only task-owned target copies; the original source must survive."""
    fingerprint = member["fingerprint"]
    stage_path = member["stage_path"]
    partial = member["stage_path"] + ".copying"
    # stage/partial paths were already proven to contain the task id and the
    # internal suffix under a configured target root, so they can be removed
    # without reading an offline source disk.
    for path, label in ((partial, "未完成复制"), (stage_path, "任务暂存")):
        if not os.path.lexists(path):
            continue
        if os.path.islink(path) or not os.path.isfile(path):
            return f"{label}的类型异常，已保留现场: {path}"
        removed, message = safe_delete(path, import_roots)
        if not removed:
            return f"{label}无法清理，已保留现场: {message}"

    # A formal destination can only exist before the video commit when a
    # subtitle was published first. Never remove it without the persisted
    # digest, because its ordinary filename is part of the visible library.
    dest_path = member["dest_path"]
    if os.path.lexists(dest_path):
        if not fingerprint or not _matches(dest_path, fingerprint):
            return f"正式片库成员无法确认属于本任务，已保留现场: {dest_path}"
        restored, message = safe_move(dest_path, stage_path, import_roots)
        if not restored:
            return f"提交前片库成员无法退回任务暂存区，已保留现场: {message}"
        removed, message = safe_delete(stage_path, import_roots)
        if not removed:
            return f"提交前片库成员无法回退，已保留现场: {message}"
    return ""


def _matches(path: str, fingerprint: str) -> bool:
    return (
        bool(path)
        and not os.path.islink(path)
        and os.path.isfile(path)
        and hash_file(path) == fingerprint
    )


def _recover_committed(task: dict, members: list[dict], conn) -> BundleRecoveryResult:
    video = next(member for member in members if member["kind"] == "video")
    subtitles = {
        os.path.basename(member["dest_path"]): member["dest_path"]
        for member in members
        if member["kind"] == "subtitle"
    }
    subtitles_by_source = {
        os.path.realpath(str(member.get("source_path") or "")): member["dest_path"]
        for member in members
        if member["kind"] == "subtitle" and member.get("source_path")
    }
    now = datetime.now().isoformat()
    for row in get_subtitles_by_task(conn, task["task_id"]):
        import_path = subtitles.get(str(row.get("planned_filename") or ""), "")
        if not import_path:
            continue
        update_subtitle(
            conn,
            row["id"],
            status="SUCCESS",
            import_path=import_path,
            confirm_status="CONFIRMED",
            completed_at=now,
        )
    fields = mark_imported(task, import_video_path=video["dest_path"])
    fields.update({
        "file_location": "import",
        "video_path": video["dest_path"],
        "import_video_path": video["dest_path"],
        "import_success": 1,
        "bundle_state": "COMMITTED_RECOVERED",
        "bundle_manifest": members,
        "bundle_committed": 1,
        # 文件包已经提交后不再恢复后续业务步骤。来源保持原样，避免服务
        # 重启后在用户无感知的情况下补做回收或永久删除。
        "source_cleanup_status": "SKIPPED",
        "source_disposition": "kept",
        "source_disposition_message": "服务在完整入库后中断，为安全起见已保留来源内容",
    })
    if task.get("task_kind") == TASK_KIND_REORGANIZE:
        intent = dict(task.get("reorganization_intent") or {})
        intent.update({
            "completed_target_path": video["dest_path"],
            "completed_at": now,
            "recovered_after_restart": True,
        })
        fields.update({
            "used_fallback": 0,
            "organization_status": ORGANIZATION_ORGANIZED,
            "source_cleanup_status": "SKIPPED",
            # 片库重整的“来源”本来就在片库内，不应显示成普通入库任务的
            # 来源保留结果；重整任务只表达已完成归位。
            "source_disposition": "",
            "source_disposition_message": "",
            "reorganization_intent": intent,
        })
        parent_id = str(task.get("parent_task_id") or "")
        if parent_id:
            parent_subtitles = get_subtitles_by_task(conn, parent_id)
            for parent_row in parent_subtitles:
                previous_path = str(
                    parent_row.get("import_path")
                    or parent_row.get("target_path")
                    or parent_row.get("source_path")
                    or ""
                )
                import_path = subtitles_by_source.get(os.path.realpath(previous_path), "")
                if not import_path:
                    continue
                update_subtitle(
                    conn,
                    parent_row["id"],
                    status="SUCCESS",
                    import_path=import_path,
                    target_path=import_path,
                    planned_filename=os.path.basename(import_path),
                    confirm_status="CONFIRMED",
                    completed_at=now,
                )
            update_task(
                conn,
                parent_id,
                organization_status=ORGANIZATION_ORGANIZED,
                reorganized_by_task_id=task["task_id"],
                video_path=video["dest_path"],
                import_video_path=video["dest_path"],
                import_path=os.path.dirname(video["dest_path"]),
                final_filename=os.path.basename(video["dest_path"]),
            )
    update_task(conn, task["task_id"], **fields)
    return BundleRecoveryResult(
        "COMMITTED_RECOVERED",
        "已确认影片和全部字幕完整入库；服务重启没有重复写入片库，来源内容已保留",
    )


def _mark_recovery_required(
    task: dict,
    conn,
    message: str,
    *,
    committed: bool = False,
) -> BundleRecoveryResult:
    is_reorganization = task.get("task_kind") == TASK_KIND_REORGANIZE
    fields = mark_failed(
        task,
        message,
        file_location="import" if is_reorganization else "source",
        video_path=task.get("source_path", ""),
    )
    fields.update({
        "bundle_state": "RECOVERY_REQUIRED",
        "bundle_committed": 1 if committed else int(task.get("bundle_committed") or 0),
    })
    update_task(conn, task["task_id"], **fields)
    return BundleRecoveryResult("RECOVERY_REQUIRED", message)


__all__ = ["BundleRecoveryResult", "recover_interrupted_bundle"]
