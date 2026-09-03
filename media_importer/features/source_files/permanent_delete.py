"""ADR-0019 来源专用永久删除协议。

原始来源路径只允许被同盘重命名到任务专属隔离区；实际 unlink/rmdir
只发生在已验证的隔离区目录描述符之下。
"""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timezone

from media_importer.features.configuration.storage_readiness import inspect_mount
from media_importer.features.configuration.storage_topology import (
    canonical_path,
    path_within,
    paths_overlap,
)

IDENTITY_MODE_INODE = "inode"
IDENTITY_MODE_REMOTE_SNAPSHOT = "remote_snapshot"


@dataclass(frozen=True)
class PermanentDeleteResult:
    ok: bool
    state: str
    message: str
    claimed_count: int = 0
    deleted_count: int = 0
    ledger_path: str = ""


def _operation_slug(operation_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(operation_id or "")).strip(".-")
    if not slug:
        raise ValueError("永久删除缺少任务标识")
    return slug[:96]


def _append_ledger(path: str, event: dict, *, create: bool = False) -> None:
    flags = os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    if create:
        flags |= os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink != 1:
            raise OSError("来源删除账本不是独立普通文件")
        payload = {
            "at": datetime.now(timezone.utc).isoformat(),
            **event,
        }
        encoded = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        offset = 0
        while offset < len(encoded):
            offset += os.write(descriptor, encoded[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _sync_directory(path: str) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        pass


def _archive_ledger(path: str, state: str) -> str:
    archived = f"{path}.{state.lower()}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    os.rename(path, archived)
    _sync_directory(os.path.dirname(path))
    return archived


def _snapshot_entry(path: str, *, expected_device: int | None = None) -> dict:
    entry_stat = os.lstat(path)
    if expected_device is not None and entry_stat.st_dev != expected_device:
        raise ValueError(f"来源包含嵌套挂载点，拒绝永久删除: {path}")
    if stat.S_ISLNK(entry_stat.st_mode):
        raise ValueError(f"来源包含符号链接，拒绝永久删除: {path}")
    if stat.S_ISREG(entry_stat.st_mode):
        return {
            "type": "file",
            "device": entry_stat.st_dev,
            "inode": entry_stat.st_ino,
            "size": entry_stat.st_size,
            "mtime_ns": entry_stat.st_mtime_ns,
        }
    if stat.S_ISDIR(entry_stat.st_mode):
        children = []
        with os.scandir(path) as iterator:
            for child in sorted(iterator, key=lambda item: item.name):
                children.append({
                    "name": child.name,
                    **_snapshot_entry(child.path, expected_device=expected_device),
                })
        return {
            "type": "directory",
            "device": entry_stat.st_dev,
            "inode": entry_stat.st_ino,
            "mtime_ns": entry_stat.st_mtime_ns,
            "children": children,
        }
    raise ValueError(f"来源包含特殊文件，拒绝永久删除: {path}")


def _mount_evidence(path: str) -> dict:
    identity = inspect_mount(path)
    return {
        "realpath": identity.realpath,
        "filesystem_type": identity.filesystem_type,
        "mount_point": identity.mount_point,
        "mount_source": identity.mount_source,
        "locality": identity.locality,
    }


def _identity_context(source_root: str, prepared: dict | None = None) -> tuple[str, dict, int]:
    current = _mount_evidence(source_root)
    stored_mode = str((prepared or {}).get("identity_mode", ""))
    if stored_mode and stored_mode not in {
        IDENTITY_MODE_INODE,
        IDENTITY_MODE_REMOTE_SNAPSHOT,
    }:
        raise OSError("来源删除账本包含未知身份模式")
    inferred_mode = (
        IDENTITY_MODE_REMOTE_SNAPSHOT
        if current.get("locality") == "remote"
        else IDENTITY_MODE_INODE
    )
    mode = stored_mode or inferred_mode
    if mode == IDENTITY_MODE_REMOTE_SNAPSHOT and current.get("locality") != "remote":
        raise OSError("来源远程挂载身份已失效或无法识别")
    expected_mount = (prepared or {}).get("source_mount")
    if expected_mount:
        for key in ("realpath", "filesystem_type", "mount_point", "mount_source", "locality"):
            if str(expected_mount.get(key, "")) != str(current.get(key, "")):
                raise OSError(f"来源挂载身份发生变化: {key}")
    return mode, current, os.lstat(source_root).st_dev


def _validate_member(source_root: str, path: str, protected_roots: list[str]) -> tuple[str, dict]:
    if os.path.islink(path):
        raise ValueError(f"来源成员是符号链接，拒绝永久删除: {path}")
    real = canonical_path(path)
    if not path_within(real, source_root, allow_root=False):
        raise ValueError(f"来源成员不在当前来源目录内: {path}")
    if any(paths_overlap(real, root) for root in protected_roots if root):
        raise ValueError("来源成员与目标片库边界重叠，拒绝永久删除")
    source_device = os.lstat(source_root).st_dev
    return real, _snapshot_entry(real, expected_device=source_device)


def _restore_claimed(
    claimed: list[tuple[str, str]],
    *,
    expected_by_original: dict[str, dict] | None = None,
    expected_device: int | None = None,
    identity_mode: str = IDENTITY_MODE_INODE,
) -> list[str]:
    failed = []
    for original, claimed_path in reversed(claimed):
        try:
            if os.path.lexists(original):
                expected = (expected_by_original or {}).get(original)
                if (
                    expected
                    and not os.path.lexists(claimed_path)
                    and _snapshot_is_subset(
                        _snapshot_entry(original, expected_device=expected_device),
                        expected,
                        identity_mode=identity_mode,
                    )
                ):
                    continue
                failed.append(original)
                continue
            os.rename(claimed_path, original)
        except (OSError, ValueError):
            failed.append(original)
    return failed


def _delete_directory_fd(directory_fd: int, *, expected_device: int) -> int:
    if os.fstat(directory_fd).st_dev != expected_device:
        raise OSError("任务删除隔离区跨越了其他文件系统")
    deleted = 0
    for name in sorted(os.listdir(directory_fd)):
        item_stat = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if item_stat.st_dev != expected_device:
            raise OSError(f"隔离区出现嵌套挂载点，停止永久删除: {name}")
        if stat.S_ISLNK(item_stat.st_mode):
            raise OSError(f"隔离区出现符号链接，停止永久删除: {name}")
        if stat.S_ISREG(item_stat.st_mode):
            os.unlink(name, dir_fd=directory_fd)
            deleted += 1
            continue
        if stat.S_ISDIR(item_stat.st_mode):
            child_fd = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_fd,
            )
            try:
                deleted += _delete_directory_fd(
                    child_fd,
                    expected_device=expected_device,
                )
            finally:
                os.close(child_fd)
            os.rmdir(name, dir_fd=directory_fd)
            deleted += 1
            continue
        raise OSError(f"隔离区出现特殊文件，停止永久删除: {name}")
    os.fsync(directory_fd)
    return deleted


def _delete_directory_path(directory: str, *, expected_device: int, deletion_root: str) -> int:
    """为不支持 dir-fd 的远程挂载删除已验证隔离区，绝不接受业务来源路径。"""

    if not path_within(directory, deletion_root, allow_root=True):
        raise OSError("远程删除路径越过任务隔离区")
    directory_stat = os.lstat(directory)
    if not stat.S_ISDIR(directory_stat.st_mode) or stat.S_ISLNK(directory_stat.st_mode):
        raise OSError("任务删除隔离区目录身份异常")
    if directory_stat.st_dev != expected_device:
        raise OSError("任务删除隔离区跨越了其他文件系统")
    deleted = 0
    with os.scandir(directory) as iterator:
        names = sorted(item.name for item in iterator)
    for name in names:
        path = os.path.join(directory, name)
        if not path_within(path, deletion_root, allow_root=False):
            raise OSError("远程删除成员越过任务隔离区")
        item_stat = os.lstat(path)
        if item_stat.st_dev != expected_device:
            raise OSError(f"隔离区出现嵌套挂载点，停止永久删除: {name}")
        if stat.S_ISLNK(item_stat.st_mode):
            raise OSError(f"隔离区出现符号链接，停止永久删除: {name}")
        if stat.S_ISREG(item_stat.st_mode):
            os.unlink(path)
            deleted += 1
            continue
        if stat.S_ISDIR(item_stat.st_mode):
            deleted += _delete_directory_path(
                path,
                expected_device=expected_device,
                deletion_root=deletion_root,
            )
            os.rmdir(path)
            deleted += 1
            continue
        raise OSError(f"隔离区出现特殊文件，停止永久删除: {name}")
    _sync_directory(directory)
    return deleted


def _read_ledger(path: str) -> list[dict]:
    ledger_stat = os.lstat(path)
    if not stat.S_ISREG(ledger_stat.st_mode) or ledger_stat.st_nlink != 1:
        raise OSError("来源删除账本身份无效")
    events = []
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                events.append(json.loads(line))
    if not events or events[0].get("state") != "PREPARED":
        raise OSError("来源删除账本缺少准备记录")
    return events


def _snapshot_is_subset(
    current: dict,
    expected: dict,
    *,
    identity_mode: str = IDENTITY_MODE_INODE,
) -> bool:
    if current.get("type") != expected.get("type"):
        return False
    if identity_mode == IDENTITY_MODE_INODE:
        for key in ("device", "inode"):
            if current.get(key) != expected.get(key):
                return False
    if current.get("type") == "file":
        return all(
            current.get(key) == expected.get(key)
            for key in ("size", "mtime_ns")
        )
    expected_children = {
        str(item.get("name", "")): item
        for item in expected.get("children", [])
    }
    for child in current.get("children", []):
        expected_child = expected_children.get(str(child.get("name", "")))
        if expected_child is None or not _snapshot_is_subset(
            child,
            expected_child,
            identity_mode=identity_mode,
        ):
            return False
    return True


def _validate_tombstone_contents(
    tombstone: str,
    prepared: dict,
    events: list[dict],
    *,
    identity_mode: str,
    current_device: int,
) -> None:
    expected_by_original = {
        str(item.get("original_path", "")): item.get("snapshot", {})
        for item in prepared.get("members", [])
    }
    expected_by_claimed = {
        os.path.basename(str(event.get("claimed_path", ""))): expected_by_original.get(
            str(event.get("original_path", "")),
            {},
        )
        for event in events
        if event.get("state") == "MEMBER_CLAIMED"
    }
    if not os.path.isdir(tombstone) or os.path.islink(tombstone):
        raise OSError("任务删除隔离区不存在或身份异常")
    with os.scandir(tombstone) as iterator:
        for child in iterator:
            expected = expected_by_claimed.get(child.name)
            if not expected or not _snapshot_is_subset(
                _snapshot_entry(
                    child.path,
                    expected_device=current_device,
                ),
                expected,
                identity_mode=identity_mode,
            ):
                raise OSError(f"任务删除隔离区出现非认领内容或成员变化: {child.name}")


def _finish_tombstone(
    tombstone: str,
    prepared: dict,
    *,
    identity_mode: str,
    current_device: int,
) -> int:
    tombstone_stat = os.lstat(tombstone)
    if (
        not stat.S_ISDIR(tombstone_stat.st_mode)
        or tombstone_stat.st_dev != current_device
        or (
            identity_mode == IDENTITY_MODE_INODE
            and (
                tombstone_stat.st_dev != prepared.get("tombstone_device")
                or tombstone_stat.st_ino != prepared.get("tombstone_inode")
            )
        )
    ):
        raise OSError("任务删除隔离区身份发生变化")
    if identity_mode == IDENTITY_MODE_REMOTE_SNAPSHOT:
        deleted_count = _delete_directory_path(
            tombstone,
            expected_device=current_device,
            deletion_root=tombstone,
        )
        os.rmdir(tombstone)
        _sync_directory(os.path.dirname(tombstone))
        return deleted_count
    directory_fd = os.open(
        tombstone,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        deleted_count = _delete_directory_fd(
            directory_fd,
            expected_device=current_device,
        )
    finally:
        os.close(directory_fd)
    os.rmdir(tombstone)
    _sync_directory(os.path.dirname(tombstone))
    return deleted_count


def _validated_ledger_claims(
    prepared: dict,
    events: list[dict],
    *,
    source_root: str,
    tombstone: str,
    protected_roots: list[str],
) -> tuple[list[tuple[str, str]], dict[str, dict]]:
    """账本只描述当前来源中的精确成员和当前任务隔离区中的认领路径。"""

    expected_by_original: dict[str, dict] = {}
    for member in prepared.get("members", []):
        original = str(member.get("original_path", ""))
        if (
            not original
            or not path_within(original, source_root, allow_root=False)
            or any(paths_overlap(original, root) for root in protected_roots if root)
        ):
            raise OSError("来源删除账本包含越界的原始路径")
        if original in expected_by_original:
            raise OSError("来源删除账本包含重复的原始路径")
        expected_by_original[original] = member.get("snapshot", {})

    claimed: list[tuple[str, str]] = []
    seen_originals: set[str] = set()
    seen_claimed: set[str] = set()
    for event in events:
        if event.get("state") != "MEMBER_CLAIMED":
            continue
        original = str(event.get("original_path", ""))
        claimed_path = str(event.get("claimed_path", ""))
        if original not in expected_by_original:
            raise OSError("来源删除账本认领了未准备的原始路径")
        if (
            not path_within(claimed_path, tombstone, allow_root=False)
            or os.path.dirname(claimed_path) != tombstone
        ):
            raise OSError("来源删除账本包含越界的隔离区路径")
        if original in seen_originals or claimed_path in seen_claimed:
            raise OSError("来源删除账本包含重复认领记录")
        seen_originals.add(original)
        seen_claimed.add(claimed_path)
        claimed.append((original, claimed_path))
    return claimed, expected_by_original


def resume_permanent_source_delete(
    ledger_path: str,
    *,
    source_root: str,
    protected_roots: list[str] | None = None,
) -> PermanentDeleteResult:
    """只按调用方给出的已知账本恢复，不扫描或猜测隐藏隔离区。"""

    try:
        events = _read_ledger(ledger_path)
        prepared = events[0]
        root = canonical_path(source_root)
        if canonical_path(str(prepared.get("source_root", ""))) != root:
            raise OSError("来源删除账本不属于当前来源目录")
        tombstone = str(prepared.get("tombstone", ""))
        if not path_within(tombstone, root, allow_root=False):
            raise OSError("来源删除隔离区越过当前来源目录")
        if any(paths_overlap(tombstone, item) for item in (protected_roots or []) if item):
            raise OSError("来源删除隔离区与目标片库边界重叠")
        claimed, expected_by_original = _validated_ledger_claims(
            prepared,
            events,
            source_root=root,
            tombstone=tombstone,
            protected_roots=list(protected_roots or []),
        )
        identity_mode, _mount, current_device = _identity_context(root, prepared)
        last_state = str(events[-1].get("state", ""))
        if last_state == "DONE":
            archived = _archive_ledger(ledger_path, "DONE")
            return PermanentDeleteResult(
                True, "DELETED", "来源永久删除已完成", ledger_path=archived,
            )
        if last_state in {"CLAIMED", "DELETE_FAILED"}:
            if not os.path.lexists(tombstone):
                all_claimed = len(claimed) == len(expected_by_original)
                originals_absent = all(
                    not os.path.lexists(original)
                    for original in expected_by_original
                )
                if all_claimed and originals_absent:
                    _append_ledger(
                        ledger_path,
                        {
                            "state": "DONE",
                            "claimed_count": len(claimed),
                            "deleted_count": 0,
                            "resumed": True,
                            "inferred_after_commit": True,
                        },
                    )
                    archived = _archive_ledger(ledger_path, "DONE")
                    return PermanentDeleteResult(
                        True,
                        "DELETED",
                        "来源隔离区已删除完成，已恢复任务完成记录",
                        claimed_count=len(claimed),
                        ledger_path=archived,
                    )
                raise OSError("任务删除隔离区缺失，且无法证明全部认领成员已完成删除")
            _validate_tombstone_contents(
                tombstone,
                prepared,
                events,
                identity_mode=identity_mode,
                current_device=current_device,
            )
            deleted_count = _finish_tombstone(
                tombstone,
                prepared,
                identity_mode=identity_mode,
                current_device=current_device,
            )
            _append_ledger(
                ledger_path,
                {
                    "state": "DONE",
                    "claimed_count": len(claimed),
                    "deleted_count": deleted_count,
                    "resumed": True,
                },
            )
            archived = _archive_ledger(ledger_path, "DONE")
            return PermanentDeleteResult(
                True,
                "DELETED",
                "已继续完成来源永久删除（无法恢复）",
                claimed_count=len(claimed),
                deleted_count=deleted_count,
                ledger_path=archived,
            )
        restore_failures = _restore_claimed(
            claimed,
            expected_by_original=expected_by_original,
            expected_device=current_device,
            identity_mode=identity_mode,
        )
        tombstone_empty_or_absent = not os.path.lexists(tombstone)
        if os.path.isdir(tombstone) and not os.path.islink(tombstone):
            tombstone_empty_or_absent = not os.listdir(tombstone)
        if not restore_failures and tombstone_empty_or_absent:
            if os.path.isdir(tombstone):
                os.rmdir(tombstone)
            _append_ledger(ledger_path, {"state": "ROLLED_BACK", "resumed": True})
            archived = _archive_ledger(ledger_path, "ROLLED_BACK")
            return PermanentDeleteResult(
                False,
                "BLOCKED",
                "未完成的永久删除认领已安全回退，来源保持不变",
                claimed_count=len(claimed),
                ledger_path=archived,
            )
        _append_ledger(
            ledger_path,
            {"state": "ROLLBACK_FAILED", "restore_failures": restore_failures, "resumed": True},
        )
        return PermanentDeleteResult(
            False,
            "PARTIAL",
            "来源删除恢复失败，部分内容仍在任务隔离区，需要人工检查",
            claimed_count=len(claimed),
            ledger_path=ledger_path,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return PermanentDeleteResult(False, "BLOCKED", f"来源删除恢复检查失败: {exc}")


def permanently_delete_source_members(
    paths: list[str],
    *,
    source_root: str,
    operation_id: str,
    ledger_dir: str,
    protected_roots: list[str] | None = None,
) -> PermanentDeleteResult:
    """认领并永久删除精确来源成员；不接受来源根本身。"""

    if not paths:
        return PermanentDeleteResult(True, "SKIPPED", "没有需要永久删除的来源内容")
    root = canonical_path(source_root)
    if not root or not os.path.isdir(root) or os.path.islink(source_root):
        return PermanentDeleteResult(False, "BLOCKED", "来源目录不存在、失效或是符号链接")
    tombstone = ""
    ledger_path = ""
    try:
        slug = _operation_slug(operation_id)
        identity_mode, mount_evidence, current_device = _identity_context(root)
        validated = [
            _validate_member(root, path, list(protected_roots or []))
            for path in paths
        ]
        real_paths = [item[0] for item in validated]
        for index, candidate in enumerate(real_paths):
            if any(
                index != other_index and paths_overlap(candidate, other)
                for other_index, other in enumerate(real_paths)
            ):
                raise ValueError("永久删除成员范围互相包含，已停止避免重复处理")
        os.makedirs(ledger_dir, mode=0o700, exist_ok=True)
        if os.path.islink(ledger_dir):
            raise ValueError("来源删除账本目录不能是符号链接")
        ledger_real = canonical_path(ledger_dir)
        if any(paths_overlap(ledger_real, path) for path in real_paths):
            raise ValueError("来源删除账本目录不能位于待删除来源成员内")
        if any(paths_overlap(ledger_real, root_path) for root_path in (protected_roots or []) if root_path):
            raise ValueError("来源删除账本目录不能位于目标片库内")
        ledger_path = os.path.join(ledger_dir, f"source-delete-{slug}.jsonl")
        tombstone = os.path.join(root, f".nas-media-delete-{slug}.deleting")
        if os.path.lexists(tombstone) or os.path.lexists(ledger_path):
            raise ValueError("同一来源删除任务已有未完成记录，请先执行恢复检查")
        os.mkdir(tombstone, mode=0o700)
        tombstone_stat = os.lstat(tombstone)
        _append_ledger(
            ledger_path,
            {
                "state": "PREPARED",
                "operation_id": slug,
                "source_root": root,
                "tombstone": tombstone,
                "tombstone_device": tombstone_stat.st_dev,
                "tombstone_inode": tombstone_stat.st_ino,
                "identity_mode": identity_mode,
                "source_mount": mount_evidence,
                "members": [
                    {"original_path": path, "snapshot": snapshot}
                    for path, snapshot in validated
                ],
            },
            create=True,
        )
        _sync_directory(root)
    except (OSError, ValueError) as exc:
        if tombstone and (not ledger_path or not os.path.lexists(ledger_path)):
            try:
                if os.path.isdir(tombstone) and not os.listdir(tombstone):
                    os.rmdir(tombstone)
            except OSError:
                pass
        return PermanentDeleteResult(False, "BLOCKED", str(exc))

    claimed: list[tuple[str, str]] = []
    try:
        for index, (original, snapshot) in enumerate(validated):
            if not _snapshot_is_subset(
                _snapshot_entry(original, expected_device=current_device),
                snapshot,
                identity_mode=identity_mode,
            ):
                raise OSError(f"来源成员在删除前发生变化: {original}")
            claimed_path = os.path.join(tombstone, f"{index:04d}-{os.path.basename(original)}")
            if os.path.lexists(claimed_path):
                raise OSError("任务删除隔离区发生名称冲突")
            os.rename(original, claimed_path)
            claimed.append((original, claimed_path))
            _append_ledger(
                ledger_path,
                {"state": "MEMBER_CLAIMED", "original_path": original, "claimed_path": claimed_path},
            )
        _sync_directory(root)
        _append_ledger(ledger_path, {"state": "CLAIMED", "claimed_count": len(claimed)})
    except (OSError, ValueError) as exc:
        restore_failures = _restore_claimed(
            claimed,
            expected_by_original={path: snapshot for path, snapshot in validated},
            expected_device=current_device,
            identity_mode=identity_mode,
        )
        state = "PARTIAL" if restore_failures else "BLOCKED"
        _append_ledger(
            ledger_path,
            {"state": "CLAIM_FAILED", "error": str(exc), "restore_failures": restore_failures},
        )
        try:
            if not os.listdir(tombstone):
                os.rmdir(tombstone)
        except OSError:
            pass
        message = f"永久删除认领失败，来源已保留: {exc}"
        if restore_failures:
            message = "永久删除认领中断，部分成员停留在任务隔离区，请勿手动移动并执行恢复检查"
        return PermanentDeleteResult(
            False, state, message, claimed_count=len(claimed), ledger_path=ledger_path,
        )

    try:
        _validate_tombstone_contents(
            tombstone,
            {
                "tombstone_device": tombstone_stat.st_dev,
                "identity_mode": identity_mode,
                "members": [
                    {"original_path": path, "snapshot": snapshot}
                    for path, snapshot in validated
                ],
            },
            [
                {
                    "state": "MEMBER_CLAIMED",
                    "original_path": original,
                    "claimed_path": claimed_path,
                }
                for original, claimed_path in claimed
            ],
            identity_mode=identity_mode,
            current_device=current_device,
        )
        deleted_count = _finish_tombstone(
            tombstone,
            {
                "tombstone_device": tombstone_stat.st_dev,
                "tombstone_inode": tombstone_stat.st_ino,
            },
            identity_mode=identity_mode,
            current_device=current_device,
        )
        _append_ledger(
            ledger_path,
            {"state": "DONE", "claimed_count": len(claimed), "deleted_count": deleted_count},
        )
        archived = _archive_ledger(ledger_path, "DONE")
        return PermanentDeleteResult(
            True,
            "DELETED",
            f"已永久删除 {len(claimed)} 个来源成员（无法恢复）",
            claimed_count=len(claimed),
            deleted_count=deleted_count,
            ledger_path=archived,
        )
    except OSError as exc:
        _append_ledger(ledger_path, {"state": "DELETE_FAILED", "error": str(exc)})
        return PermanentDeleteResult(
            False,
            "PARTIAL",
            f"来源成员已认领到任务隔离区，但永久删除未完成：{exc}；修复后将从隔离区继续处理",
            claimed_count=len(claimed),
            ledger_path=ledger_path,
        )


__all__ = [
    "PermanentDeleteResult",
    "permanently_delete_source_members",
    "resume_permanent_source_delete",
]
