import json
import sqlite3
from datetime import datetime

from .connection import _row_to_dict, _sqlite_conn_lock


def upsert_source_unit(conn: sqlite3.Connection, *, unit_id: str, source_root: str,
                       unit_path: str, kind: str, snapshot: list) -> dict:
    now = datetime.now().isoformat()
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    with _sqlite_conn_lock:
        conn.execute(
            """INSERT INTO source_units
               (unit_id, source_root, unit_path, kind, snapshot_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(unit_id) DO UPDATE SET
                 source_root=excluded.source_root,
                 unit_path=excluded.unit_path,
                 kind=excluded.kind,
                 updated_at=excluded.updated_at""",
            (unit_id, source_root, unit_path, kind, snapshot_json, now, now),
        )
        conn.commit()
    return get_source_unit(conn, unit_id)


def get_source_unit(conn: sqlite3.Connection, unit_id: str) -> dict | None:
    with _sqlite_conn_lock:
        row = _row_to_dict(conn.execute(
            "SELECT * FROM source_units WHERE unit_id=?", (unit_id,)
        ).fetchone())
    if row:
        row["snapshot"] = json.loads(row.pop("snapshot_json") or "[]")
    return row


def update_source_unit(conn: sqlite3.Connection, unit_id: str, **fields) -> dict | None:
    allowed = {"state", "cleanup_status", "last_error", "snapshot_json", "updated_at"}
    values = {key: value for key, value in fields.items() if key in allowed}
    values["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{key}=?" for key in values)
    with _sqlite_conn_lock:
        conn.execute(
            f"UPDATE source_units SET {set_clause} WHERE unit_id=?",
            [*values.values(), unit_id],
        )
        conn.commit()
    return get_source_unit(conn, unit_id)


def list_tasks_for_source_unit(conn: sqlite3.Connection, unit_id: str) -> list[dict]:
    with _sqlite_conn_lock:
        rows = conn.execute(
            "SELECT task_id, source_path, status, stage, import_success FROM tasks WHERE source_unit_id=?",
            (unit_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_pending_source_unit_ids(conn: sqlite3.Connection) -> list[str]:
    with _sqlite_conn_lock:
        rows = conn.execute(
            "SELECT unit_id FROM source_units "
            "WHERE state IN ('WAITING', 'BLOCKED', 'RECYCLING', 'DELETING')"
        ).fetchall()
    return [str(row[0]) for row in rows]
