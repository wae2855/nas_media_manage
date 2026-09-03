"""Canonical directory-role topology used by config and file side effects."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DirectoryRoot:
    role: str
    label: str
    path: str
    realpath: str


@dataclass(frozen=True)
class DirectoryConflict:
    first: DirectoryRoot
    second: DirectoryRoot

    @property
    def message(self) -> str:
        return (
            f"{self.first.label}与{self.second.label}不能使用相同目录或互相包含："
            f"{self.first.path}；{self.second.path}"
        )


def canonical_path(path: str) -> str:
    value = str(path or "").strip()
    if not value:
        return ""
    return os.path.realpath(os.path.abspath(value))


def _configured_library_specs(config: dict) -> list[tuple[str, str]]:
    roots = config.get("library_roots") if isinstance(config, dict) else None
    if isinstance(roots, list) and roots:
        return [
            (
                str(item.get("name", "") or f"片库 {index + 1}"),
                str(item.get("path", "") or "").strip(),
            )
            for index, item in enumerate(roots)
            if isinstance(item, dict)
            and str(item.get("path", "") or "").strip()
        ]
    legacy = str((config or {}).get("library_root", "") or "").strip()
    return [("默认片库", legacy)] if legacy else []


def configured_library_roots(config: dict) -> list[str]:
    return [path for _name, path in _configured_library_specs(config)]


def directory_roots(config: dict) -> list[DirectoryRoot]:
    config = config or {}
    policy = config.get("source_policy", {}) or {}
    raw: list[tuple[str, str, str]] = [
        ("source", "文件来源", str(config.get("source_dir", "") or "")),
        (
            "recycle",
            "本地回收",
            str(policy.get("recycle_dir", "") or policy.get("quarantine_dir", "") or ""),
        ),
        ("log", "运行日志", str(config.get("log_dir", "") or "")),
        (
            "resource",
            "海报与缓存",
            str(config.get("resource_dir", "") or config.get("resources_dir", "") or ""),
        ),
    ]
    for index, (name, path) in enumerate(_configured_library_specs(config)):
        label = f"目标片库「{name}」"
        raw.append((f"target:{index}", label, path))

    result = []
    for role, label, path in raw:
        value = path.strip()
        if not value:
            continue
        result.append(DirectoryRoot(role, label, value, canonical_path(value)))
    return result


def paths_overlap(first: str, second: str) -> bool:
    first_real = canonical_path(first)
    second_real = canonical_path(second)
    if not first_real or not second_real:
        return False
    try:
        common = os.path.commonpath([first_real, second_real])
    except ValueError:
        return False
    return common in {first_real, second_real}


def path_within(path: str, root: str, *, allow_root: bool = True) -> bool:
    path_real = canonical_path(path)
    root_real = canonical_path(root)
    if not path_real or not root_real:
        return False
    try:
        within = os.path.commonpath([path_real, root_real]) == root_real
    except ValueError:
        return False
    return within and (allow_root or path_real != root_real)


def path_in_library(config: dict, path: str) -> bool:
    return any(path_within(path, root) for root in configured_library_roots(config))


def validate_directory_topology(config: dict) -> list[DirectoryConflict]:
    roots = directory_roots(config)
    conflicts = []
    for index, first in enumerate(roots):
        for second in roots[index + 1:]:
            if paths_overlap(first.realpath, second.realpath):
                conflicts.append(DirectoryConflict(first, second))
    return conflicts


def topology_error_messages(config: dict) -> list[str]:
    return [conflict.message for conflict in validate_directory_topology(config)]
