import json
from dataclasses import dataclass, field

from media_importer.infrastructure.db import (
    disable_dimension as db_disable_dimension,
)
from media_importer.infrastructure.db import (
    enable_dimension as db_enable_dimension,
)
from media_importer.infrastructure.db import (
    get_all_dimensions as db_get_all_dimensions,
)
from media_importer.infrastructure.db import (
    get_dimension as db_get_dimension,
)
from media_importer.infrastructure.db import (
    get_enabled_dimensions as db_get_enabled_dimensions,
)
from media_importer.infrastructure.db import (
    reset_dimension as db_reset_dimension,
)
from media_importer.infrastructure.db import (
    update_dimension as db_update_dimension,
)

from .dimension_manager import check_tier_access
from .dimension_mapping_engine import (
    MappingValidationError,
    execute_mapping,
    mapping_content_hash,
    validate_mapping,
)


@dataclass
class DimensionActionResult:
    code: int
    data: dict = field(default_factory=dict)
    message: str = ""


def list_dimensions(conn) -> list:
    return db_get_all_dimensions(conn)


def list_enabled_dimensions(conn) -> list:
    return db_get_enabled_dimensions(conn)


def get_dimension_detail(conn, name: str) -> DimensionActionResult:
    dimension = db_get_dimension(conn, name)
    if dimension is None:
        return DimensionActionResult(code=404, message=f"维度不存在: {name}")
    return DimensionActionResult(code=200, data=dimension or {})


def get_dimension_mapping_detail(
    conn, name: str, provider_type: str
) -> DimensionActionResult:
    dimension = db_get_dimension(conn, name)
    if dimension is None:
        return DimensionActionResult(code=404, message=f"维度不存在: {name}")
    mappings = _mapping_dict(dimension.get("provider_mappings"))
    mapping = mappings.get(provider_type)
    if not isinstance(mapping, dict):
        return DimensionActionResult(
            code=404,
            message=f"{dimension.get('label', name)} 尚未配置 {provider_type} 映射",
        )
    return DimensionActionResult(
        code=200,
        data={
            "dimension": name,
            "label": dimension.get("label", name),
            "provider": provider_type,
            "mapping": mapping,
            "content_hash": mapping_content_hash(mapping),
            "summary": _mapping_summary(mapping),
            "values": dimension.get("value_list", []),
        },
    )


def update_dimension_mapping_detail(
    conn, name: str, provider_type: str, body: dict
) -> DimensionActionResult:
    current = get_dimension_mapping_detail(conn, name, provider_type)
    if current.code != 200:
        return current
    expected_hash = str(body.get("expected_hash", "") or "")
    if not expected_hash:
        return DimensionActionResult(code=400, message="保存映射前缺少版本校验信息")
    if expected_hash != current.data["content_hash"]:
        return DimensionActionResult(
            code=409,
            data=current.data,
            message="映射已在其他页面被修改，请刷新后再保存",
        )
    mapping = body.get("mapping")
    allowed_targets = {
        str(item.get("value"))
        for item in current.data.get("values", [])
        if item.get("value") is not None
    }
    try:
        validated = validate_mapping(mapping, allowed_targets)
    except MappingValidationError as exc:
        return DimensionActionResult(code=400, message=f"映射未保存：{exc}")
    dimension = db_get_dimension(conn, name) or {}
    mappings = _mapping_dict(dimension.get("provider_mappings"))
    mappings[provider_type] = validated
    updated = db_update_dimension(conn, name, provider_mappings=mappings)
    saved = get_dimension_mapping_detail(conn, name, provider_type)
    return DimensionActionResult(
        code=200,
        data=saved.data if saved.code == 200 else (updated or {}),
        message="Provider 映射已保存",
    )


def preview_dimension_mapping(
    conn, name: str, provider_type: str, body: dict
) -> DimensionActionResult:
    current = get_dimension_mapping_detail(conn, name, provider_type)
    if current.code != 200:
        return current
    mapping = body.get("mapping") or current.data["mapping"]
    allowed_targets = {
        str(item.get("value"))
        for item in current.data.get("values", [])
        if item.get("value") is not None
    }
    try:
        result = execute_mapping(
            name,
            mapping,
            body.get("provider_data") or {},
            release_dates=body.get("release_dates") or [],
            allowed_targets=allowed_targets,
        )
    except MappingValidationError as exc:
        return DimensionActionResult(code=400, message=f"无法预览：{exc}")
    return DimensionActionResult(code=200, data=result, message="映射预览完成")


def _mapping_dict(value) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


def _mapping_summary(mapping: dict) -> dict:
    unmatched = mapping.get("unmatched", {"action": "review"})
    return {
        "field": mapping.get("field", ""),
        "shape": mapping.get("shape", ""),
        "operator": mapping.get("operator", ""),
        "rule_count": len(mapping.get("rules", [])),
        "unmatched_action": unmatched.get("action", "review"),
        "unmatched_target": unmatched.get("target", ""),
        "schema_version": mapping.get("schema_version"),
    }


def update_dimension_detail(
    conn, name: str, body: dict, *, config: dict | None = None
) -> DimensionActionResult:
    dimension = db_get_dimension(conn, name)
    if dimension is None:
        return DimensionActionResult(code=404, message=f"维度不存在: {name}")

    if "value_list" in body:
        try:
            old_values = {
                str(item.get("value"))
                for item in (dimension.get("value_list") or [])
                if isinstance(item, dict) and item.get("value") is not None
            }
            candidate_values = body.get("value_list")
            if isinstance(candidate_values, str):
                candidate_values = json.loads(candidate_values)
            new_values = {
                str(item.get("value"))
                for item in (candidate_values or [])
                if isinstance(item, dict) and item.get("value") is not None
            }
        except (TypeError, ValueError):
            return DimensionActionResult(code=400, message="维度值格式错误")
        removed = old_values - new_values
        if removed:
            references = _removed_value_references(
                conn, name, removed, dimension, config or {}
            )
            if references:
                return DimensionActionResult(
                    code=409,
                    message=(
                        "这些维度值仍在使用，不能删除："
                        + "；".join(references[:3])
                    ),
                )

    allowed = {
        key: body[key]
        for key in ("label", "ai_prompt", "tmdb_field", "value_list", "color", "description")
        if key in body
    }
    if not allowed:
        return DimensionActionResult(code=400, message="无有效更新字段")

    updated = db_update_dimension(conn, name, **allowed)
    return DimensionActionResult(code=200, data=updated or {}, message="维度配置已更新")


def _removed_value_references(
    conn, name: str, removed: set[str], dimension: dict, config: dict
) -> list[str]:
    references = []
    mappings = _mapping_dict(dimension.get("provider_mappings"))
    for provider_type, mapping in mappings.items():
        if not isinstance(mapping, dict):
            continue
        targets = {
            str(rule.get("target"))
            for rule in mapping.get("rules", [])
            if isinstance(rule, dict)
        }
        unmatched = mapping.get("unmatched", {})
        if unmatched.get("action") == "value":
            targets.add(str(unmatched.get("target")))
        hits = sorted(removed & targets)
        if hits:
            references.append(f"{provider_type.upper()} 映射仍指向 {', '.join(hits)}")
    for index, rule in enumerate(config.get("path_rules", []) or []):
        if not isinstance(rule, dict):
            continue
        raw = str((rule.get("conditions", {}) or {}).get(name, "") or "")
        hits = sorted(removed & set(raw.split("|")))
        if hits:
            references.append(
                f"入库规则「{rule.get('name') or f'第 {index + 1} 条'}」仍使用 {', '.join(hits)}"
            )
    try:
        from media_importer.infrastructure.db import list_all_tasks

        for task in list_all_tasks(conn, limit=500):
            if task.get("status") in {"SUCCESS", "SKIPPED", "CANCELLED"}:
                continue
            raw_dimensions = task.get("scrape_dimensions") or {}
            if isinstance(raw_dimensions, str):
                raw_dimensions = json.loads(raw_dimensions or "{}")
            raw = str(raw_dimensions.get(name, "") or "")
            if removed & set(raw.split("|")):
                references.append("尚未完成的任务仍在使用该值")
                break
    except (TypeError, ValueError):
        references.append("无法安全确认活动任务的维度值引用")
    return references


def enable_dimension_detail(conn, name: str) -> DimensionActionResult:
    dimension = db_get_dimension(conn, name)
    if dimension is None:
        return DimensionActionResult(code=404, message=f"维度不存在: {name}")

    required_tier = dimension.get("required_tier", "free")
    if required_tier != "free" and not check_tier_access(required_tier):
        return DimensionActionResult(code=403, message=f"该维度需要 {required_tier.upper()} 许可")

    updated = db_enable_dimension(conn, name)
    return DimensionActionResult(
        code=200,
        data=updated or {},
        message=f"维度 {dimension.get('label', name)} 已启用",
    )


def disable_dimension_detail(conn, name: str) -> DimensionActionResult:
    dimension = db_get_dimension(conn, name)
    if dimension is None:
        return DimensionActionResult(code=404, message=f"维度不存在: {name}")

    updated = db_disable_dimension(conn, name)
    return DimensionActionResult(
        code=200,
        data=updated or {},
        message=f"维度 {dimension.get('label', name)} 已禁用",
    )


def reset_dimension_detail(conn, name: str) -> DimensionActionResult:
    dimension = db_get_dimension(conn, name)
    if dimension is None:
        return DimensionActionResult(code=404, message=f"维度不存在: {name}")

    updated = db_reset_dimension(conn, name)
    if updated is None:
        return DimensionActionResult(code=500, message="恢复默认失败: 缺少默认配置")

    return DimensionActionResult(
        code=200,
        data=updated or {},
        message=f"维度 {dimension.get('label', name)} 已恢复默认配置",
    )
