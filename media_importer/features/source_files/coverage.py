"""Conservative proof for terminal duplicate records, never status rewriting."""

from __future__ import annotations

import os
import re

from media_importer.features.configuration.storage_topology import path_within
from media_importer.infrastructure.db import get_subtitles_by_task, get_task
from media_importer.infrastructure.filesystem import hash_file


def retain_source(task: dict) -> bool:
    outcome = str(task.get("outcome_code") or "")
    reason = str(task.get("skip_reason") or "")
    return (
        task.get("bundle_state") == "COMMITTED_RECOVERED"
        or outcome.startswith("USER_")
        or outcome == "SOURCE_DISPOSITION_UPDATED"
        or bool(task.get("requested_source_disposition"))
        or task.get("status") == "CANCELLED"
        or "用户" in reason
        or "保留片库" in reason
    )


def task_ready(task: dict, completing_task_id: str = "") -> bool:
    if retain_source(task) or task.get("import_success") != 1:
        return False
    return (task.get("status"), task.get("stage")) == ("SUCCESS", "DONE") or (
        task.get("task_id") == completing_task_id
        and (task.get("status"), task.get("stage")) == ("PENDING", "RUNNING")
    )


def coverage_blocker(conn, config, unit, tasks, completing_task_id="", phase_callback=None):
    """Return a user-facing blocker and the number of proven duplicate rows."""
    ready = [task for task in tasks if task_ready(task, completing_task_id)]
    blocked = [task for task in tasks if not task_ready(task, completing_task_id)]
    if not tasks:
        return "源单元仍有任务未全部成功", 0
    # Do not read large files while any genuinely active/retained task exists.
    for task in blocked:
        name = os.path.basename(str(task.get("source_path") or ""))
        if retain_source(task):
            return f"源单元保留来源：{name}（人工处置或重启保护）", 0
        if task.get("status") not in {"FAILED", "SKIPPED"} or task.get("stage") != "DONE":
            labels = {"QUEUED": "排队中", "AWAIT_REVIEW": "待确认", "RUNNING": "处理中"}
            return f"源单元仍有任务未全部成功：{name}（{labels.get(task.get('stage'), '未完成')}）", 0
        if not any(candidate["source_path"] == task["source_path"] for candidate in ready):
            return f"源单元仍有任务未全部成功：{name}（没有同一来源快照的成功记录）", 0
    proofs = {}
    for task in blocked:
        matching = [candidate for candidate in ready if candidate["source_path"] == task["source_path"]]
        covered = False
        for candidate in matching:
            tid = candidate["task_id"]
            if tid not in proofs:
                proofs[tid] = _verified_bundle(conn, config, unit, tid, phase_callback)
            members = proofs[tid]
            required = {os.path.realpath(task["source_path"])}
            required.update(os.path.realpath(row["source_path"])
                            for row in get_subtitles_by_task(conn, task["task_id"]))
            if members and required.issubset(members):
                covered = True
                break
        if not covered:
            return ("源单元仍有任务未全部成功："
                    f"{os.path.basename(task['source_path'])}（历史重复记录缺少完整入库证明，或影片/字幕已变化）"), 0
    return "", len(blocked)


def _verified_bundle(conn, config, unit, task_id, phase_callback):
    task = get_task(conn, task_id) or {}
    manifest = task.get("bundle_manifest")
    if task.get("bundle_committed") != 1 or task.get("bundle_state") != "COMMITTED":
        return set()
    if not isinstance(manifest, list) or not manifest:
        return set()
    roots = [str(root.get("path") or "") for root in config.get("library_roots", [])
             if isinstance(root, dict) and root.get("enabled", True)]
    snapshot_paths = {os.path.realpath(os.path.join(unit["unit_path"], item["relative_path"]))
                      for item in unit["snapshot"] if item.get("type") != "directory"}
    seen = set()
    targets = set()
    videos = []
    try:
        for member in manifest:
            if not isinstance(member, dict):
                return set()
            source, dest = str(member.get("source_path") or ""), str(member.get("dest_path") or "")
            digest = str(member.get("fingerprint") or "")
            if (not os.path.isabs(source) or not os.path.isabs(dest)
                    or os.path.islink(source) or os.path.islink(dest)
                    or source != os.path.realpath(source) or dest != os.path.realpath(dest)
                    or source not in snapshot_paths or source in seen or dest in targets
                    or not any(path_within(dest, root, allow_root=False) for root in roots if root)
                    or member.get("kind") not in {"video", "subtitle"}
                    or member.get("state") != "published" or member.get("transfer_mode") != "copy"
                    or not re.fullmatch(r"[0-9a-f]{64}", digest)):
                return set()
            if member["kind"] == "video":
                videos.append(source)
            for path, phase in ((source, "verify_source"), (dest, "verify_target")):
                before = os.stat(path, follow_symlinks=False)
                if hash_file(path, phase=phase, phase_callback=phase_callback) != digest:
                    return set()
                after = os.stat(path, follow_symlinks=False)
                if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                    return set()
            seen.add(source)
            targets.add(dest)
    except (OSError, ValueError):
        return set()
    required = {os.path.realpath(row["source_path"]) for row in get_subtitles_by_task(conn, task_id)}
    return seen if videos == [task["source_path"]] and required.issubset(seen) else set()
