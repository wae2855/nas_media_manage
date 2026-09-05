import logging
import os
import sqlite3
import threading
from typing import Optional

from .constants import (
    CREATE_DIMENSIONS_TABLE,
    CREATE_RECYCLE_ITEMS_INDEXES,
    CREATE_RECYCLE_ITEMS_TABLE,
    CREATE_SOURCE_UNITS_INDEXES,
    CREATE_SOURCE_UNITS_TABLE,
    CREATE_SUBTITLES_INDEXES,
    CREATE_SUBTITLES_TABLE,
    CREATE_TASKS_INDEXES,
    CREATE_TASKS_TABLE,
)

logger = logging.getLogger(__name__)
_sqlite_conn_lock = threading.RLock()


def init_db(db_path: str) -> sqlite3.Connection:
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    # ThreadingHTTPServer shares this connection across request threads. Repository
    # calls are serialized with _sqlite_conn_lock; disabling sqlite3's per-connection
    # statement cache also prevents concurrent cache corruption at the C boundary.
    conn = sqlite3.connect(
        db_path,
        check_same_thread=False,
        cached_statements=0,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(CREATE_TASKS_TABLE)
    conn.execute(CREATE_SUBTITLES_TABLE)
    conn.execute(CREATE_DIMENSIONS_TABLE)
    conn.execute(CREATE_RECYCLE_ITEMS_TABLE)
    conn.execute(CREATE_SOURCE_UNITS_TABLE)
    _migrate_schema(conn)
    for idx_sql in CREATE_TASKS_INDEXES:
        conn.execute(idx_sql)
    for idx_sql in CREATE_SUBTITLES_INDEXES:
        conn.execute(idx_sql)
    for idx_sql in CREATE_RECYCLE_ITEMS_INDEXES:
        conn.execute(idx_sql)
    for idx_sql in CREATE_SOURCE_UNITS_INDEXES:
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
    # 2026-06-16: 确认流程重构 — 记录是否换过元数据
    for col_ddl in [
        "ALTER TABLE tasks ADD COLUMN confirmed_override INTEGER DEFAULT 0",
        "ALTER TABLE tasks ADD COLUMN confirmed_title TEXT DEFAULT ''",
        "ALTER TABLE tasks ADD COLUMN override_source TEXT DEFAULT ''",
        "ALTER TABLE tasks ADD COLUMN source_unit_id TEXT DEFAULT ''",
        "ALTER TABLE tasks ADD COLUMN source_cleanup_status TEXT DEFAULT ''",
        "ALTER TABLE tasks ADD COLUMN bundle_state TEXT DEFAULT ''",
        "ALTER TABLE tasks ADD COLUMN bundle_manifest TEXT DEFAULT '[]'",
        "ALTER TABLE tasks ADD COLUMN bundle_committed INTEGER DEFAULT 0",
        "ALTER TABLE tasks ADD COLUMN progress_item_name TEXT DEFAULT ''",
        "ALTER TABLE tasks ADD COLUMN progress_item_kind TEXT DEFAULT ''",
        "ALTER TABLE tasks ADD COLUMN progress_item_index INTEGER DEFAULT 0",
        "ALTER TABLE tasks ADD COLUMN progress_item_total INTEGER DEFAULT 0",
        "ALTER TABLE tasks ADD COLUMN task_kind TEXT DEFAULT 'IMPORT'",
        "ALTER TABLE tasks ADD COLUMN parent_task_id TEXT DEFAULT ''",
        "ALTER TABLE tasks ADD COLUMN used_fallback INTEGER DEFAULT 0",
        "ALTER TABLE tasks ADD COLUMN organization_status TEXT DEFAULT ''",
        "ALTER TABLE tasks ADD COLUMN reorganized_by_task_id TEXT DEFAULT ''",
        "ALTER TABLE tasks ADD COLUMN reorganization_intent TEXT DEFAULT '{}'",
        "ALTER TABLE tasks ADD COLUMN cancel_requested INTEGER DEFAULT 0",
        "ALTER TABLE tasks ADD COLUMN stop_requested_at TEXT DEFAULT ''",
        "ALTER TABLE tasks ADD COLUMN requested_source_disposition TEXT DEFAULT ''",
        "ALTER TABLE tasks ADD COLUMN outcome_code TEXT DEFAULT ''",
        "ALTER TABLE tasks ADD COLUMN source_disposition TEXT DEFAULT ''",
        "ALTER TABLE tasks ADD COLUMN source_disposition_message TEXT DEFAULT ''",
        "ALTER TABLE tasks ADD COLUMN manual_provider_binding TEXT DEFAULT '{}'",
        "ALTER TABLE task_subtitles ADD COLUMN member_id TEXT DEFAULT ''",
        "ALTER TABLE task_subtitles ADD COLUMN source_size INTEGER DEFAULT 0",
        "ALTER TABLE task_subtitles ADD COLUMN source_mtime_ns INTEGER DEFAULT 0",
        "ALTER TABLE task_subtitles ADD COLUMN source_fingerprint TEXT DEFAULT ''",
        "ALTER TABLE task_subtitles ADD COLUMN planned_filename TEXT DEFAULT ''",
    ]:
        try:
            conn.execute(col_ddl)
        except sqlite3.OperationalError:
            pass  # 列已存在（新库通过 CREATE TABLE 创建，旧库通过 ALTER 补上）
    # 2026-06-19: confirm_reason 万能胶字段退役 — DROP COLUMN
    _drop_confirm_reason_column(conn)
    # 2026-08-22: 维度默认值（ADR-0010 B 方案）— 映射不到时的兜底默认值
    if not _column_exists(conn, "dimensions", "default_value"):
        conn.execute(
            "ALTER TABLE dimensions ADD COLUMN default_value TEXT DEFAULT ''"
        )
    if not _column_exists(conn, "dimensions", "default_provider_mappings"):
        conn.execute(
            "ALTER TABLE dimensions ADD COLUMN default_provider_mappings TEXT DEFAULT ''"
        )
    # 2026-08-23: source_type 收敛（ADR-0010）：ai/ai+provider → provider
    conn.execute(
        "UPDATE dimensions SET source_type='provider' "
        "WHERE source_type IN ('ai', 'ai+provider', 'ai+tmdb')"
    )


def _parse_sqlite_version(version_str: str) -> tuple:
    """解析 SQLite 版本字符串为 (major, minor, patch) 元组。

    例：
    - "3.51.0" -> (3, 51, 0)
    - "3.34.1" -> (3, 34, 1)
    - "3.35.0" -> (3, 35, 0)
    """
    parts = version_str.split(".")
    major = int(parts[0]) if len(parts) >= 1 and parts[0].isdigit() else 0
    minor = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
    patch = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0
    return (major, minor, patch)


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """用 PRAGMA table_info 检查表中列是否存在。"""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    for row in rows:
        # PRAGMA table_info 返回 (cid, name, type, notnull, dflt_value, pk)
        if row[1] == column:
            return True
    return False


def _drop_confirm_reason_column(conn: sqlite3.Connection) -> None:
    """退役 confirm_reason 列：SQLite >= 3.35.0 DROP COLUMN，否则保留并 warning。

    幂等：列已不存在则跳过。
    """
    if not _column_exists(conn, "tasks", "confirm_reason"):
        return  # 已是最终 schema，跳过

    version_str = sqlite3.sqlite_version
    version_tuple = _parse_sqlite_version(version_str)

    if version_tuple >= (3, 35, 0):
        conn.execute("ALTER TABLE tasks DROP COLUMN confirm_reason")
        logger.info(
            "confirm_reason 列已删除（SQLite %s）", version_str
        )
    else:
        logger.warning(
            "SQLite %s 不支持 DROP COLUMN，confirm_reason 列保留为死数据，不影响功能",
            version_str,
        )


def _row_to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    return dict(row)


def _rows_to_dicts(rows) -> list:
    return [dict(r) for r in rows]
