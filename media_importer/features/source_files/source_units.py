"""源单元识别与整组回收门禁。"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from dataclasses import dataclass
from fnmatch import fnmatch

from media_importer.features.configuration.storage_readiness import inspect_storage_readiness
from media_importer.features.configuration.storage_topology import (
    canonical_path,
    configured_library_roots,
    path_in_library,
    path_within,
)
from media_importer.features.operation_locks import serialize_source_disposition
from media_importer.features.recycle import move_dir_to_recycle, move_to_recycle
from media_importer.features.source_files.coverage import coverage_blocker, retain_source
from media_importer.features.source_files.media_candidates import (
    ACCEPT,
    MediaCandidatePolicy,
)
from media_importer.features.source_files.permanent_delete import (
    permanently_delete_source_members,
    resume_permanent_source_delete,
)
from media_importer.infrastructure.db import (
    get_source_unit,
    list_pending_source_unit_ids,
    list_tasks_for_source_unit,
    update_source_unit,
    update_task,
    upsert_source_unit,
)


@dataclass(frozen=True)
class SourceUnit:
    unit_id: str
    source_root: str
    unit_path: str
    kind: str
    snapshot: list[dict]


@dataclass(frozen=True)
class SourceUnitRecycleResult:
    state: str
    message: str


def _is_within(root: str, path: str) -> bool:
    try:
        return os.path.commonpath([root, path]) == root
    except ValueError:
        return False


def _snapshot(unit_path: str, kind: str) -> list[dict]:
    paths = []
    if kind == "loose_root":
        paths = [
            os.path.join(unit_path, name) for name in sorted(os.listdir(unit_path))
            if os.path.isfile(os.path.join(unit_path, name))
        ]
    else:
        for current, dirs, files in os.walk(unit_path):
            dirs.sort()
            for name in list(dirs):
                path = os.path.join(current, name)
                entry_stat = os.lstat(path)
                if stat.S_ISLNK(entry_stat.st_mode):
                    raise ValueError(f"源单元包含符号链接，拒绝自动处理: {path}")
                if not stat.S_ISDIR(entry_stat.st_mode):
                    raise ValueError(f"源单元包含特殊目录项，拒绝自动处理: {path}")
                result_path = os.path.relpath(path, unit_path)
                paths.append((path, result_path, "directory"))
            for name in sorted(files):
                path = os.path.join(current, name)
                paths.append((path, os.path.relpath(path, unit_path), "file"))
    if kind == "loose_root":
        paths = [(path, os.path.relpath(path, unit_path), "file") for path in paths]
    result = []
    for path, relative_path, entry_type in paths:
        if os.path.islink(path):
            raise ValueError(f"源单元包含符号链接，拒绝自动处理: {path}")
        entry_stat = os.lstat(path)
        if entry_type == "file" and not stat.S_ISREG(entry_stat.st_mode):
            raise ValueError(f"源单元包含特殊文件，拒绝自动处理: {path}")
        item = {
            "relative_path": relative_path,
            "size": entry_stat.st_size if entry_type == "file" else 0,
            "mtime_ns": entry_stat.st_mtime_ns,
        }
        if entry_type == "directory":
            item["type"] = "directory"
        result.append(item)
    result.sort(key=lambda item: (item["relative_path"], item.get("type", "file")))
    return result


def _snapshot_with_candidate_evidence(
    snapshot: list[dict],
    unit_path: str,
    config: dict | None,
) -> list[dict]:
    if config is None:
        return snapshot
    policy = MediaCandidatePolicy(config)
    video_paths = [
        os.path.join(unit_path, item["relative_path"])
        for item in snapshot
        if item.get("type") != "directory"
        and os.path.splitext(item["relative_path"])[1].lower() in policy.video_extensions
    ]
    decisions = policy.classify_tree(unit_path, video_paths)
    decorated = []
    for item in snapshot:
        current = dict(item)
        path = os.path.realpath(os.path.join(unit_path, item["relative_path"]))
        decision = decisions.get(path)
        if decision:
            current["media_candidate"] = {
                "disposition": decision.disposition,
                "reason": decision.reason,
                "evidence": decision.evidence,
            }
        decorated.append(current)
    return decorated


def _physical_snapshot(snapshot: list[dict]) -> list[dict]:
    """去除冻结的业务判定，只比较磁盘事实。"""
    return [
        {key: value for key, value in item.items() if key != "media_candidate"}
        for item in snapshot
    ]


def resolve_source_unit(
    source_root: str,
    source_path: str,
    *,
    config: dict | None = None,
) -> SourceUnit:
    root = os.path.realpath(os.path.abspath(source_root))
    path = os.path.realpath(os.path.abspath(source_path))
    if not _is_within(root, path) or path == root:
        raise ValueError("源文件不在配置的源目录内")
    relative = os.path.relpath(path, root)
    first = relative.split(os.sep, 1)[0]
    first_path = os.path.join(root, first)
    if os.sep in relative and os.path.isdir(first_path):
        kind = "folder"
        unit_path = first_path
        marker = first
    else:
        kind = "loose_root"
        unit_path = root
        marker = "."
    physical_snapshot = _snapshot(unit_path, kind)
    snapshot_key = json.dumps(
        physical_snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    digest = hashlib.sha256(
        f"{root}\0{kind}\0{marker}\0{snapshot_key}".encode()
    ).hexdigest()[:24]
    snapshot = _snapshot_with_candidate_evidence(
        physical_snapshot, unit_path, config
    )
    return SourceUnit(digest, root, unit_path, kind, snapshot)


def register_source_unit(
    conn,
    source_root: str,
    source_path: str,
    *,
    config: dict | None = None,
) -> SourceUnit:
    unit = resolve_source_unit(source_root, source_path, config=config)
    existing = get_source_unit(conn, unit.unit_id)
    upsert_source_unit(
        conn,
        unit_id=unit.unit_id,
        source_root=unit.source_root,
        unit_path=unit.unit_path,
        kind=unit.kind,
        snapshot=unit.snapshot,
    )
    # 只为物理快照完全一致的旧记录补充一次冻结判定。绝不借此刷新发生变化
    # 的来源单元，否则会绕过清理前的快照一致性门禁。
    if (
        existing
        and config is not None
        and _physical_snapshot(existing.get("snapshot", []))
        == _physical_snapshot(unit.snapshot)
        and not any("media_candidate" in item for item in existing.get("snapshot", []))
    ):
        update_source_unit(
            conn,
            unit.unit_id,
            snapshot_json=json.dumps(unit.snapshot, ensure_ascii=False, sort_keys=True),
        )
    return unit


class SourceUnitCoordinator:
    def __init__(self, conn, config: dict):
        self.conn = conn
        self.config = config or {}

    @serialize_source_disposition(lambda _self, unit_id, **_kwargs: unit_id)
    def try_recycle(
        self, unit_id: str, *, completing_task_id: str = "", phase_callback=None,
    ) -> SourceUnitRecycleResult:
        # Workers and background retries must not dispose the same snapshot twice.
        unit = get_source_unit(self.conn, unit_id)
        if unit and unit["state"] in {"RECYCLED", "DELETED"}:
            result = SourceUnitRecycleResult(unit["state"], "该来源单元已处理完成")
        else:
            try:
                result = self._try_recycle(
                    unit_id, completing_task_id=completing_task_id, phase_callback=phase_callback,
                )
            except (OSError, ValueError) as error:
                result = SourceUnitRecycleResult("BLOCKED", f"来源复核异常，已停止处理：{error}")
        disposition = {"DELETED": "deleted", "RECYCLED": "recycled", "SKIPPED": "kept",
                       "WAITING": "pending", "BLOCKED": "failed"}.get(result.state, "pending")
        if unit and result.state != "SKIPPED":
            update_source_unit(self.conn, unit_id, state=result.state,
                               cleanup_status="DONE" if result.state in {"RECYCLED", "DELETED"} else result.state,
                               last_error=result.message if result.state in {"WAITING", "BLOCKED"} else "")
        for task in list_tasks_for_source_unit(self.conn, unit_id):
            if retain_source(task):
                continue
            update_task(self.conn, task["task_id"], source_cleanup_status=result.state,
                        source_disposition=disposition, source_disposition_message=result.message)
        return result

    def _try_recycle(
        self,
        unit_id: str,
        *,
        completing_task_id: str = "",
        phase_callback=None,
    ) -> SourceUnitRecycleResult:
        policy = self.config.get("source_policy", {}) or {}
        if policy.get("mode") != "recycle_source_unit":
            return SourceUnitRecycleResult("SKIPPED", "当前模式不回收源单元")
        from media_importer.features.configuration.storage_topology import (
            topology_error_messages,
        )

        conflicts = topology_error_messages(self.config)
        if conflicts:
            return SourceUnitRecycleResult(
                "BLOCKED",
                "目录边界不安全，已阻止来源单元回收：" + conflicts[0],
            )
        unit = get_source_unit(self.conn, unit_id)
        if not unit:
            return SourceUnitRecycleResult("BLOCKED", "源单元记录不存在")
        current_source = str(self.config.get("source_dir", "") or "")
        if (
            not current_source
            or canonical_path(unit["source_root"]) != canonical_path(current_source)
            or not path_within(unit["unit_path"], current_source)
            or path_in_library(self.config, unit["source_root"])
            or path_in_library(self.config, unit["unit_path"])
        ):
            return SourceUnitRecycleResult(
                "BLOCKED",
                "来源单元已不属于当前来源目录，或现已属于目标片库；已保留全部文件",
            )
        disposal_mode = policy.get("disposal_mode", "local_recycle")
        ledger_dir = os.path.join(
            str(self.config.get("_data_dir") or unit["source_root"]),
            "source_delete_ledgers",
        )
        active_ledger = os.path.join(ledger_dir, f"source-delete-{unit_id}.jsonl")
        if disposal_mode == "permanent_delete" and os.path.isfile(active_ledger):
            resumed = resume_permanent_source_delete(
                active_ledger,
                source_root=unit["source_root"],
                protected_roots=configured_library_roots(self.config),
            )
            if resumed.ok:
                update_source_unit(self.conn, unit_id, state="DELETED", cleanup_status="DONE")
                return SourceUnitRecycleResult("DELETED", resumed.message)
            update_source_unit(
                self.conn, unit_id, state="BLOCKED", cleanup_status="FAILED",
                last_error=resumed.message,
            )
            return SourceUnitRecycleResult("BLOCKED", resumed.message)
        tasks = list_tasks_for_source_unit(self.conn, unit_id)
        patterns = policy.get("unit_incomplete_patterns") or [
            "*.part", "*.partial", "*.aria2", "*.!qB", "*.crdownload"
        ]
        incomplete = [
            item["relative_path"] for item in unit["snapshot"]
            if any(fnmatch(item["relative_path"].lower(), str(pattern).lower()) for pattern in patterns)
        ]
        if incomplete:
            update_source_unit(self.conn, unit_id, state="WAITING", cleanup_status="WAITING")
            return SourceUnitRecycleResult("WAITING", "源单元仍包含未完成下载标记")
        settle_seconds = max(0, int(policy.get("unit_settle_seconds", 120)))
        newest_mtime = max(
            (int(item.get("mtime_ns", 0)) for item in unit["snapshot"]), default=0
        )
        if newest_mtime and time.time_ns() - newest_mtime < settle_seconds * 1_000_000_000:
            update_source_unit(self.conn, unit_id, state="WAITING", cleanup_status="WAITING")
            return SourceUnitRecycleResult("WAITING", f"源单元尚未稳定满 {settle_seconds} 秒")
        candidate_video_extensions = MediaCandidatePolicy(
            self.config
        ).video_extensions
        missing_candidate_evidence = any(
            item.get("type") != "directory"
            and os.path.splitext(item["relative_path"])[1].lower()
            in candidate_video_extensions
            and "media_candidate" not in item
            for item in unit.get("snapshot", [])
        )
        if self.config and missing_candidate_evidence:
            if not os.path.isdir(unit["unit_path"]):
                return SourceUnitRecycleResult("BLOCKED", "源单元目录不存在或挂载已失效")
            current_physical = _snapshot(unit["unit_path"], unit["kind"])
            if current_physical != _physical_snapshot(unit["snapshot"]):
                message = "源单元内容发生变化，无法补齐旧记录的媒体判定"
                update_source_unit(
                    self.conn,
                    unit_id,
                    state="BLOCKED",
                    cleanup_status="BLOCKED",
                    last_error=message,
                )
                return SourceUnitRecycleResult("BLOCKED", message)
            repaired_snapshot = _snapshot_with_candidate_evidence(
                current_physical,
                unit["unit_path"],
                self.config,
            )
            update_source_unit(
                self.conn,
                unit_id,
                snapshot_json=json.dumps(
                    repaired_snapshot,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
            unit["snapshot"] = repaired_snapshot
        configured_exts = self.config.get("video_extensions") or [
            ".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".ts", ".m2ts", ".webm"
        ]
        video_exts = {
            str(ext).lower() if str(ext).startswith(".") else "." + str(ext).lower()
            for ext in configured_exts
        }
        expected_media = {
            os.path.realpath(os.path.join(unit["unit_path"], item["relative_path"]))
            for item in unit["snapshot"]
            if item.get("type") != "directory"
            and os.path.splitext(item["relative_path"])[1].lower() in video_exts
            and (item.get("media_candidate") or {}).get("disposition", ACCEPT) == ACCEPT
        }
        covered_media = {os.path.realpath(task.get("source_path", "")) for task in tasks}
        if not expected_media.issubset(covered_media):
            update_source_unit(self.conn, unit_id, state="WAITING", cleanup_status="WAITING")
            return SourceUnitRecycleResult("WAITING", "源单元仍有媒体文件尚未创建任务")
        blocker, duplicate_count = coverage_blocker(
            self.conn, self.config, unit, tasks, completing_task_id, phase_callback,
        )
        if blocker:
            update_source_unit(self.conn, unit_id, state="WAITING", cleanup_status="WAITING")
            return SourceUnitRecycleResult("WAITING", blocker)
        if not os.path.isdir(unit["unit_path"]):
            return SourceUnitRecycleResult("BLOCKED", "源单元目录不存在或挂载已失效")
        current = _snapshot(unit["unit_path"], unit["kind"])
        if current != _physical_snapshot(unit["snapshot"]):
            update_source_unit(
                self.conn, unit_id, state="BLOCKED", cleanup_status="BLOCKED",
                last_error="源单元内容发生变化",
            )
            return SourceUnitRecycleResult("BLOCKED", "源单元内容发生变化，可能仍在下载")
        unit_size = sum(
            int(item.get("size", 0))
            for item in unit["snapshot"]
            if item.get("type") != "directory"
        )
        readiness_roles = (
            {"source"}
            if disposal_mode == "permanent_delete"
            else {"source", "recycle"}
        )
        readiness = inspect_storage_readiness(
            self.config,
            write_bytes=unit_size,
            roles=readiness_roles,
            include_topology=False,
        )
        blocked_roles = set(readiness.get("blocking", []))
        required_roles = {"source"}
        if disposal_mode != "permanent_delete":
            required_roles.add("recycle")
        if blocked_roles.intersection(required_roles):
            message = (
                "源目录当前不可用"
                if disposal_mode == "permanent_delete"
                else "源目录或回收目录当前不可用"
            )
            return SourceUnitRecycleResult("BLOCKED", message)

        recycle_dir = policy.get("recycle_dir", "")
        if list_tasks_for_source_unit(self.conn, unit_id) != tasks:
            return SourceUnitRecycleResult("WAITING", "来源复核期间任务状态发生变化，已保留来源等待下次复核")
        final_snapshot = _snapshot(unit["unit_path"], unit["kind"])
        if final_snapshot != _physical_snapshot(unit["snapshot"]):
            return SourceUnitRecycleResult(
                "BLOCKED", "来源复核完成后内容再次发生变化，已保留来源等待稳定",
            )
        update_source_unit(
            self.conn,
            unit_id,
            state="DELETING" if disposal_mode == "permanent_delete" else "RECYCLING",
            cleanup_status="RUNNING",
        )
        if disposal_mode == "permanent_delete":
            members = (
                [unit["unit_path"]]
                if unit["kind"] == "folder"
                else [
                    os.path.join(unit["unit_path"], item["relative_path"])
                    for item in unit["snapshot"]
                    if item.get("type") != "directory"
                ]
            )
            deleted = permanently_delete_source_members(
                members,
                source_root=unit["source_root"],
                operation_id=unit_id,
                ledger_dir=ledger_dir,
                protected_roots=configured_library_roots(self.config),
            )
            ok, message = deleted.ok, deleted.message
        elif unit["kind"] == "folder":
            ok, _target, message = move_dir_to_recycle(
                unit["unit_path"], recycle_dir, reason="source_unit_cleanup",
                source_dir=unit["source_root"],
                import_roots=configured_library_roots(self.config),
                extra_meta={"source_unit_id": unit_id},
                phase_callback=phase_callback,
            )
        else:
            ok, message = self._move_loose_files(
                unit,
                recycle_dir,
                phase_callback=phase_callback,
            )
        if not ok:
            update_source_unit(
                self.conn, unit_id, state="BLOCKED", cleanup_status="FAILED", last_error=message,
            )
            return SourceUnitRecycleResult("BLOCKED", message)
        completed_state = "DELETED" if disposal_mode == "permanent_delete" else "RECYCLED"
        update_source_unit(self.conn, unit_id, state=completed_state, cleanup_status="DONE")
        if duplicate_count:
            message += f"；已核验同一来源文件的完整入库证明，{duplicate_count} 条历史重复记录保留供审计"
        return SourceUnitRecycleResult(completed_state, message)

    def retry_pending(self) -> list[SourceUnitRecycleResult]:
        results = []
        for unit_id in list_pending_source_unit_ids(self.conn):
            result = self.try_recycle(unit_id)
            results.append(result)
        return results

    def _move_loose_files(
        self,
        unit: dict,
        recycle_dir: str,
        *,
        phase_callback=None,
    ) -> tuple[bool, str]:
        # 单文件移动均有回收元数据；失败时保留未移动成员并允许再次协调。
        remaining = list(unit["snapshot"])
        total_size = sum(int(item.get("size", 0)) for item in remaining)
        completed_before = 0

        def phase_for_file(base_bytes: int):
            def on_file_phase(phase, completed, total):
                if not phase_callback:
                    return
                if phase == "transfer":
                    phase_callback(
                        phase,
                        min(total_size, base_bytes + completed),
                        total_size,
                    )
                else:
                    phase_callback(phase, completed, total)

            return on_file_phase

        for item in list(remaining):
            path = os.path.join(unit["unit_path"], item["relative_path"])

            ok, _target, message = move_to_recycle(
                path, recycle_dir, reason="source_unit_cleanup",
                source_dir=unit["source_root"],
                import_roots=configured_library_roots(self.config),
                extra_meta={"source_unit_id": unit["unit_id"]},
                phase_callback=phase_for_file(completed_before),
            )
            if not ok:
                return False, message
            completed_before += int(item.get("size", 0))
            remaining.remove(item)
            update_source_unit(
                self.conn,
                unit["unit_id"],
                snapshot_json=json.dumps(remaining, ensure_ascii=False, sort_keys=True),
            )
        return True, "已将源目录直属文件统一移入回收站"
