"""片库根目录与相对规则的唯一边界。"""

from __future__ import annotations

import copy
import os
import re


class LibraryPathError(ValueError):
    pass


def _static_parent(template: str) -> str:
    prefix = template.split("{", 1)[0].rstrip(os.sep)
    return prefix


def canonicalize_library_config(config: dict) -> dict:
    """复制并归一化配置；无法证明同属一个安全根目录时拒绝迁移。"""
    result = copy.deepcopy(config or {})
    root = str(result.get("library_root", "") or "").strip()
    rules = result.get("path_rules", []) or []
    fallback = str(result.get("fallback_dir", "") or "").strip()
    absolute_values = [
        str(rule.get("template", "")) for rule in rules
        if isinstance(rule, dict) and os.path.isabs(str(rule.get("template", "")))
    ]
    if fallback and os.path.isabs(fallback):
        absolute_values.append(fallback)

    if not root and absolute_values:
        anchors = [_static_parent(value) for value in absolute_values]
        anchors = [value for value in anchors if value]
        try:
            common = os.path.commonpath(anchors)
        except ValueError as exc:
            raise LibraryPathError("旧规则没有可确认的共同的入库根目录") from exc
        volume_root = os.path.abspath(common).anchor if hasattr(os.path.abspath(common), "anchor") else os.sep
        if not common or common in {os.sep, volume_root}:
            raise LibraryPathError("旧规则没有可确认的共同的入库根目录")
        # 两个不同一级卷即使 commonpath 为 / 也必须拒绝；普通目录则可安全收敛。
        if common == os.path.dirname(common):
            raise LibraryPathError("旧规则没有可确认的共同的入库根目录")
        root = common
        result["library_root"] = root

    if root:
        root = os.path.realpath(os.path.abspath(root))
        result["library_root"] = root
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            template = str(rule.get("template", "") or "")
            if os.path.isabs(template):
                rule["template"] = _relative_under_root(root, template)
            elif template:
                _validate_relative(template)
        if fallback:
            result["fallback_dir"] = (
                _relative_under_root(root, fallback) if os.path.isabs(fallback)
                else _validate_relative(fallback)
            )
    return result


def _validate_relative(path: str) -> str:
    if os.path.isabs(path):
        raise LibraryPathError("入库子目录必须是相对路径")
    normalized = os.path.normpath(path)
    if normalized == ".." or normalized.startswith(".." + os.sep):
        raise LibraryPathError("入库子目录不能超出片库根目录")
    return path


def _relative_under_root(root: str, path: str) -> str:
    candidate = os.path.realpath(os.path.abspath(path))
    try:
        if os.path.commonpath([root, candidate]) != root:
            raise LibraryPathError("入库规则不在共同的入库根目录下")
    except ValueError as exc:
        raise LibraryPathError("入库规则不在共同的入库根目录下") from exc
    return os.path.relpath(candidate, root)


def resolve_library_template(library_root: str, template: str, values: dict) -> str:
    if not library_root:
        raise LibraryPathError("片库根目录未配置")
    _validate_relative(template)
    for value in (values or {}).values():
        if isinstance(value, str) and (
            value in {".", ".."} or ".." in value
            or os.sep in value or (os.altsep and os.altsep in value)
        ):
            raise LibraryPathError("入库变量包含不安全的路径片段")
    rendered = re.sub(
        r"\{([^:}]+)(?::[^}]+)?\}",
        lambda match: str((values or {}).get(match.group(1), "")),
        template,
    ).rstrip("/")
    _validate_relative(rendered)
    root = os.path.realpath(os.path.abspath(library_root))
    candidate = os.path.realpath(os.path.join(root, rendered))
    try:
        if os.path.commonpath([root, candidate]) != root:
            raise LibraryPathError("渲染后的入库路径超出片库根目录")
    except ValueError as exc:
        raise LibraryPathError("渲染后的入库路径超出片库根目录") from exc
    return candidate
