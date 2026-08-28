import sqlite3

from .constants import DEFAULT_DIMENSIONS


def _seed_dimensions(conn: sqlite3.Connection):
    """当前事实：直接以 DEFAULT_DIMENSIONS 为最终 schema 初始化 dimensions 表。

    产品未上线，旧维度迁移（region / broad_genre / restricted_level / source_type /
    tmdb_field / provider_mappings）已删除。新库只需按 DEFAULT_DIMENSIONS 写入，
    旧库如已有 dimensions 行则不动，由未来 schema_version 框架处理未来升级。
    """
    cur = conn.execute("SELECT COUNT(*) FROM dimensions")
    if cur.fetchone()[0] > 0:
        return
    for dim in DEFAULT_DIMENSIONS:
        conn.execute(
            """INSERT INTO dimensions
               (name, label, source_type, sort_order, ai_prompt, tmdb_field,
                provider_mappings, value_list, default_value_list, color, is_system,
                is_enabled, trust_ai_assist, trust_ai_search, required_tier, description)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (dim["name"], dim["label"], dim["source_type"], dim["sort_order"],
             dim["ai_prompt"], dim["tmdb_field"], dim["provider_mappings"],
             dim["value_list"], dim["default_value_list"], dim["color"],
             dim["is_system"], dim["is_enabled"], dim.get("trust_ai_assist", 1),
             dim.get("trust_ai_search", 0), dim["required_tier"], dim["description"])
        )


__all__ = ["_seed_dimensions"]
