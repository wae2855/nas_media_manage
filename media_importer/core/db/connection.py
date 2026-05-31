import sqlite3
import os
import logging
import threading

from .constants import (
    CREATE_TASKS_TABLE,
    CREATE_SUBTITLES_TABLE,
    CREATE_DIMENSIONS_TABLE,
    CREATE_TASKS_INDEXES,
    CREATE_SUBTITLES_INDEXES,
    DEFAULT_DIMENSIONS,
)


logger = logging.getLogger(__name__)
_sqlite_conn_lock = threading.RLock()


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
    conn.execute(CREATE_DIMENSIONS_TABLE)
    _migrate_schema(conn)
    for idx_sql in CREATE_TASKS_INDEXES:
        conn.execute(idx_sql)
    for idx_sql in CREATE_SUBTITLES_INDEXES:
        conn.execute(idx_sql)
    from .dimension_repo import _seed_dimensions
    _seed_dimensions(conn)
    from .cleaner_repo import init_cleaner_tables
    init_cleaner_tables(conn)
    conn.commit()
    return conn


def _migrate_schema(conn: sqlite3.Connection):
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "tasks" in tables:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        if "video_path" not in existing:
            conn.execute("ALTER TABLE tasks ADD COLUMN video_path TEXT DEFAULT ''")
        if "file_location" not in existing:
            conn.execute("ALTER TABLE tasks ADD COLUMN file_location TEXT DEFAULT 'source'")
            conn.execute("UPDATE tasks SET file_location='import' WHERE status='SUCCESS' AND import_success=1")
            conn.execute("UPDATE tasks SET file_location='deleted' WHERE status='SKIPPED'")
            conn.execute("UPDATE tasks SET file_location='recycle' WHERE status='NEEDS_REVIEW'")
            conn.execute("UPDATE tasks SET file_location='temp' WHERE status='CONFIRMING'")
        else:
            source_count = conn.execute("SELECT COUNT(*) FROM tasks WHERE file_location='source' AND status='SUCCESS' AND import_success=1").fetchone()[0]
            if source_count > 0:
                conn.execute("UPDATE tasks SET file_location='import' WHERE file_location='source' AND status='SUCCESS' AND import_success=1")
                conn.execute("UPDATE tasks SET file_location='deleted' WHERE file_location='source' AND status='SKIPPED'")
                conn.execute("UPDATE tasks SET file_location='recycle' WHERE file_location='source' AND status='NEEDS_REVIEW'")
                conn.execute("UPDATE tasks SET file_location='temp' WHERE file_location='source' AND status='CONFIRMING'")
        if "import_video_path" not in existing:
            conn.execute("ALTER TABLE tasks ADD COLUMN import_video_path TEXT DEFAULT ''")
        if "scrape_trace" not in existing:
            conn.execute("ALTER TABLE tasks ADD COLUMN scrape_trace TEXT DEFAULT ''")
        if "provider_type" not in existing:
            conn.execute("ALTER TABLE tasks ADD COLUMN provider_type TEXT DEFAULT ''")
        if "provider_id" not in existing:
            conn.execute("ALTER TABLE tasks ADD COLUMN provider_id TEXT DEFAULT ''")
        if "source_fingerprint" not in existing:
            conn.execute("ALTER TABLE tasks ADD COLUMN source_fingerprint TEXT DEFAULT ''")
        if "source_file_size" not in existing:
            conn.execute("ALTER TABLE tasks ADD COLUMN source_file_size INTEGER DEFAULT 0")
        if "source_mtime" not in existing:
            conn.execute("ALTER TABLE tasks ADD COLUMN source_mtime TEXT DEFAULT ''")
        conn.execute("UPDATE tasks SET status='FAILED' WHERE status IN ('NEEDS_REVIEW', 'ROLLBACK')")
        conn.execute("UPDATE tasks SET status='SKIPPED' WHERE status='DUPLICATE_REVIEW'")
        conn.execute("UPDATE tasks SET file_location='recycle' WHERE file_location='source' AND status='FAILED' AND import_success=0")
        conn.execute("UPDATE tasks SET file_location='recycle' WHERE file_location='source' AND status='SKIPPED'")
    if "dimensions" in tables:
        dim_existing = {row[1] for row in conn.execute("PRAGMA table_info(dimensions)").fetchall()}
        if "default_value_list" not in dim_existing:
            conn.execute("ALTER TABLE dimensions ADD COLUMN default_value_list TEXT DEFAULT ''")
            for d in DEFAULT_DIMENSIONS:
                name = d['name']
                existing_row = conn.execute(
                    "SELECT default_value_list FROM dimensions WHERE name=?", (name,)
                ).fetchone()
                if existing_row and (not existing_row[0] or existing_row[0] == ''):
                    conn.execute(
                        "UPDATE dimensions SET default_value_list=? WHERE name=?",
                        (d['default_value_list'], name)
                    )
    if "task_subtitles" in tables:
        sub_existing = {row[1] for row in conn.execute("PRAGMA table_info(task_subtitles)").fetchall()}
        if "target_path" not in sub_existing:
            conn.execute("ALTER TABLE task_subtitles ADD COLUMN target_path TEXT DEFAULT ''")


def _row_to_dict(row) -> dict:
    if row is None:
        return None
    return dict(row)


def _rows_to_dicts(rows) -> list:
    return [dict(r) for r in rows]
