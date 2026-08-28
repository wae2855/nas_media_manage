import json
import sqlite3
from typing import Optional

from .connection import _sqlite_conn_lock
from .constants import DEFAULT_DIMENSIONS


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


def get_dimension(conn: sqlite3.Connection, name: str) -> Optional[dict]:
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


def update_dimension(conn: sqlite3.Connection, name: str, **fields) -> Optional[dict]:
    valid_columns = {
        "label", "ai_prompt", "tmdb_field", "provider_mappings", "value_list",
        "trust_ai_assist", "trust_ai_search", "color", "description",
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


def enable_dimension(conn: sqlite3.Connection, name: str) -> Optional[dict]:
    with _sqlite_conn_lock:
        conn.execute("UPDATE dimensions SET is_enabled=1 WHERE name=?", (name,))
        conn.commit()
    return get_dimension(conn, name)


def disable_dimension(conn: sqlite3.Connection, name: str) -> Optional[dict]:
    with _sqlite_conn_lock:
        conn.execute("UPDATE dimensions SET is_enabled=0 WHERE name=?", (name,))
        conn.commit()
    return get_dimension(conn, name)


def reset_dimension(conn: sqlite3.Connection, name: str) -> Optional[dict]:
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
