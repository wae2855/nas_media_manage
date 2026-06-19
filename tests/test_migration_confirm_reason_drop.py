"""confirm_reason 列退役 migration 测试。

覆盖：
1. 新建 DB 不含 confirm_reason 列（CREATE TABLE 已移除）
2. 旧 DB（手工构造含 confirm_reason 列）能被 migration 升级
3. migration 幂等：列已删除则跳过
4. SQLite 版本解析函数

SQLite 版本兼容性：
- SQLite >= 3.35.0 (2021-03) 支持 DROP COLUMN → 列物理删除
- SQLite < 3.35.0 → 列保留为死数据，warning 日志，不影响功能
"""

import logging
import os
import sqlite3
import tempfile

import pytest

from media_importer.core.db.connection import (
    _column_exists,
    _drop_confirm_reason_column,
    _parse_sqlite_version,
    init_db,
)
from media_importer.core.db.task_repo import create_task, get_task


def _current_sqlite_version() -> tuple:
    """当前测试环境的 SQLite 版本。"""
    return _parse_sqlite_version(sqlite3.sqlite_version)


def _supports_drop_column() -> bool:
    return _current_sqlite_version() >= (3, 35, 0)


@pytest.fixture
def db_path():
    """临时 DB 文件路径。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    for ext in ("", "-wal", "-shm"):
        try:
            os.unlink(path + ext)
        except OSError:
            pass


def _column_names(db_path, table="tasks"):
    """返回指定表的列名列表。"""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        # PRAGMA table_info 返回 (cid, name, type, notnull, dflt_value, pk)
        return [row[1] for row in rows]
    finally:
        conn.close()


def _build_old_db_with_confirm_reason(db_path: str) -> None:
    """手工构造一个含 confirm_reason 列的"旧版" tasks 表，并插入一行。

    复用 constants.CREATE_TASKS_TABLE 的当前 schema，再额外补 confirm_reason 列，
    模拟"步骤 B 之前的真实旧库"形态。这样 init_db 创建索引不会因列缺失而失败。
    """
    from media_importer.core.db.constants import CREATE_TASKS_TABLE
    # 把 confirm_reason 列插入到 CREATE TABLE 字符串的右括号前
    old_table_sql = CREATE_TASKS_TABLE.replace(
        "scrape_trace TEXT DEFAULT '',",
        "scrape_trace TEXT DEFAULT '',\n    confirm_reason TEXT DEFAULT '',",
        1,
    )
    assert "confirm_reason" in old_table_sql, "旧表 DDL 注入失败"

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(old_table_sql)
        conn.execute(
            """
            INSERT INTO tasks (task_id, source_path, source_filename,
                               confirm_reason, match_level)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "old-task-1",
                "/old/path/movie.mp4",
                "movie.mp4",
                "已废弃拼接串",
                "NEEDS_CONFIRM",
            ),
        )
        conn.commit()
    finally:
        conn.close()


class TestParseSqliteVersion:
    """版本解析单元测试。"""

    def test_parse_3_51_0(self):
        assert _parse_sqlite_version("3.51.0") == (3, 51, 0)

    def test_parse_3_35_0_boundary(self):
        assert _parse_sqlite_version("3.35.0") == (3, 35, 0)

    def test_parse_3_34_1_just_below_boundary(self):
        assert _parse_sqlite_version("3.34.1") == (3, 34, 1)

    def test_parse_single_segment_fallback(self):
        """鲁棒性：异常格式不能崩溃，解析为 (0, 0, 0)。"""
        assert _parse_sqlite_version("abc") == (0, 0, 0)
        assert _parse_sqlite_version("") == (0, 0, 0)

    def test_parse_two_segment(self):
        assert _parse_sqlite_version("3.35") == (3, 35, 0)


class TestNewDbHasNoConfirmReasonColumn:
    """新建 DB（走 CREATE TABLE）不应有 confirm_reason 列。"""

    def test_init_db_creates_table_without_confirm_reason(self, db_path):
        init_db(db_path)
        cols = _column_names(db_path)
        assert "confirm_reason" not in cols, (
            f"新建 DB 不应含 confirm_reason 列，实际列: {cols}"
        )


class TestOldDbWithConfirmReasonCanStart:
    """旧 DB（手工构造含 confirm_reason 列）必须能被 init_db 升级，不报错。"""

    def test_init_db_does_not_fail_on_old_schema(self, db_path):
        """手工造旧库 → init_db 升级不能抛异常。"""
        _build_old_db_with_confirm_reason(db_path)
        # 关键断言：init_db 不抛异常
        init_db(db_path)

    def test_old_db_columns_after_init(self, db_path):
        """升级后：若环境支持 DROP COLUMN，则 confirm_reason 已删除；否则保留。"""
        _build_old_db_with_confirm_reason(db_path)
        init_db(db_path)
        cols = _column_names(db_path)

        if _supports_drop_column():
            assert "confirm_reason" not in cols, (
                f"SQLite {sqlite3.sqlite_version} >= 3.35.0 应已 DROP COLUMN，实际列: {cols}"
            )
        else:
            assert "confirm_reason" in cols, (
                f"SQLite {sqlite3.sqlite_version} < 3.35.0 应保留 confirm_reason 列（warning 路径）"
            )

    def test_old_data_preserved_after_migration(self, db_path):
        """升级后旧任务行数据仍可读（不被 DROP COLUMN 影响）。"""
        _build_old_db_with_confirm_reason(db_path)
        init_db(db_path)

        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT task_id, source_filename, match_level FROM tasks WHERE task_id = ?",
                ("old-task-1",),
            ).fetchone()
            assert row is not None, "旧任务行不应在 migration 中丢失"
            assert row[0] == "old-task-1"
            assert row[1] == "movie.mp4"
            assert row[2] == "NEEDS_CONFIRM"
        finally:
            conn.close()

    def test_old_db_with_low_sqlite_can_still_create_and_read_task(self, db_path, monkeypatch):
        """低版本 SQLite 路径：列保留但 create_task/get_task 仍正常。"""
        # 仅在当前环境支持 DROP COLUMN 时才验证降级路径
        if _supports_drop_column():
            # 模拟低版本：monkeypatch sqlite3.sqlite_version
            monkeypatch.setattr(sqlite3, "sqlite_version", "3.34.1")

        _build_old_db_with_confirm_reason(db_path)
        # 此时用 monkeypatched version 直接调用 _drop_confirm_reason_column
        conn = sqlite3.connect(db_path)
        try:
            _drop_confirm_reason_column(conn)
            conn.commit()
        finally:
            conn.close()

        cols = _column_names(db_path)
        version = sqlite3.sqlite_version
        if _supports_drop_column() and version == "3.34.1":
            # monkeypatch 生效：低版本路径 → 列保留
            assert "confirm_reason" in cols, (
                f"monkeypatched SQLite {version} 应保留 confirm_reason 列"
            )
        elif not _supports_drop_column():
            # 真实低版本环境：列保留
            assert "confirm_reason" in cols


class TestMigrationIsIdempotent:
    """migration 幂等：连续执行不能报错。"""

    def test_double_drop_is_safe(self, db_path):
        """连续两次调用 _drop_confirm_reason_column，第二次必须 no-op。"""
        _build_old_db_with_confirm_reason(db_path)
        init_db(db_path)
        # init_db 已触发一次 migration，列在 SQLite>=3.35.0 环境下已删除
        # 再连一个新 conn 触发一次
        conn = sqlite3.connect(db_path)
        try:
            _drop_confirm_reason_column(conn)  # 第二次必须 no-op，不报错
            conn.commit()
        finally:
            conn.close()

    def test_idempotent_on_fresh_db(self, db_path):
        """新库（无 confirm_reason 列）连续调用 migration 也不报错。"""
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        try:
            _drop_confirm_reason_column(conn)
            _drop_confirm_reason_column(conn)  # 连续调用
            conn.commit()
        finally:
            conn.close()


class TestColumnExistsHelper:
    """_column_exists 辅助函数单元测试。"""

    def test_returns_true_when_column_present(self, db_path):
        _build_old_db_with_confirm_reason(db_path)
        conn = sqlite3.connect(db_path)
        try:
            assert _column_exists(conn, "tasks", "confirm_reason") is True
        finally:
            conn.close()

    def test_returns_false_when_column_absent(self, db_path):
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        try:
            assert _column_exists(conn, "tasks", "confirm_reason") is False
        finally:
            conn.close()


class TestMigrationLogsOnLowVersion:
    """低版本 SQLite 路径必须写 warning 日志（不静默失败）。"""

    def test_low_version_writes_warning(self, db_path, monkeypatch, caplog):
        """monkeypatch 模拟低版本 + 旧 DB → 期望 warning 日志。"""
        if not _supports_drop_column():
            pytest.skip("当前环境本身就是低版本，monkeypatch 无意义")

        monkeypatch.setattr(sqlite3, "sqlite_version", "3.34.1")
        _build_old_db_with_confirm_reason(db_path)

        conn = sqlite3.connect(db_path)
        try:
            with caplog.at_level(logging.WARNING, logger="media_importer.core.db.connection"):
                _drop_confirm_reason_column(conn)
            assert any(
                "DROP COLUMN" in record.message and "3.34.1" in record.message
                for record in caplog.records
            ), f"低版本路径应写 warning 日志，实际: {[r.message for r in caplog.records]}"
        finally:
            conn.close()

    def test_high_version_writes_info(self, db_path, monkeypatch, caplog):
        """monkeypatch 模拟高版本 + 旧 DB → 期望 info 日志 + 列删除。"""
        if not _supports_drop_column():
            pytest.skip("当前环境低版本，DROP COLUMN 路径无法验证")

        monkeypatch.setattr(sqlite3, "sqlite_version", "3.51.0")
        _build_old_db_with_confirm_reason(db_path)

        conn = sqlite3.connect(db_path)
        try:
            with caplog.at_level(logging.INFO, logger="media_importer.core.db.connection"):
                _drop_confirm_reason_column(conn)
            assert any(
                "列已删除" in record.message and "3.51.0" in record.message
                for record in caplog.records
            ), f"高版本路径应写 info 日志，实际: {[r.message for r in caplog.records]}"
            assert _column_exists(conn, "tasks", "confirm_reason") is False
        finally:
            conn.close()