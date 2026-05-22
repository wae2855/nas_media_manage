#!/usr/bin/env python3
import sqlite3
import os
import json
import threading
from datetime import datetime


_sqlite_conn_lock = threading.RLock()


CREATE_TASKS_TABLE = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT UNIQUE NOT NULL,
    source_path TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    file_size_mb REAL DEFAULT 0,
    status TEXT DEFAULT 'PENDING',
    retry_count INTEGER DEFAULT 0,
    created_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    last_seen_at TEXT,
    current_step INTEGER DEFAULT 0,
    total_steps INTEGER DEFAULT 10,
    step_name TEXT DEFAULT '',
    percentage INTEGER DEFAULT 0,
    bytes_copied INTEGER DEFAULT 0,
    total_bytes INTEGER DEFAULT 0,
    scrape_result TEXT DEFAULT '{}',
    scrape_title_cn TEXT,
    scrape_title_en TEXT,
    scrape_year TEXT,
    scrape_media_type TEXT,
    scrape_season INTEGER,
    scrape_episode INTEGER,
    scrape_dimensions TEXT DEFAULT '{}',
    scrape_confidence REAL DEFAULT 0,
    classify_result TEXT DEFAULT '',
    import_path TEXT DEFAULT '',
    final_filename TEXT DEFAULT '',
    dedup_result TEXT DEFAULT '{}',
    dedup_existing_file TEXT DEFAULT '',
    import_video_path TEXT DEFAULT '',
    import_success INTEGER DEFAULT 0,
    confirm_status TEXT DEFAULT 'NONE',
    confirmed_at TEXT,
    skip_reason TEXT DEFAULT '',
    error_code INTEGER DEFAULT 0,
    error_message TEXT DEFAULT ''
)
"""

CREATE_SUBTITLES_TABLE = """
CREATE TABLE IF NOT EXISTS task_subtitles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    lang TEXT DEFAULT '',
    status TEXT DEFAULT 'PENDING',
    import_path TEXT DEFAULT '',
    confirm_status TEXT DEFAULT 'NONE',
    error_message TEXT DEFAULT '',
    created_at TEXT,
    completed_at TEXT
)
"""

CREATE_TASKS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_tasks_source_path ON tasks(source_path)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at DESC)",
]

CREATE_SUBTITLES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_subtitles_task_id ON task_subtitles(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_subtitles_source_path ON task_subtitles(source_path)",
]

VALID_STATUSES = [
    "PENDING", "PROCESSING", "SUCCESS", "FAILED", "SKIPPED",
    "CONFIRMING", "NEEDS_REVIEW", "ROLLBACK",
]


def init_db(db_path: str) -> sqlite3.Connection:
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(CREATE_TASKS_TABLE)
    conn.execute(CREATE_SUBTITLES_TABLE)
    for idx_sql in CREATE_TASKS_INDEXES:
        conn.execute(idx_sql)
    for idx_sql in CREATE_SUBTITLES_INDEXES:
        conn.execute(idx_sql)
    conn.commit()
    return conn


def _row_to_dict(row) -> dict:
    if row is None:
        return None
    return dict(row)


def _rows_to_dicts(rows) -> list:
    return [dict(r) for r in rows]


def create_task(conn: sqlite3.Connection, source_path: str, source_filename: str,
                file_size_mb: float = 0, task_id: str = None) -> dict:
    import uuid
    tid = task_id or uuid.uuid4().hex[:12]
    now = datetime.now().isoformat()
    with _sqlite_conn_lock:
        conn.execute(
            """INSERT INTO tasks
               (task_id, source_path, source_filename, file_size_mb, status,
                created_at, last_seen_at, total_steps)
               VALUES (?, ?, ?, ?, 'PENDING', ?, ?, 10)""",
            (tid, source_path, source_filename, file_size_mb, now, now)
        )
        conn.commit()
    return get_task(conn, tid)


def get_task(conn: sqlite3.Connection, task_id: str) -> dict:
    cur = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,))
    row = _row_to_dict(cur.fetchone())
    if row and row.get('scrape_result'):
        try:
            row['scrape_result'] = json.loads(row['scrape_result'])
        except (json.JSONDecodeError, TypeError):
            pass
    if row and row.get('scrape_dimensions'):
        try:
            row['scrape_dimensions'] = json.loads(row['scrape_dimensions'])
        except (json.JSONDecodeError, TypeError):
            pass
    if row and row.get('dedup_result'):
        try:
            row['dedup_result'] = json.loads(row['dedup_result'])
        except (json.JSONDecodeError, TypeError):
            pass
    return row


def find_by_source_path(conn: sqlite3.Connection, source_path: str) -> dict:
    cur = conn.execute(
        "SELECT * FROM tasks WHERE source_path=? ORDER BY created_at DESC LIMIT 1",
        (source_path,)
    )
    return _row_to_dict(cur.fetchone())


def find_by_source_filename(conn: sqlite3.Connection, source_filename: str
                            ) -> list:
    cur = conn.execute(
        "SELECT * FROM tasks WHERE source_filename=? ORDER BY created_at DESC",
        (source_filename,)
    )
    return _rows_to_dicts(cur.fetchall())


def list_tasks(conn: sqlite3.Connection, page: int = 1, page_size: int = 20,
               status: str = None) -> tuple:
    offset = (page - 1) * page_size
    conditions = []
    params = []
    if status and status.lower() != "all" and status in VALID_STATUSES:
        conditions.append("status=?")
        params.append(status)
    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    count_sql = "SELECT COUNT(*) FROM tasks" + where_clause
    total = conn.execute(count_sql, params).fetchone()[0]
    data_sql = ("SELECT task_id, source_filename, status, percentage, "
                "scrape_title_cn, scrape_title_en, scrape_year, "
                "scrape_media_type, import_path, final_filename, "
                "skip_reason, error_message, import_success, "
                "confirm_status, created_at, started_at, completed_at "
                "FROM tasks" + where_clause +
                " ORDER BY created_at DESC LIMIT ? OFFSET ?")
    rows = _rows_to_dicts(
        conn.execute(data_sql, params + [page_size, offset]).fetchall()
    )
    total_pages = max(1, (total + page_size - 1) // page_size)
    return rows, total, total_pages


def update_task(conn: sqlite3.Connection, task_id: str, **fields) -> dict:
    valid_columns = {
        "source_path", "source_filename", "file_size_mb", "status",
        "retry_count", "created_at", "started_at", "completed_at",
        "last_seen_at", "current_step", "total_steps", "step_name",
        "percentage", "bytes_copied", "total_bytes",
        "scrape_result", "scrape_title_cn", "scrape_title_en",
        "scrape_year", "scrape_media_type", "scrape_season",
        "scrape_episode", "scrape_dimensions", "scrape_confidence",
        "classify_result", "import_path", "final_filename",
        "dedup_result", "dedup_existing_file", "import_video_path",
        "import_success", "confirm_status", "confirmed_at",
        "skip_reason", "error_code", "error_message",
    }
    update_fields = {}
    for k, v in fields.items():
        if k in valid_columns:
            if k in ("scrape_result", "scrape_dimensions", "dedup_result"):
                if isinstance(v, (dict, list)):
                    update_fields[k] = json.dumps(v, ensure_ascii=False)
                else:
                    update_fields[k] = v
            else:
                update_fields[k] = v
    if not update_fields:
        return get_task(conn, task_id)
    set_clause = ", ".join(f"{k}=?" for k in update_fields)
    params = list(update_fields.values()) + [task_id]
    with _sqlite_conn_lock:
        conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE task_id=?",
            params
        )
        conn.commit()
    return get_task(conn, task_id)


def count_by_status(conn: sqlite3.Connection) -> dict:
    counts = {s: 0 for s in VALID_STATUSES}
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status"
    ).fetchall()
    for row in rows:
        s = row["status"]
        if s in counts:
            counts[s] = row["cnt"]
    return counts


def has_active_tasks(conn: sqlite3.Connection) -> bool:
    cur = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE status IN ('PENDING', 'PROCESSING')"
    )
    return cur.fetchone()[0] > 0


def count_by_specific_status(conn: sqlite3.Connection, status: str) -> int:
    cur = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE status=?", (status,)
    )
    return cur.fetchone()[0]


def find_failed_too_many(conn: sqlite3.Connection, max_retries: int) -> list:
    rows = conn.execute(
        "SELECT * FROM tasks WHERE status='FAILED' AND retry_count>=?",
        (max_retries,)
    ).fetchall()
    return _rows_to_dicts(rows)


def get_next_pending(conn: sqlite3.Connection) -> dict:
    cur = conn.execute(
        "SELECT task_id FROM tasks WHERE status='PENDING' ORDER BY created_at ASC LIMIT 1"
    )
    row = cur.fetchone()
    if row is None:
        return None
    return get_task(conn, row["task_id"])


def list_all_tasks(conn: sqlite3.Connection, limit: int = 500) -> list:
    rows = conn.execute(
        "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return _rows_to_dicts(rows)


def count_all_tasks(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]


def create_subtitles(conn: sqlite3.Connection, task_id: str,
                     subtitle_paths: list) -> list:
    now = datetime.now().isoformat()
    inserted = []
    for sp in subtitle_paths:
        filename = os.path.basename(sp)
        with _sqlite_conn_lock:
            cur = conn.execute(
                """INSERT INTO task_subtitles
                   (task_id, source_path, source_filename, status, created_at)
                   VALUES (?, ?, ?, 'PENDING', ?)""",
                (task_id, sp, filename, now)
            )
            inserted.append({
                "id": cur.lastrowid,
                "task_id": task_id,
                "source_path": sp,
                "source_filename": filename,
                "status": "PENDING",
            })
        conn.commit()
    return inserted


def get_subtitles_by_task(conn: sqlite3.Connection, task_id: str) -> list:
    rows = conn.execute(
        "SELECT * FROM task_subtitles WHERE task_id=? ORDER BY id ASC",
        (task_id,)
    ).fetchall()
    return _rows_to_dicts(rows)


def update_subtitle(conn: sqlite3.Connection, subtitle_id: int, **fields) -> dict:
    valid_columns = {
        "lang", "status", "import_path", "confirm_status",
        "error_message", "completed_at",
    }
    update_fields = {k: v for k, v in fields.items() if k in valid_columns}
    if not update_fields:
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
    }
    update_fields = {k: v for k, v in fields.items() if k in valid_columns}
    if not update_fields:
        return 0
    set_clause = ", ".join(f"{k}=?" for k in update_fields)
    params = list(update_fields.values()) + [task_id]
    with _sqlite_conn_lock:
        conn.execute(
            f"UPDATE task_subtitles SET {set_clause} WHERE task_id=?",
            params
        )
        conn.commit()
    return conn.total_changes


def count_subtitles_by_task(conn: sqlite3.Connection, task_id: str) -> tuple:
    total = conn.execute(
        "SELECT COUNT(*) FROM task_subtitles WHERE task_id=?", (task_id,)
    ).fetchone()[0]
    success = conn.execute(
        "SELECT COUNT(*) FROM task_subtitles WHERE task_id=? AND status='SUCCESS'",
        (task_id,)
    ).fetchone()[0]
    return total, success