"""配置页与文件副作用入口共享的存储就绪事实。"""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import asdict, dataclass

from media_importer.infrastructure.filesystem import check_write_permission

from .fnos_directory_access import (
    authorized_root_for_path,
    build_fnos_directory_capability,
)
from .storage_topology import validate_directory_topology

REMOTE_FILESYSTEMS = frozenset({
    "9p", "cifs", "davfs", "davfs2", "fuse.rclone", "fuse.sshfs",
    "nfs", "nfs4", "smb3", "sshfs",
})
LOCAL_ONLY_ROLES = frozenset({"temp", "recycle", "log", "resource"})


@dataclass(frozen=True)
class MountIdentity:
    realpath: str
    device: int
    filesystem_type: str
    mount_point: str
    mount_source: str
    locality: str


def _decode_mount_field(value: str) -> str:
    return value.replace("\\040", " ").replace("\\011", "\t").replace("\\134", "\\")


def _linux_mounts() -> list[tuple[str, str, str]]:
    mounts = []
    try:
        with open("/proc/self/mountinfo", encoding="utf-8") as handle:
            for line in handle:
                left, right = line.rstrip().split(" - ", 1)
                left_fields = left.split()
                right_fields = right.split()
                mounts.append((
                    _decode_mount_field(left_fields[4]),
                    right_fields[0],
                    _decode_mount_field(right_fields[1]),
                ))
    except (OSError, ValueError, IndexError):
        return []
    return sorted(mounts, key=lambda item: len(item[0]), reverse=True)


def inspect_mount(path: str) -> MountIdentity:
    realpath = os.path.realpath(path)
    stat = os.stat(realpath)
    mount_point = ""
    filesystem_type = "unknown"
    mount_source = "unknown"
    for candidate, candidate_type, candidate_source in _linux_mounts():
        try:
            if os.path.commonpath([realpath, candidate]) == candidate:
                mount_point = candidate
                filesystem_type = candidate_type
                mount_source = candidate_source
                break
        except ValueError:
            continue
    if filesystem_type in REMOTE_FILESYSTEMS or filesystem_type.startswith("fuse."):
        locality = "remote"
    elif filesystem_type != "unknown":
        locality = "local"
    elif platform.system() != "Linux":
        # 非 fnOS 的本地开发环境没有 /proc/mountinfo；只用于开发预览。
        locality = "local-development"
    else:
        locality = "unknown"
    return MountIdentity(
        realpath=realpath,
        device=stat.st_dev,
        filesystem_type=filesystem_type,
        mount_point=mount_point,
        mount_source=mount_source,
        locality=locality,
    )


def _target_roots(config: dict) -> list[str]:
    configured_roots = config.get("library_roots")
    if isinstance(configured_roots, list) and configured_roots:
        return [
            str(root.get("path", "") or "")
            for root in configured_roots
            if isinstance(root, dict) and root.get("enabled", True) is not False
        ]
    library_root = str(config.get("library_root", "") or "").strip()
    if library_root:
        return [library_root]
    # Fresh installs have no target roots. Legacy absolute rules are migrated
    # only after the user explicitly chooses their physical library roots.
    return []


def _target_root_specs(config: dict) -> list[tuple[str, str, str]]:
    configured_roots = config.get("library_roots")
    if isinstance(configured_roots, list) and configured_roots:
        return [
            (
                str(root.get("id", "") or index),
                str(root.get("name", "") or f"目标片库 {index + 1}"),
                str(root.get("path", "") or ""),
            )
            for index, root in enumerate(configured_roots)
            if isinstance(root, dict) and root.get("enabled", True) is not False
        ]
    root_id = "default" if config.get("library_root") else "0"
    roots = _target_roots(config)
    return [
        (root_id if len(roots) == 1 else str(index), "目标片库", root)
        for index, root in enumerate(roots)
    ]


def _location_specs(config: dict) -> list[tuple[str, str, bool, str, str]]:
    source_policy = config.get("source_policy", {}) or {}
    source_cleaner = config.get("source_cleaner", {}) or {}
    mode = source_policy.get("mode")
    if mode not in {"preserve_all", "preserve_media", "recycle_source_unit"}:
        mode = "recycle_source_unit" if source_policy.get("cleanup_source_after_done") is True else "preserve_all"
    source_write = mode == "recycle_source_unit" or (
        mode == "preserve_media" and source_cleaner.get("enabled") is True
    )
    specs = [
        ("source", config.get("source_dir", ""), source_write, "source", "文件来源"),
        ("temp", config.get("temp_dir", ""), True, "temp", "本地中转"),
        ("recycle", source_policy.get("recycle_dir", "") or source_policy.get("quarantine_dir", ""), True, "recycle", "本地回收"),
    ]
    log_dir = config.get("log_dir", "")
    if log_dir:
        specs.append(("log", log_dir, True, "log", "运行日志"))
    resource_dir = config.get("resource_dir", "") or config.get("resources_dir", "")
    if resource_dir:
        specs.append(("resource", resource_dir, True, "resource", "海报与缓存"))
    specs.extend(
        ("target", root, True, f"target:{root_id}", name)
        for root_id, name, root in _target_root_specs(config)
    )
    return specs


def _check_write(path: str) -> tuple[bool, str]:
    return check_write_permission(path)


def _capacity(path: str, write_bytes: int, reserved_bytes: int) -> dict:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return {"known": False, "total": None, "free": None, "required": None, "reserve": None}
    reserve = max(1024 ** 3, int(usage.total * 0.05))
    required = max(0, write_bytes) + max(0, reserved_bytes) + reserve
    return {
        "known": True,
        "total": usage.total,
        "free": usage.free,
        "required": required,
        "reserve": reserve,
    }


def inspect_storage_readiness(config: dict, *, write_bytes: int = 0,
                              reserved_bytes: int = 0,
                              authorization_capability: dict | None = None) -> dict:
    locations = []
    blocking = []
    warnings = []
    identities = config.get("storage_identities", {}) or {}
    authorization = (
        authorization_capability
        if authorization_capability is not None
        else build_fnos_directory_capability()
    )
    authorization_enforced = bool(authorization.get("enforced"))
    authorization_available = bool(authorization.get("available"))
    authorized_folders = authorization.get("folders") or []

    for index, conflict in enumerate(validate_directory_topology(config)):
        location_id = f"topology:{index}"
        locations.append({
            "id": location_id,
            "role": "topology",
            "label": "目录边界",
            "path": "",
            "status": "OFFLINE",
            "level": "error",
            "message": conflict.message,
            "capabilities": {"read": False, "write": False, "automatic": False},
        })
        blocking.append(location_id)

    for role, path, need_write, location_id, label in _location_specs(config):
        item = {
            "id": location_id,
            "role": role,
            "label": label,
            "path": path,
            "status": "ONLINE",
            "level": "ok",
            "message": "可用",
            "capabilities": {"read": False, "write": False, "automatic": True},
        }
        if not path or not os.path.isabs(path):
            item.update(status="OFFLINE", level="error", message="目录未配置或不是绝对路径")
            blocking.append(location_id)
            locations.append(item)
            continue
        if role in {"source", "target", "recycle"} and authorization_enforced:
            authorized_root = (
                authorized_root_for_path(path, authorized_folders)
                if authorization_available else ""
            )
            item["authorization"] = {
                "required": True,
                "authorized": bool(authorized_root),
                "root": authorized_root,
            }
            if not authorization_available:
                item.update(
                    status="OFFLINE", level="error",
                    message="无法确认 fnOS 目录授权，请刷新授权状态后重试",
                )
                blocking.append(location_id)
                locations.append(item)
                continue
            if not authorized_root:
                item.update(
                    status="OFFLINE", level="error",
                    message="目录尚未授权给本应用，请先通过 fnOS 目录选择器授权",
                )
                blocking.append(location_id)
                locations.append(item)
                continue
        if not os.path.isdir(path):
            item.update(status="OFFLINE", level="error", message="目录不存在；可能尚未授权或挂载已失效")
            blocking.append(location_id)
            locations.append(item)
            continue
        try:
            identity = inspect_mount(path)
        except OSError as exc:
            item.update(status="OFFLINE", level="error", message=f"无法读取目录身份: {exc}")
            blocking.append(location_id)
            locations.append(item)
            continue

        item["identity"] = asdict(identity)
        readable = os.access(path, os.R_OK | os.X_OK)
        writable, write_error = _check_write(path) if need_write else (os.access(path, os.W_OK), "")
        item["capabilities"].update(read=readable, write=writable)
        expected = identities.get(location_id)
        if expected and (
            expected.get("realpath") != identity.realpath
            or expected.get("device") != identity.device
            or expected.get("mount_source") != identity.mount_source
        ):
            item.update(status="RECOVERING", level="error", message="目录身份已变化，请确认挂载后重新绑定")
        elif not readable or (need_write and not writable):
            item.update(status="DEGRADED", level="error", message=write_error or "目录权限不足")
        elif role in LOCAL_ONLY_ROLES and identity.locality in {"remote", "unknown"}:
            item.update(status="DEGRADED", level="error", message="该目录必须位于可确认的本地磁盘")
        elif identity.locality in {"remote", "unknown"}:
            item.update(status="DEGRADED", level="warning", message="远程容量或原子发布能力有限，仅允许人工任务")
            item["capabilities"]["automatic"] = False

        if need_write:
            item["capacity"] = _capacity(path, write_bytes, reserved_bytes)
            capacity = item["capacity"]
            if not capacity["known"] and role in LOCAL_ONLY_ROLES:
                item.update(status="DEGRADED", level="error", message="无法读取本地磁盘容量")
            elif capacity["known"] and capacity["free"] < capacity["required"]:
                item.update(status="DEGRADED", level="error", message="磁盘可用空间不足")
            elif (
                capacity["known"]
                and capacity["free"] - write_bytes - reserved_bytes < 2 * capacity["reserve"]
                and item["level"] == "ok"
            ):
                item.update(status="DEGRADED", level="warning", message="操作后剩余空间接近安全余量")
                item["capabilities"]["automatic"] = False

        if item["level"] == "error":
            blocking.append(location_id)
        elif item["level"] == "warning":
            warnings.append(location_id)
        locations.append(item)

    state = "READY" if not blocking else "BLOCKED"
    return {
        "state": state,
        "automatic_allowed": state == "READY" and not warnings,
        "blocking": blocking,
        "warnings": warnings,
        "locations": locations,
    }
