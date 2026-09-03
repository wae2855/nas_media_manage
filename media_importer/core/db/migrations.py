import json
import sqlite3

from .constants import _MAPPING_PRESETS, DEFAULT_DIMENSIONS


def _seed_dimensions(conn: sqlite3.Connection):
    """当前事实：直接以 DEFAULT_DIMENSIONS 为最终 schema 初始化 dimensions 表。

    产品未上线，旧维度迁移（region / broad_genre / restricted_level / source_type /
    tmdb_field / provider_mappings）已删除。新库只需按 DEFAULT_DIMENSIONS 写入，
    旧库如已有 dimensions 行则不动，由未来 schema_version 框架处理未来升级。
    """
    for dim in DEFAULT_DIMENSIONS:
        conn.execute(
            """INSERT OR IGNORE INTO dimensions
               (name, label, source_type, sort_order, ai_prompt, tmdb_field,
                provider_mappings, default_provider_mappings, value_list,
                default_value_list, color, is_system,
                is_enabled, trust_ai_assist, trust_ai_search, required_tier, description)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (dim["name"], dim["label"], dim["source_type"], dim["sort_order"],
             dim["ai_prompt"], dim["tmdb_field"], dim["provider_mappings"],
             dim.get("default_provider_mappings", dim["provider_mappings"]),
             dim["value_list"], dim["default_value_list"], dim["color"],
             dim["is_system"], dim["is_enabled"], dim.get("trust_ai_assist", 1),
             dim.get("trust_ai_search", 0), dim["required_tier"], dim["description"])
        )
        _migrate_provider_mapping(conn, dim)
        _migrate_dimension_labels(conn, dim)


def _migrate_provider_mapping(conn: sqlite3.Connection, dimension: dict) -> None:
    """只迁移等于产品旧预置的映射，任何用户自定义值原样保留。"""
    name = dimension["name"]
    current = conn.execute(
        "SELECT provider_mappings, default_provider_mappings FROM dimensions WHERE name=?",
        (name,),
    ).fetchone()
    if current is None:
        return
    new_default = dimension.get("default_provider_mappings", "") or ""
    try:
        previous_default = json.loads(current["default_provider_mappings"] or "{}")
        current_mapping = json.loads(current["provider_mappings"] or "{}")
    except (TypeError, ValueError):
        return
    conn.execute(
        "UPDATE dimensions SET default_provider_mappings=? WHERE name=?",
        (new_default, name),
    )
    # 产品预置升级：仅当前映射仍与升级前的默认副本完全一致时跟随更新。
    # 用户只要改过任意规则或优先级，两者就不相等，当前映射保持原样；
    # “恢复产品预置”仍可从上面更新后的 default_provider_mappings 取到最新版。
    if previous_default and current_mapping == previous_default:
        conn.execute(
            "UPDATE dimensions SET provider_mappings=? WHERE name=?",
            (new_default, name),
        )
        return
    legacy = (
        _MAPPING_PRESETS.get("dimensions", {}).get(name, {}).get("legacy", {})
    )
    if legacy and current_mapping == legacy:
        conn.execute(
            "UPDATE dimensions SET provider_mappings=? WHERE name=?",
            (new_default, name),
        )
    if name == "content_sensitivity" and current_mapping == {
        "tmdb": {
            "schema_version": 2,
            "field": "adult",
            "shape": "boolean",
            "operator": "lookup",
            "rules": [
                {"id": "tmdb-adult-explicit", "inputs": [True], "target": "explicit"}
            ],
            "unmatched": {"action": "review"},
        }
    }:
        conn.execute(
            "UPDATE dimensions SET provider_mappings=? WHERE name=?",
            (new_default, name),
        )
    if name == "content_sensitivity" and current_mapping == {
        "tmdb": {
            "schema_version": 2,
            "field": "adult",
            "shape": "boolean",
            "operator": "lookup",
            "rules": [
                {"id": "tmdb-adult-explicit", "inputs": [True], "target": "adult"}
            ],
            "unmatched": {"action": "review"},
        }
    }:
        conn.execute(
            "UPDATE dimensions SET provider_mappings=? WHERE name=?",
            (new_default, name),
        )


def _migrate_dimension_labels(conn: sqlite3.Connection, dimension: dict) -> None:
    if dimension["name"] == "content_sensitivity":
        row = conn.execute(
            "SELECT label, value_list, ai_prompt, description "
            "FROM dimensions WHERE name='content_sensitivity'"
        ).fetchone()
        if row is not None:
            updates = {"default_value_list": dimension["default_value_list"]}
            if row["label"] == "内容敏感度":
                updates["label"] = dimension["label"]
            if row["ai_prompt"] == (
                "仅根据 Provider 的明确成人标记判断内容敏感度。"
                "没有明确证据时不要猜测，保留为待确认。"
            ):
                updates["ai_prompt"] = dimension["ai_prompt"]
            if row["description"] == "仅在 Provider 有明确证据时标记成人或敏感内容":
                updates["description"] = dimension["description"]
            try:
                values = json.loads(row["value_list"] or "[]")
            except (TypeError, ValueError):
                values = []
            if values in ([
                {"value": "explicit", "label": "明确成人内容"},
                {"value": "unknown", "label": "未确认"},
            ], [
                {"value": "normal", "label": "普通内容"},
                {"value": "restricted", "label": "限制内容"},
                {"value": "adult", "label": "成人内容"},
            ]):
                updates["value_list"] = dimension["value_list"]
            if updates:
                assignments = ", ".join(f"{key}=?" for key in updates)
                conn.execute(
                    f"UPDATE dimensions SET {assignments} "
                    "WHERE name='content_sensitivity'",
                    list(updates.values()),
                )
        return
    if dimension["name"] != "restricted_level":
        return
    row = conn.execute(
        "SELECT label, value_list FROM dimensions WHERE name='restricted_level'"
    ).fetchone()
    if row is None:
        return
    updates = {
        "default_value_list": dimension["default_value_list"],
        "description": dimension["description"],
        "ai_prompt": dimension["ai_prompt"],
    }
    if row["label"] == "限制级分类":
        updates["label"] = "观看分级"
    try:
        values = json.loads(row["value_list"] or "[]")
    except (TypeError, ValueError):
        values = []
    changed = False
    for item in values:
        if item.get("value") == "17+" and item.get("label") == "成人内容":
            item["label"] = "限制观看"
            changed = True
    if changed:
        updates["value_list"] = json.dumps(values, ensure_ascii=False)
    assignments = ", ".join(f"{key}=?" for key in updates)
    conn.execute(
        f"UPDATE dimensions SET {assignments} WHERE name='restricted_level'",
        list(updates.values()),
    )


__all__ = ["_seed_dimensions"]
