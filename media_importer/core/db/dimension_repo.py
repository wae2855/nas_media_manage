import sqlite3
import json

from .connection import _sqlite_conn_lock, logger
from .constants import DEFAULT_DIMENSIONS


def _seed_dimensions(conn: sqlite3.Connection):
    cur = conn.execute("SELECT COUNT(*) FROM dimensions")
    if cur.fetchone()[0] > 0:
        _migrate_dimensions(conn)
        return
    for dim in DEFAULT_DIMENSIONS:
        conn.execute(
            """INSERT INTO dimensions
               (name, label, source_type, sort_order, ai_prompt, tmdb_field,
                provider_mappings, value_list, default_value_list, color, is_system,
                is_enabled, required_tier, description)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (dim["name"], dim["label"], dim["source_type"], dim["sort_order"],
             dim["ai_prompt"], dim["tmdb_field"], dim["provider_mappings"],
             dim["value_list"], dim["default_value_list"], dim["color"],
             dim["is_system"], dim["is_enabled"], dim["required_tier"],
             dim["description"])
        )


def _migrate_dimensions(conn: sqlite3.Connection):
    _migrate_region(conn)
    _migrate_broad_genre(conn)
    _migrate_restricted_level(conn)
    _migrate_source_type(conn)
    _migrate_tmdb_field(conn)
    _migrate_provider_mappings(conn)


def _migrate_region(conn):
    row = conn.execute(
        "SELECT value_list FROM dimensions WHERE name='region'"
    ).fetchone()
    if not row:
        return

    try:
        vl = json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return

    if not vl or not isinstance(vl, list):
        return

    first_value = vl[0].get('value', '') if vl else ''
    if first_value in ('asia', 'western', 'european'):
        new_data = None
        for d in DEFAULT_DIMENSIONS:
            if d['name'] == 'region':
                new_data = d
                break
        if new_data:
            conn.execute(
                "UPDATE dimensions SET value_list=?, ai_prompt=?, description=? WHERE name='region'",
                (new_data['value_list'], new_data['ai_prompt'], new_data['description'])
            )
            conn.commit()
            logger.info("已迁移 region 维度数据：大类分组 → 具体国家")


def _migrate_broad_genre(conn):
    row = conn.execute(
        "SELECT value_list FROM dimensions WHERE name='broad_genre'"
    ).fetchone()
    if not row:
        return

    try:
        vl = json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return

    if not vl or not isinstance(vl, list):
        return

    old_keys = {'horror', 'scifi', 'action', 'drama'}
    needs_migrate = any(v.get('value') in old_keys for v in vl)

    if not needs_migrate:
        needs_migrate = _cleanup_invalid_genre_ids(vl)

    if not needs_migrate:
        return

    new_data = None
    for d in DEFAULT_DIMENSIONS:
        if d['name'] == 'broad_genre':
            new_data = d
            break
    if new_data:
        conn.execute(
            "UPDATE dimensions SET value_list=?, ai_prompt=?, description=?, default_value_list=? WHERE name='broad_genre'",
            (new_data['value_list'], new_data['ai_prompt'], new_data['description'], new_data['default_value_list'])
        )
        conn.commit()
        logger.info("已迁移 broad_genre 维度数据：更新分类映射")


def _cleanup_invalid_genre_ids(value_list):
    INVALID_GENRE_IDS = {10761}
    changed = False
    for item in value_list:
        ids = item.get('tmdb_genre_ids', [])
        cleaned = [gid for gid in ids if gid not in INVALID_GENRE_IDS]
        if len(cleaned) != len(ids):
            item['tmdb_genre_ids'] = cleaned
            changed = True
    return changed


def _migrate_restricted_level(conn):
    row = conn.execute(
        "SELECT value_list, default_value_list FROM dimensions WHERE name='restricted_level'"
    ).fetchone()
    if not row:
        return

    needs_update = False
    new_value_list = row[0]
    new_default_value_list = row[1]

    for idx, raw in enumerate([new_value_list, new_default_value_list]):
        try:
            vl = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not vl or not isinstance(vl, list):
            continue
        has_old = any(v.get('value') == '13-15' for v in vl)
        if has_old:
            for v in vl:
                if v.get('value') == '13-15':
                    v['value'] = '13-16'
            needs_update = True
            if idx == 0:
                new_value_list = json.dumps(vl, ensure_ascii=False)
            else:
                new_default_value_list = json.dumps(vl, ensure_ascii=False)

    if not needs_update:
        return

    new_data = None
    for d in DEFAULT_DIMENSIONS:
        if d['name'] == 'restricted_level':
            new_data = d
            break

    if new_data:
        conn.execute(
            "UPDATE dimensions SET value_list=?, default_value_list=?, ai_prompt=? WHERE name='restricted_level'",
            (new_value_list, new_default_value_list, new_data['ai_prompt'])
        )
        conn.commit()
        logger.info("已迁移 restricted_level 维度数据：13-15 → 13-16")


def _migrate_source_type(conn):
    rows = conn.execute(
        "SELECT name, source_type FROM dimensions WHERE source_type IN ('tmdb', 'tmdb_ai')"
    ).fetchall()
    if not rows:
        return

    for row in rows:
        conn.execute(
            "UPDATE dimensions SET source_type='ai+tmdb' WHERE name=?",
            (row[0],)
        )
    conn.commit()
    logger.info(f"已迁移 {len(rows)} 个维度 source_type: tmdb/tmdb_ai → ai+tmdb")


def _migrate_tmdb_field(conn):
    updates = {
        'documentary': {'source_type': 'ai+tmdb', 'tmdb_field': 'genres'},
        'restricted_level': {'source_type': 'ai+tmdb', 'tmdb_field': 'release_dates'},
        'animation': {'source_type': 'ai+tmdb', 'tmdb_field': 'genres'},
    }

    for name, new_vals in updates.items():
        row = conn.execute(
            "SELECT source_type, tmdb_field FROM dimensions WHERE name=?", (name,)
        ).fetchone()
        if not row:
            continue

        current_type, current_field = row
        needs_update = False
        set_clauses = []
        params = []

        for key, val in new_vals.items():
            if key == 'source_type' and current_type != val:
                needs_update = True
                set_clauses.append("source_type=?")
                params.append(val)
            elif key == 'tmdb_field' and current_field != val:
                needs_update = True
                set_clauses.append("tmdb_field=?")
                params.append(val)

        if needs_update:
            conn.execute(
                f"UPDATE dimensions SET {','.join(set_clauses)} WHERE name=?",
                params + [name]
            )
            logger.info(f"已迁移维度 {name}: source_type={current_type}→{new_vals['source_type']}, tmdb_field={current_field}→{new_vals['tmdb_field']}")

    conn.commit()


def _migrate_provider_mappings(conn: sqlite3.Connection):
    cols = [row[1] for row in conn.execute("PRAGMA table_info(dimensions)").fetchall()]
    if 'provider_mappings' not in cols:
        conn.execute("ALTER TABLE dimensions ADD COLUMN provider_mappings TEXT DEFAULT ''")
        conn.commit()
        logger.info("已添加 provider_mappings 列到 dimensions 表")

    rows = conn.execute(
        "SELECT name, tmdb_field, value_list FROM dimensions WHERE source_type='ai+tmdb'"
    ).fetchall()

    if not rows:
        return

    for row in rows:
        name, tmdb_field, value_list_json = row
        provider_mappings = _build_provider_mappings(tmdb_field, value_list_json)
        conn.execute(
            "UPDATE dimensions SET source_type='ai+provider', provider_mappings=? WHERE name=?",
            (provider_mappings, name)
        )

    conn.commit()
    logger.info(f"已迁移 {len(rows)} 个维度: source_type ai+tmdb → ai+provider, 构建 provider_mappings")


def _build_provider_mappings(tmdb_field, value_list_json):
    if not tmdb_field:
        return ""

    try:
        vl = json.loads(value_list_json)
    except (json.JSONDecodeError, TypeError):
        return ""

    if not vl or not isinstance(vl, list):
        return ""

    if tmdb_field == "genres":
        has_genre_ids = any(item.get('tmdb_genre_ids') for item in vl)
        if not has_genre_ids:
            return ""

        values = [item.get('value') for item in vl]
        is_boolean = len(vl) == 2 and 'true' in values and 'false' in values

        if is_boolean:
            true_item = next((item for item in vl if item.get('value') == 'true'), None)
            if true_item and true_item.get('tmdb_genre_ids'):
                return json.dumps({
                    "tmdb": {
                        "field": "genres",
                        "match_type": "genre_ids",
                        "match_rules": {
                            "true": {"ids": true_item['tmdb_genre_ids']}
                        }
                    }
                }, ensure_ascii=False)
        else:
            match_rules = {}
            for item in vl:
                rule = {"ids": item.get('tmdb_genre_ids', [])}
                if 'priority' in item:
                    rule['priority'] = item['priority']
                match_rules[item['value']] = rule
            return json.dumps({
                "tmdb": {
                    "field": "genres",
                    "match_type": "genre_ids",
                    "match_rules": match_rules
                }
            }, ensure_ascii=False)

    elif tmdb_field == "release_dates":
        return json.dumps({
            "tmdb": {
                "field": "release_dates",
                "match_type": "certification"
            }
        }, ensure_ascii=False)

    elif tmdb_field == "origin_country":
        codes = {}
        for item in vl:
            if item.get('tmdb_codes'):
                codes[item['value']] = item['tmdb_codes']
        return json.dumps({
            "tmdb": {
                "field": "origin_country",
                "match_type": "country_codes",
                "codes": codes
            }
        }, ensure_ascii=False)

    elif tmdb_field == "original_language":
        return json.dumps({
            "tmdb": {
                "field": "original_language",
                "match_type": "direct_match"
            }
        }, ensure_ascii=False)

    return ""


def get_all_dimensions(conn: sqlite3.Connection) -> list:
    rows = conn.execute(
        "SELECT * FROM dimensions ORDER BY sort_order ASC"
    ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        if d.get('value_list'):
            try:
                d['value_list'] = json.loads(d['value_list'])
            except (json.JSONDecodeError, TypeError):
                d['value_list'] = []
        result.append(d)
    return result


def get_enabled_dimensions(conn: sqlite3.Connection) -> list:
    rows = conn.execute(
        "SELECT * FROM dimensions WHERE is_enabled=1 ORDER BY sort_order ASC"
    ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        if d.get('value_list'):
            try:
                d['value_list'] = json.loads(d['value_list'])
            except (json.JSONDecodeError, TypeError):
                d['value_list'] = []
        result.append(d)
    return result


def get_dimension(conn: sqlite3.Connection, name: str) -> dict:
    cur = conn.execute("SELECT * FROM dimensions WHERE name=?", (name,))
    row = cur.fetchone()
    if row is None:
        return None
    d = dict(row)
    if d.get('value_list'):
        try:
            d['value_list'] = json.loads(d['value_list'])
        except (json.JSONDecodeError, TypeError):
            d['value_list'] = []
    return d


def update_dimension(conn: sqlite3.Connection, name: str, **fields) -> dict:
    valid_columns = {
        "label", "ai_prompt", "tmdb_field", "provider_mappings", "value_list",
        "color", "description",
    }
    update_fields = {}
    for k, v in fields.items():
        if k in valid_columns:
            if k == "value_list" and isinstance(v, (dict, list)):
                update_fields[k] = json.dumps(v, ensure_ascii=False)
            else:
                update_fields[k] = v
    if not update_fields:
        return get_dimension(conn, name)
    set_clause = ", ".join(f"{k}=?" for k in update_fields)
    params = list(update_fields.values()) + [name]
    with _sqlite_conn_lock:
        conn.execute(f"UPDATE dimensions SET {set_clause} WHERE name=?", params)
        conn.commit()
    return get_dimension(conn, name)


def enable_dimension(conn: sqlite3.Connection, name: str) -> dict:
    with _sqlite_conn_lock:
        conn.execute("UPDATE dimensions SET is_enabled=1 WHERE name=?", (name,))
        conn.commit()
    return get_dimension(conn, name)


def disable_dimension(conn: sqlite3.Connection, name: str) -> dict:
    with _sqlite_conn_lock:
        conn.execute("UPDATE dimensions SET is_enabled=0 WHERE name=?", (name,))
        conn.commit()
    return get_dimension(conn, name)


def reset_dimension(conn: sqlite3.Connection, name: str) -> dict:
    row = conn.execute(
        "SELECT default_value_list, ai_prompt, description FROM dimensions WHERE name=?",
        (name,)
    ).fetchone()
    if row is None:
        return None
    default_vl = row['default_value_list']
    if not default_vl or default_vl.strip() == '':
        for d in DEFAULT_DIMENSIONS:
            if d['name'] == name:
                default_vl = d.get('value_list', '[]')
                break
    if not default_vl or default_vl.strip() == '':
        return None
    with _sqlite_conn_lock:
        conn.execute(
            "UPDATE dimensions SET value_list=?, ai_prompt=?, description=? WHERE name=?",
            (default_vl, row['ai_prompt'] or '', row['description'] or '', name)
        )
        conn.commit()
    return get_dimension(conn, name)
