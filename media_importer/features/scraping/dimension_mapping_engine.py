"""版本化 Provider 维度映射合同与通用执行器。"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

MAPPING_SCHEMA_VERSION = 2
ALLOWED_SHAPES = {"scalar", "boolean", "set", "ordered_set", "country_value"}
ALLOWED_OPERATORS = {
    "lookup", "contains_any", "first_lookup", "ordered_input_lookup",
    "certification_lookup",
}
_PRESET_PATH = Path(__file__).with_name("data") / "provider_dimension_mappings.v2.json"


class MappingValidationError(ValueError):
    pass


def load_mapping_presets() -> dict:
    payload = json.loads(_PRESET_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != MAPPING_SCHEMA_VERSION:
        raise MappingValidationError("Provider 映射预置版本不受支持")
    return payload


def provider_capabilities(provider_type: str) -> dict:
    provider = load_mapping_presets().get("providers", {}).get(provider_type)
    if not provider:
        raise MappingValidationError(f"Provider 不支持维度映射: {provider_type}")
    return copy.deepcopy(provider)


def default_provider_mappings(dimension_name: str) -> dict:
    item = load_mapping_presets().get("dimensions", {}).get(dimension_name, {})
    return copy.deepcopy(item.get("providers", {}))


def legacy_provider_mappings(dimension_name: str) -> dict:
    item = load_mapping_presets().get("dimensions", {}).get(dimension_name, {})
    return copy.deepcopy(item.get("legacy", {}))


def mapping_content_hash(mapping: dict) -> str:
    canonical = json.dumps(mapping, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_mapping(mapping: dict, allowed_targets: set[str]) -> dict:
    if not isinstance(mapping, dict):
        raise MappingValidationError("映射必须是对象")
    if mapping.get("schema_version") != MAPPING_SCHEMA_VERSION:
        raise MappingValidationError("映射版本必须为 2")
    if mapping.get("shape") not in ALLOWED_SHAPES:
        raise MappingValidationError("Provider 数据形状不受支持")
    if mapping.get("operator") not in ALLOWED_OPERATORS:
        raise MappingValidationError("映射方式不受支持")
    field = mapping.get("field")
    if not isinstance(field, str) or not field.strip():
        raise MappingValidationError("Provider 字段不能为空")
    rules = mapping.get("rules")
    if not isinstance(rules, list):
        raise MappingValidationError("映射规则必须是列表")
    seen_ids = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise MappingValidationError("映射规则格式错误")
        rule_id = str(rule.get("id", "")).strip()
        if not rule_id or rule_id in seen_ids:
            raise MappingValidationError("映射规则 ID 不能为空或重复")
        seen_ids.add(rule_id)
        inputs = rule.get("inputs")
        if not isinstance(inputs, list) or not inputs:
            raise MappingValidationError(f"规则 {rule_id} 缺少 Provider 原始值")
        if rule.get("target") not in allowed_targets:
            raise MappingValidationError(f"规则 {rule_id} 指向了不存在的维度值")
    unmatched = mapping.get("unmatched", {"action": "review"})
    if unmatched.get("action") not in {"review", "value"}:
        raise MappingValidationError("未匹配策略只允许人工确认或指定值")
    if unmatched.get("action") == "value" and unmatched.get("target") not in allowed_targets:
        raise MappingValidationError("未匹配策略指向了不存在的维度值")
    return copy.deepcopy(mapping)


def execute_mapping(
    dimension_name: str,
    mapping: dict,
    provider_data: dict,
    *,
    release_dates: list | None = None,
    allowed_targets: set[str] | None = None,
) -> dict:
    allowed_targets = allowed_targets or {
        str(rule.get("target")) for rule in mapping.get("rules", [])
    }
    validate_mapping(mapping, allowed_targets)
    operator = mapping["operator"]
    field = mapping["field"]
    raw_value = release_dates if field == "release_dates" else provider_data.get(field)
    result = None
    matched_rule = None
    matched_input = None

    if operator == "certification_lookup":
        result, matched_rule, matched_input = _map_certification(mapping, raw_value or [])
    elif raw_value is not None and raw_value != [] and raw_value != "":
        if operator == "ordered_input_lookup":
            result, matched_rule, matched_input = _ordered_input_lookup(mapping, raw_value)
        elif operator == "first_lookup":
            first = raw_value[0] if isinstance(raw_value, list) else raw_value
            result, matched_rule, matched_input = _lookup(mapping, first)
        elif operator == "contains_any":
            result, matched_rule, matched_input = _contains_any(mapping, raw_value)
        else:
            result, matched_rule, matched_input = _lookup(mapping, raw_value)

    if result is None:
        unmatched = mapping.get("unmatched", {"action": "review"})
        if raw_value not in (None, "", []) and unmatched.get("action") == "value":
            result = unmatched.get("target")

    reliability = 0
    if result is not None:
        reliability = 1.0
        if operator == "ordered_input_lookup":
            reliability = 0.9
        if operator == "certification_lookup" and matched_input:
            reliability = 1.0 if matched_input.get("country") == "US" else 0.95
        if matched_rule is None:
            reliability = min(reliability, 0.9)
    return {
        "name": dimension_name,
        "value": result,
        "source_reliability": reliability,
        "mapping_evidence": {
            "mapping_version": mapping["schema_version"],
            "provider_field": field,
            "raw_value": raw_value,
            "rule_id": matched_rule.get("id") if matched_rule else "",
            "matched_input": matched_input,
            "target": result,
        },
    }


def _normalize(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    return str(value).strip().upper()


def _lookup(mapping: dict, raw_value):
    normalized = _normalize(raw_value)
    for rule in mapping["rules"]:
        for candidate in rule["inputs"]:
            if _normalize(candidate) == normalized:
                return rule["target"], rule, raw_value
    return None, None, None


def _contains_any(mapping: dict, raw_values):
    values = raw_values if isinstance(raw_values, list) else [raw_values]
    normalized = {
        _normalize(item.get("id") if isinstance(item, dict) else item)
        for item in values
    }
    for rule in mapping["rules"]:
        for candidate in rule["inputs"]:
            if _normalize(candidate) in normalized:
                return rule["target"], rule, candidate
    return None, None, None


def _ordered_input_lookup(mapping: dict, raw_values):
    values = raw_values if isinstance(raw_values, list) else [raw_values]
    by_input = {}
    for rule in mapping["rules"]:
        for candidate in rule["inputs"]:
            by_input[_normalize(candidate)] = rule
    for item in values:
        raw = item.get("id") if isinstance(item, dict) else item
        rule = by_input.get(_normalize(raw))
        if rule:
            return rule["target"], rule, raw
    return None, None, None


def _map_certification(mapping: dict, release_dates: list):
    priorities = mapping.get("country_priority", [])
    ordered = sorted(
        release_dates,
        key=lambda item: priorities.index(item.get("iso_3166_1"))
        if item.get("iso_3166_1") in priorities else len(priorities),
    )
    for item in ordered:
        country = item.get("iso_3166_1", "")
        certifications = []
        rating = str(item.get("rating", "") or "").strip()
        if rating:
            certifications.append(rating)
        certifications.extend(
            str(value.get("certification", "") or "").strip()
            for value in item.get("release_dates", [])
            if str(value.get("certification", "") or "").strip()
        )
        for certification in certifications:
            target, rule, _matched = _lookup_for_country(
                mapping, certification, country
            )
            if target is not None:
                return target, rule, {"country": country, "certification": certification}
    return None, None, None


def _lookup_for_country(mapping: dict, raw_value, country: str):
    normalized = _normalize(raw_value)
    for rule in mapping["rules"]:
        if rule.get("country") and rule.get("country") != country:
            continue
        for candidate in rule["inputs"]:
            if _normalize(candidate) == normalized:
                return rule["target"], rule, raw_value
    return None, None, None
