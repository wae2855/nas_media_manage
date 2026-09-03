import os
import sqlite3
import uuid
from datetime import datetime
from typing import Optional

from media_importer.infrastructure.filesystem import hash_file

from .connection import _row_to_dict, _rows_to_dicts, _sqlite_conn_lock


def create_subtitles(conn: sqlite3.Connection, task_id: str,
                     subtitle_paths: list, target_paths: Optional[list] = None) -> list:
    now = datetime.now().isoformat()
    inserted = []
    tpaths = target_paths or []
    with _sqlite_conn_lock:
        for i, sp in enumerate(subtitle_paths):
            filename = os.path.basename(sp)
            tp = tpaths[i] if i < len(tpaths) else ""
            member_id = uuid.uuid4().hex
            try:
                source_stat = os.stat(sp, follow_symlinks=False)
                source_size = source_stat.st_size
                source_mtime_ns = source_stat.st_mtime_ns
                source_fingerprint = hash_file(sp)
            except OSError:
                source_size = 0
                source_mtime_ns = 0
                source_fingerprint = ""
            cur = conn.execute(
                """INSERT INTO task_subtitles
                   (task_id, source_path, source_filename, member_id,
                    source_size, source_mtime_ns, source_fingerprint,
                    target_path, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)""",
                (
                    task_id, sp, filename, member_id, source_size,
                    source_mtime_ns, source_fingerprint, tp, now,
                )
            )
            inserted.append({
                "id": cur.lastrowid,
                "task_id": task_id,
                "source_path": sp,
                "source_filename": filename,
                "member_id": member_id,
                "source_size": source_size,
                "source_mtime_ns": source_mtime_ns,
                "source_fingerprint": source_fingerprint,
                "target_path": tp,
                "status": "PENDING",
            })
        conn.commit()
    return inserted


def get_subtitles_by_task(conn: sqlite3.Connection, task_id: str) -> list:
    with _sqlite_conn_lock:
        rows = conn.execute(
            "SELECT * FROM task_subtitles WHERE task_id=? ORDER BY id ASC",
            (task_id,)
        ).fetchall()
        return _rows_to_dicts(rows)


def update_subtitle(conn: sqlite3.Connection, subtitle_id: int, **fields) -> Optional[dict]:
    valid_columns = {
        "lang", "status", "import_path", "confirm_status",
        "error_message", "completed_at", "target_path", "source_path",
        "planned_filename", "source_size", "source_mtime_ns",
        "source_fingerprint", "member_id",
    }
    update_fields = {k: v for k, v in fields.items() if k in valid_columns}
    if not update_fields:
        with _sqlite_conn_lock:
            cur = conn.execute(
                "SELECT * FROM task_subtitles WHERE id=?", (subtitle_id,)
            )
            return _row_to_dict(cur.fetchone())
    set_clause = ", ".join(f"{k}=?" for k in update_fields)
    params = list(update_fields.values()) + [subtitle_id]
    with _sqlite_conn_lock:
        conn.execute(
            f"UPDATE task_subtitles SET {set_clause} WHERE id=?",
            params
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM task_subtitles WHERE id=?", (subtitle_id,)
        )
        return _row_to_dict(cur.fetchone())


def update_subtitles_by_task(conn: sqlite3.Connection, task_id: str,
                              **fields) -> int:
    valid_columns = {
        "status", "import_path", "confirm_status", "completed_at",
        "target_path",
    }
    update_fields = {k: v for k, v in fields.items() if k in valid_columns}
    if not update_fields:
        return 0
    set_clause = ", ".join(f"{k}=?" for k in update_fields)
    params = list(update_fields.values()) + [task_id]
    with _sqlite_conn_lock:
        cur = conn.execute(
            f"UPDATE task_subtitles SET {set_clause} WHERE task_id=?",
            params
        )
        conn.commit()
        return max(cur.rowcount, 0)


def count_subtitles_by_task(conn: sqlite3.Connection, task_id: str) -> tuple:
    with _sqlite_conn_lock:
        total = conn.execute(
            "SELECT COUNT(*) FROM task_subtitles WHERE task_id=?", (task_id,)
        ).fetchone()[0]
        success = conn.execute(
            "SELECT COUNT(*) FROM task_subtitles "
            "WHERE task_id=? AND status='SUCCESS'",
            (task_id,)
        ).fetchone()[0]
        return total, success
