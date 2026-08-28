"""配置页与文件副作用入口共享的存储就绪事实。"""

from __future__ import annotations

import os
import platform
import shutil
import tempfile
from dataclasses import asdict, dataclass

REMOTE_FILESYSTEMS = frozenset({
    "9p", "cifs", "davfs", "davfs2", "fuse.rclone", "fuse.sshfs",
    "nfs", "nfs4", "smb3", "sshfs",
})
LOCAL_ONLY_ROLES = frozenset({"temp", "recycle", "log"})


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
    candidates = []
    for rule in config.get("path_rules", []) or []:
        template = rule.get("template", "") if isinstance(rule, dict) else ""
        prefix = template.split("{", 1)[0].rstrip(os.sep)
        if prefix:
            candidates.append(os.path.dirname(prefix) if os.path.splitext(prefix)[1] else prefix)
    fallback = config.get("fallback_dir", "")
    if fallback:
        candidates.append(fallback)

    groups = {}
    for candidate in dict.fromkeys(candidates):
        parts = os.path.abspath(candidate).split(os.sep)
        volume_anchor = parts[1] if len(parts) > 1 else ""
        groups.setdefault(volume_anchor, []).append(candidate)
    roots = []
    for paths in groups.values():
        try:
            common = os.path.commonpath(paths)
        except ValueError:
            common = ""
        volume_root = os.sep + os.path.abspath(paths[0]).split(os.sep)[1]
        if common and common not in {os.sep, volume_root}:
            roots.append(common)
        else:
            roots.extend(paths)
    return roots


def _location_specs(config: dict) -> list[tuple[str, str, bool]]:
    source_policy = config.get("source_policy", {}) or {}
    source_cleaner = config.get("source_cleaner", {}) or {}
    source_write = (
        source_policy.get("cleanup_source_after_done") is True
        or source_cleaner.get("enabled") is True
    )
    specs = [
        ("source", config.get("source_dir", ""), source_write),
        ("temp", config.get("temp_dir", ""), True),
        ("recycle", source_policy.get("recycle_dir", "") or source_policy.get("quarantine_dir", ""), True),
    ]
    log_dir = config.get("log_dir", "")
    if log_dir:
        specs.append(("log", log_dir, True))
    specs.extend(("target", root, True) for root in _target_roots(config))
    return specs


def _check_write(path: str) -> tuple[bool, str]:
    try:
        with tempfile.NamedTemporaryFile(dir=path, prefix=".storage_check_", delete=True):
            pass
        return True, ""
    except OSError as exc:
        return False, str(exc)


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
                              reserved_bytes: int = 0) -> dict:
    locations = []
    blocking = []
    warnings = []
    identities = config.get("storage_identities", {}) or {}

    for index, (role, path, need_write) in enumerate(_location_specs(config)):
        location_id = role if role != "target" else f"target:{index}"
        item = {
            "id": location_id,
            "role": role,
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
