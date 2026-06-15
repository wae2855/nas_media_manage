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
    from .migrations import _seed_dimensions
    _seed_dimensions(conn)
    from .cleaner_repo import init_cleaner_tables
    init_cleaner_tables(conn)
    conn.commit()
    return conn


def _migrate_schema(conn: sqlite3.Connection):
    """DB schema 初始化：当前事实直接以最终 schema 创建表，无需 v1/v2 阶段迁移。

    产品未上线：CREATE_*_TABLE 已是最终 schema，不存在旧库升级。
    保留 schema_version 框架以便未来升级，但当前不再插入任何历史阶段记录。
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version "
        "(version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )


def _row_to_dict(row) -> dict:
    if row is None:
        return None
    return dict(row)


def _rows_to_dicts(rows) -> list:
    return [dict(r) for r in rows]
