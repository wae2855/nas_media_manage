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
    is_fnos_app_managed_path,
)
from .storage_topology import validate_directory_topology

REMOTE_FILESYSTEMS = frozenset({
    "9p", "cifs", "davfs", "davfs2", "fuse.rclone", "fuse.sshfs",
    "nfs", "nfs4", "smb3", "sshfs",
})
LOCAL_ONLY_ROLES = frozenset({"temp", "recycle", "log", "resource"})
APP_MANAGED_ROLES = frozenset({"temp", "recycle", "log", "resource"})
# New imports write source -> target task staging only after scrape, routing,
# dedup and any manual review.  The temp role remains visible for legacy
# checkpoints, but an idle watcher must not stat it and wake an otherwise
# sleeping disk.
PROCESSING_SUPPORT_ROLES = frozenset({"source", "recycle", "log", "resource"})


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


def _legacy_target_root_specs(config: dict) -> list[tuple[str, str, str]]:
    """Compatibility roots for pre-migration absolute fallback/rule configs."""
    candidates = []
    fallback = str((config or {}).get("fallback_dir", "") or "").strip()
    if fallback and os.path.isabs(fallback):
        candidates.append(("legacy-fallback", "待整理片库", fallback))
    for index, rule in enumerate((config or {}).get("path_rules", []) or []):
        if not isinstance(rule, dict):
            continue
        template = str(rule.get("template", "") or "").strip()
        if not template or not os.path.isabs(template):
            continue
        static_parts = []
        for part in os.path.normpath(template).split(os.sep):
            if "{" in part:
                break
            static_parts.append(part)
        root = os.sep.join(static_parts) or os.sep
        candidates.append((f"legacy-rule-{index}", f"旧版目标规则 {index + 1}", root))
    unique = []
    seen = set()
    for item in candidates:
        normalized = os.path.normpath(item[2])
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append((item[0], item[1], normalized))
    return unique


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


def _mount_identity_changed(expected: dict, current: MountIdentity) -> bool:
    """Compare stable mount facts without treating ``st_dev`` as an identity.

    Linux allocates device numbers when filesystems are mounted.  The same
    physical volume can therefore receive a different ``st_dev`` after a
    restart or reinstall.  Mount source, mount point, filesystem type and
    realpath are stable enough to detect a genuinely different binding.
    ``device`` remains in the snapshot for diagnostics only.
    """
    if str(expected.get("realpath", "")) != current.realpath:
        return True
    for field, actual in (
        ("mount_source", current.mount_source),
        ("mount_point", current.mount_point),
        ("filesystem_type", current.filesystem_type),
    ):
        recorded = str(expected.get(field, "") or "")
        if recorded and recorded != "unknown" and recorded != actual:
            return True
    return False


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


def automatic_blocking_reasons(readiness: dict) -> list[str]:
    """Return plain-language reasons that prevent background automation."""
    locations = {
        str(item.get("id", "")): item
        for item in readiness.get("locations", [])
        if isinstance(item, dict)
    }
    location_ids = list(readiness.get("automatic_blocking", []) or [])
    if not location_ids and not readiness.get("automatic_allowed", False):
        location_ids = list(readiness.get("blocking", []) or [])

    reasons = []
    for location_id in location_ids:
        item = locations.get(str(location_id))
        if not item:
            continue
        label = str(item.get("label", "") or location_id)
        message = str(item.get("message", "") or "当前不满足自动运行条件")
        reasons.append(f"{label}：{message}")
    return reasons


def inspect_storage_readiness(
    config: dict,
    *,
    write_bytes: int = 0,
    reserved_bytes: int = 0,
    authorization_capability: dict | None = None,
    roles: set[str] | frozenset[str] | None = None,
    target_root_ids: set[str] | frozenset[str] | None = None,
    include_topology: bool = True,
    source_read_only: bool = False,
) -> dict:
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

    topology_conflicts = validate_directory_topology(config) if include_topology else []
    for index, conflict in enumerate(topology_conflicts):
        location_id = f"topology:{index}"
        locations.append({
            "id": location_id,
            "role": "topology",
            "label": "目录边界",
            "path": "",
            "status": "OFFLINE",
            "level": "error",
            "message": conflict.message,
            "capabilities": {
                "read": False,
                "write": False,
                "create": False,
                "update": False,
                "delete": False,
                "automatic": False,
            },
        })
        blocking.append(location_id)

    for role, path, need_write, location_id, label in _location_specs(config):
        if roles is not None and role not in roles:
            continue
        if (
            role == "target"
            and target_root_ids is not None
            and location_id.removeprefix("target:") not in target_root_ids
        ):
            continue
        if role == "source" and source_read_only:
            need_write = False
        managed_by_app = role in APP_MANAGED_ROLES and is_fnos_app_managed_path(path)
        item = {
            "id": location_id,
            "role": role,
            "label": label,
            "path": path,
            "status": "ONLINE",
            "level": "ok",
            "message": "可用",
            "managed_by_app": managed_by_app,
            "capabilities": {
                "read": False,
                "write": False,
                "create": False,
                "update": False,
                "delete": False,
                "automatic": True,
            },
        }
        if not path or not os.path.isabs(path):
            item.update(status="OFFLINE", level="error", message="目录未配置或不是绝对路径")
            blocking.append(location_id)
            locations.append(item)
            continue
        if authorization_enforced and not managed_by_app:
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
        item["capabilities"].update(
            read=readable,
            write=writable,
            create=writable,
            update=writable,
            # 这是产品操作上限，不是 POSIX ACL 推断。目标片库即使物理可写，
            # 通用删除仍由业务层禁止；逐项确认替换走独立的本地回收协议。
            delete=writable and role != "target",
        )
        expected = identities.get(location_id)
        if expected and not managed_by_app and _mount_identity_changed(expected, identity):
            item.update(status="RECOVERING", level="error", message="目录身份已变化，请确认挂载后重新绑定")
        elif not readable or (need_write and not writable):
            item.update(status="DEGRADED", level="error", message=write_error or "目录权限不足")
        elif role in LOCAL_ONLY_ROLES and identity.locality in {"remote", "unknown"}:
            item.update(status="DEGRADED", level="error", message="该目录必须位于可确认的本地磁盘")
        elif identity.locality == "remote" and role == "source":
            # ADR-0012：已识别的远程来源允许自动扫描。文件监控会在启动和
            # 每轮扫描前重检挂载身份、权限与可读性，并等待文件稳定后才建任务。
            item.update(
                status="DEGRADED",
                level="warning",
                message="网盘来源当前在线；后台运行会在每轮扫描前复核挂载和权限",
            )
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

        if role == "target" and item["level"] == "ok":
            item["message"] = "可读取并新增入库；不执行通用删除"
        elif managed_by_app and item["level"] == "ok":
            item["message"] = "应用私有目录可用，无需 fnOS 共享目录授权"

        if item["level"] == "error":
            blocking.append(location_id)
        elif item["level"] == "warning":
            warnings.append(location_id)
        locations.append(item)

    state = "READY" if not blocking else "BLOCKED"
    automatic_blocking = [
        str(item.get("id", ""))
        for item in locations
        if item.get("level") == "error"
        or not (item.get("capabilities", {}) or {}).get("automatic", False)
    ]
    return {
        "state": state,
        "automatic_allowed": state == "READY" and not automatic_blocking,
        "automatic_blocking": automatic_blocking,
        "blocking": blocking,
        "warnings": warnings,
        "locations": locations,
    }


def inspect_source_scan_readiness(
    config: dict,
    *,
    authorization_capability: dict | None = None,
) -> dict:
    """Check only the source facts required by an idle watcher scan."""
    return inspect_storage_readiness(
        config,
        authorization_capability=authorization_capability,
        roles={"source"},
        include_topology=False,
        source_read_only=True,
    )


def inspect_processing_support_readiness(
    config: dict,
    *,
    write_bytes: int = 0,
    reserved_bytes: int = 0,
    authorization_capability: dict | None = None,
) -> dict:
    """Check source and support storage without touching target libraries."""
    return inspect_storage_readiness(
        config,
        write_bytes=write_bytes,
        reserved_bytes=reserved_bytes,
        authorization_capability=authorization_capability,
        roles=PROCESSING_SUPPORT_ROLES,
        include_topology=False,
    )


def configured_target_for_path(config: dict, path: str) -> dict | None:
    """Resolve a normalized task path to one configured root without I/O."""
    value = str(path or "").strip()
    if not value or not os.path.isabs(value):
        return None
    candidate = os.path.normpath(os.path.abspath(value))
    matches = []
    specs = _target_root_specs(config)
    legacy = not specs
    if legacy:
        specs = _legacy_target_root_specs(config)
    for root_id, name, root in specs:
        root_value = str(root or "").strip()
        if not root_value or not os.path.isabs(root_value):
            continue
        root_path = os.path.normpath(os.path.abspath(root_value))
        try:
            if root_path and os.path.commonpath((candidate, root_path)) == root_path:
                matches.append({"id": root_id, "name": name, "path": root})
        except ValueError:
            continue
    if not matches:
        return None
    if not legacy:
        return matches[0] if len(matches) == 1 else None
    return sorted(matches, key=lambda item: len(str(item["path"])), reverse=True)[0]


def inspect_selected_target_readiness(
    config: dict,
    import_path: str,
    *,
    write_bytes: int = 0,
    reserved_bytes: int = 0,
    authorization_capability: dict | None = None,
) -> dict:
    """Check only the library selected by a classified task."""
    target = configured_target_for_path(config, import_path)
    if target is None:
        location_id = "target:selected"
        return {
            "state": "BLOCKED",
            "automatic_allowed": False,
            "automatic_blocking": [location_id],
            "blocking": [location_id],
            "warnings": [],
            "locations": [{
                "id": location_id,
                "role": "target",
                "label": "目标片库",
                "path": str(import_path or ""),
                "status": "OFFLINE",
                "level": "error",
                "message": "入库路径无法唯一归属于已启用片库",
                "capabilities": {
                    "read": False,
                    "write": False,
                    "create": False,
                    "update": False,
                    "delete": False,
                    "automatic": False,
                },
            }],
        }
    scoped_config = config
    configured_ids = {root_id for root_id, _name, _path in _target_root_specs(config)}
    if str(target["id"]) not in configured_ids:
        scoped_config = dict(config or {})
        scoped_config["library_roots"] = [{
            "id": str(target["id"]),
            "name": str(target["name"]),
            "path": str(target["path"]),
            "enabled": True,
        }]
    return inspect_storage_readiness(
        scoped_config,
        write_bytes=write_bytes,
        reserved_bytes=reserved_bytes,
        authorization_capability=authorization_capability,
        roles={"target"},
        target_root_ids={str(target["id"])},
        include_topology=False,
    )
