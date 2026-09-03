"""片库根目录与相对规则的唯一边界。"""

from __future__ import annotations

import copy
import os
import re

ROOT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class LibraryPathError(ValueError):
    pass


def _static_parent(template: str) -> str:
    prefix = template.split("{", 1)[0].rstrip(os.sep)
    return prefix


def _legacy_rule_purpose(rule: dict, index: int) -> str:
    name = str(rule.get("name", "") or "").strip()
    if name:
        return name
    conditions = rule.get("conditions")
    if not isinstance(conditions, dict) or not conditions:
        return "默认入库规则"
    parts = []
    if str(conditions.get("documentary", "")).lower() == "yes":
        parts.append("纪录片")
    if str(conditions.get("restricted", "")).lower() == "yes":
        parts.append("限制级")
    media_type = str(conditions.get("media_type", "") or "").lower()
    if media_type == "movie":
        parts.append("电影")
    elif media_type == "tv":
        parts.append("电视剧")
    return "".join(parts) + "规则" if parts else f"规则 {index + 1}"


def migrate_legacy_library_rules(config: dict, roots: list[dict],
                                 default_id: str = "") -> dict:
    """Migrate legacy rules only after every rule explicitly selected a root."""
    result = copy.deepcopy(config or {})
    result["library_roots"] = roots
    result["default_library_root_id"] = default_id
    result["library_root"] = ""
    if not roots:
        raise LibraryPathError("请先选择至少一个目标片库，再确认旧规则迁移")
    return canonicalize_library_config(result, require_rule_assignments=True)


def canonicalize_library_config(config: dict, *, require_rule_assignments: bool = False) -> dict:
    """复制并归一化多片库配置；无法证明安全边界时拒绝迁移。"""
    result = copy.deepcopy(config or {})
    root = str(result.get("library_root", "") or "").strip()
    roots = result.get("library_roots")
    rules = result.get("path_rules", []) or []
    fallback = str(result.get("fallback_dir", "") or "").strip()
    absolute_values = [
        str(rule.get("template", "")) for rule in rules
        if isinstance(rule, dict) and os.path.isabs(str(rule.get("template", "")))
    ]
    if fallback and os.path.isabs(fallback):
        absolute_values.append(fallback)

    if not root and roots in (None, []) and absolute_values:
        raise LibraryPathError("检测到旧版绝对入库规则，请在存储检查中选择片库根目录并确认迁移")

    if roots is None:
        roots = []
        if root:
            roots.append({"id": "default", "name": "主片库", "path": root, "enabled": True})
    if not isinstance(roots, list):
        raise LibraryPathError("片库根目录列表格式无效")

    canonical_roots = []
    ids = set()
    paths = set()
    for index, item in enumerate(roots):
        if not isinstance(item, dict):
            raise LibraryPathError(f"第 {index + 1} 个片库根目录格式无效")
        root_id = str(item.get("id", "") or "").strip()
        if not ROOT_ID_PATTERN.fullmatch(root_id):
            raise LibraryPathError("片库 ID 只能使用小写字母、数字、下划线和短横线")
        if root_id in ids:
            raise LibraryPathError(f"片库 ID 重复: {root_id}")
        path = str(item.get("path", "") or "").strip()
        if not path or not os.path.isabs(path):
            raise LibraryPathError(f"片库“{item.get('name') or root_id}”必须配置绝对路径")
        path = os.path.realpath(os.path.abspath(path))
        if path in paths:
            raise LibraryPathError(f"片库路径重复: {path}")
        ids.add(root_id)
        paths.add(path)
        canonical_roots.append({
            "id": root_id,
            "name": str(item.get("name", "") or "").strip() or f"片库 {index + 1}",
            "path": path,
            "enabled": item.get("enabled", True) is not False,
        })

    result["library_roots"] = canonical_roots
    default_id = str(result.get("default_library_root_id", "") or "").strip()
    if canonical_roots:
        if not default_id:
            default_id = canonical_roots[0]["id"]
        if default_id not in ids:
            raise LibraryPathError("默认片库不存在")
        result["default_library_root_id"] = default_id
        # 兼容只读取 library_root 的旧调用；新保存事实源是 library_roots。
        default_root = next(item for item in canonical_roots if item["id"] == default_id)
        if default_root["enabled"] is False:
            raise LibraryPathError("默认片库不能停用")
        result["library_root"] = default_root["path"]

        root_by_id = {item["id"]: item["path"] for item in canonical_roots}
        enabled_by_id = {item["id"]: item["enabled"] for item in canonical_roots}
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict):
                continue
            purpose = _legacy_rule_purpose(rule, index)
            rule_id = str(rule.get("library_root_id", "") or "").strip()
            template = str(rule.get("template", "") or "")
            if not rule_id:
                if require_rule_assignments:
                    raise LibraryPathError(
                        f"第 {index + 1} 条规则“{purpose}”尚未选择目标片库"
                    )
                if template and not os.path.isabs(template):
                    _validate_relative(template)
                rule.pop("library_root_id", None)
                continue
            if rule_id not in root_by_id:
                raise LibraryPathError(
                    f"第 {index + 1} 条规则“{purpose}”引用了不存在的片库: {rule_id}"
                )
            if enabled_by_id[rule_id] is False:
                raise LibraryPathError(
                    f"第 {index + 1} 条规则“{purpose}”引用了已停用的片库: {rule_id}"
                )
            rule["library_root_id"] = rule_id
            if os.path.isabs(template):
                try:
                    rule["template"] = _relative_under_root(root_by_id[rule_id], template)
                except LibraryPathError as exc:
                    raise LibraryPathError(
                        f"第 {index + 1} 条规则“{purpose}”的旧路径不在所选片库内: "
                        f"{_static_parent(template) or template}"
                    ) from exc
            elif template:
                _validate_relative(template)
        if fallback:
            fallback_id = str(result.get("fallback_library_root_id", "") or "").strip()
            if not fallback_id:
                if require_rule_assignments:
                    raise LibraryPathError("兜底入库目录尚未选择目标片库")
                result.pop("fallback_library_root_id", None)
            else:
                if fallback_id not in root_by_id:
                    raise LibraryPathError(f"兜底目录引用了不存在的片库: {fallback_id}")
                if enabled_by_id[fallback_id] is False:
                    raise LibraryPathError(f"兜底目录引用了已停用的片库: {fallback_id}")
                result["fallback_library_root_id"] = fallback_id
                result["fallback_dir"] = (
                    _relative_under_root(root_by_id[fallback_id], fallback)
                    if os.path.isabs(fallback) else _validate_relative(fallback)
                )
        identities = result.get("storage_identities")
        if isinstance(identities, dict):
            legacy_targets = [
                value for key, value in identities.items()
                if str(key).startswith("target:") and key != f"target:{default_id}"
            ]
            if f"target:{default_id}" not in identities and len(canonical_roots) == 1 and len(legacy_targets) == 1:
                identities[f"target:{default_id}"] = legacy_targets[0]
    elif root:
        result["library_roots"] = [{
            "id": "default", "name": "主片库", "path": root, "enabled": True,
        }]
        result["default_library_root_id"] = "default"
        return canonicalize_library_config(
            result, require_rule_assignments=require_rule_assignments
        )
    elif require_rule_assignments and (rules or fallback):
        raise LibraryPathError("请先添加至少一个目标片库")
    return result


def library_roots(config: dict) -> list[dict]:
    """返回已规范化的片库根，兼容旧单根输入。"""
    return canonicalize_library_config(config).get("library_roots", [])


def library_root_by_id(config: dict, root_id: str | None = None) -> dict:
    canonical = canonicalize_library_config(config)
    selected_id = root_id or canonical.get("default_library_root_id", "")
    for root in canonical.get("library_roots", []):
        if root.get("id") == selected_id:
            if root.get("enabled") is False:
                raise LibraryPathError(f"片库已停用: {selected_id}")
            return root
    raise LibraryPathError(f"片库不存在: {selected_id or '未配置'}")


def resolve_rule_template(config: dict, rule: dict | None, template: str, values: dict,
                          *, fallback: bool = False) -> str:
    if fallback:
        root_id = str((config or {}).get("fallback_library_root_id", "") or "").strip()
    else:
        root_id = str((rule or {}).get("library_root_id", "") or "").strip()
    if not root_id:
        raise LibraryPathError("入库规则尚未选择目标片库")
    roots = (config or {}).get("library_roots") or []
    root = next(
        (
            item for item in roots
            if isinstance(item, dict) and str(item.get("id", "")) == root_id
        ),
        None,
    )
    if not root:
        raise LibraryPathError(f"片库不存在: {root_id}")
    if root.get("enabled", True) is False:
        raise LibraryPathError(f"片库已停用: {root_id}")
    root_path = str(root.get("path", "") or "").strip()
    if not root_path or not os.path.isabs(root_path):
        raise LibraryPathError(f"片库路径无效: {root_id}")
    return resolve_library_template(root_path, template, values)


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
