"""源单元识别与整组回收门禁。"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from fnmatch import fnmatch

from media_importer.features.configuration.storage_readiness import inspect_storage_readiness
from media_importer.features.recycle import move_dir_to_recycle, move_to_recycle
from media_importer.infrastructure.db import (
    get_source_unit,
    list_pending_source_unit_ids,
    list_tasks_for_source_unit,
    update_source_unit,
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
            for name in sorted(files):
                paths.append(os.path.join(current, name))
    result = []
    for path in paths:
        if os.path.islink(path):
            raise ValueError(f"源单元包含符号链接，拒绝自动回收: {path}")
        stat = os.stat(path)
        result.append({
            "relative_path": os.path.relpath(path, unit_path),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        })
    return result


def resolve_source_unit(source_root: str, source_path: str) -> SourceUnit:
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
    snapshot = _snapshot(unit_path, kind)
    snapshot_key = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    digest = hashlib.sha256(
        f"{root}\0{kind}\0{marker}\0{snapshot_key}".encode()
    ).hexdigest()[:24]
    return SourceUnit(digest, root, unit_path, kind, snapshot)


def register_source_unit(conn, source_root: str, source_path: str) -> SourceUnit:
    unit = resolve_source_unit(source_root, source_path)
    upsert_source_unit(
        conn,
        unit_id=unit.unit_id,
        source_root=unit.source_root,
        unit_path=unit.unit_path,
        kind=unit.kind,
        snapshot=unit.snapshot,
    )
    return unit


class SourceUnitCoordinator:
    def __init__(self, conn, config: dict):
        self.conn = conn
        self.config = config or {}

    def try_recycle(self, unit_id: str) -> SourceUnitRecycleResult:
        policy = self.config.get("source_policy", {}) or {}
        if policy.get("mode") != "recycle_source_unit":
            return SourceUnitRecycleResult("SKIPPED", "当前模式不回收源单元")
        unit = get_source_unit(self.conn, unit_id)
        if not unit:
            return SourceUnitRecycleResult("BLOCKED", "源单元记录不存在")
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
            if os.path.splitext(item["relative_path"])[1].lower() in video_exts
        }
        covered_media = {os.path.realpath(task.get("source_path", "")) for task in tasks}
        if not expected_media.issubset(covered_media):
            update_source_unit(self.conn, unit_id, state="WAITING", cleanup_status="WAITING")
            return SourceUnitRecycleResult("WAITING", "源单元仍有媒体文件尚未创建任务")
        if not tasks or not all(
            task.get("status") == "SUCCESS"
            and task.get("stage") == "DONE"
            and task.get("import_success") == 1
            for task in tasks
        ):
            update_source_unit(self.conn, unit_id, state="WAITING", cleanup_status="WAITING")
            return SourceUnitRecycleResult("WAITING", "源单元仍有任务未全部成功")
        if not os.path.isdir(unit["unit_path"]):
            return SourceUnitRecycleResult("BLOCKED", "源单元目录不存在或挂载已失效")
        current = _snapshot(unit["unit_path"], unit["kind"])
        if current != unit["snapshot"]:
            update_source_unit(
                self.conn, unit_id, state="BLOCKED", cleanup_status="BLOCKED",
                last_error="源单元内容发生变化",
            )
            return SourceUnitRecycleResult("BLOCKED", "源单元内容发生变化，可能仍在下载")
        unit_size = sum(int(item.get("size", 0)) for item in unit["snapshot"])
        readiness = inspect_storage_readiness(self.config, write_bytes=unit_size)
        blocked_roles = set(readiness.get("blocking", []))
        if blocked_roles.intersection({"source", "recycle"}):
            return SourceUnitRecycleResult("BLOCKED", "源目录或回收目录当前不可用")

        recycle_dir = policy.get("recycle_dir", "")
        update_source_unit(self.conn, unit_id, state="RECYCLING", cleanup_status="RUNNING")
        if unit["kind"] == "folder":
            ok, _target, message = move_dir_to_recycle(
                unit["unit_path"], recycle_dir, reason="source_unit_cleanup",
                source_dir=unit["source_root"], extra_meta={"source_unit_id": unit_id},
            )
        else:
            ok, message = self._move_loose_files(unit, recycle_dir)
        if not ok:
            update_source_unit(
                self.conn, unit_id, state="BLOCKED", cleanup_status="FAILED", last_error=message,
            )
            return SourceUnitRecycleResult("BLOCKED", message)
        update_source_unit(self.conn, unit_id, state="RECYCLED", cleanup_status="DONE")
        return SourceUnitRecycleResult("RECYCLED", message)

    def retry_pending(self) -> list[SourceUnitRecycleResult]:
        return [
            self.try_recycle(unit_id)
            for unit_id in list_pending_source_unit_ids(self.conn)
        ]

    def _move_loose_files(self, unit: dict, recycle_dir: str) -> tuple[bool, str]:
        # 单文件移动均有回收元数据；失败时保留未移动成员并允许再次协调。
        remaining = list(unit["snapshot"])
        for item in list(remaining):
            path = os.path.join(unit["unit_path"], item["relative_path"])
            ok, _target, message = move_to_recycle(
                path, recycle_dir, reason="source_unit_cleanup",
                source_dir=unit["source_root"], extra_meta={"source_unit_id": unit["unit_id"]},
            )
            if not ok:
                return False, message
            remaining.remove(item)
            update_source_unit(
                self.conn,
                unit["unit_id"],
                snapshot_json=json.dumps(remaining, ensure_ascii=False, sort_keys=True),
            )
        return True, "已将源目录直属文件统一移入回收站"
