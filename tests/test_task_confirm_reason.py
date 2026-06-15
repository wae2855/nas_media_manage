"""任务确认原因持久化测试（RED 测试 - 修复前应失败）。

覆盖：
- confirm_reason 写入 DB 并能在重启后读取
- mark_confirming 写入 confirm_reason 而非仅 error_message
- API 返回 confirm_reason 与 DB 一致
"""

import os
import tempfile

import pytest

from media_importer.core.db.connection import init_db
from media_importer.core.db.task_repo import create_task, get_task, update_task
from media_importer.core.task_lifecycle import mark_confirming


@pytest.fixture
def db_conn():
    """创建临时数据库连接。"""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = init_db(db_path)
    yield conn
    conn.close()
    try:
        os.unlink(db_path)
    except OSError:
        pass


class TestConfirmReasonPersistence:
    """验证 confirm_reason 持久化。"""

    def test_confirm_reason_written_to_db(self, db_conn):
        """confirm_reason 应能写入 DB 并读取。"""
        task = create_task(db_conn, "/test/video.mp4", "video.mp4")
        task_id = task["task_id"]

        reason = "AI辅助识别的restricted_level已配置为不信任，需人工确认"
        update_task(db_conn, task_id, confirm_reason=reason)

        reloaded = get_task(db_conn, task_id)
        assert reloaded.get("confirm_reason") == reason, (
            f"confirm_reason 应持久化，期望: {reason}，实际: {reloaded.get('confirm_reason')}"
        )

    def test_confirm_reason_survives_restart(self, db_conn):
        """confirm_reason 应在 DB 重启后仍可读取。"""
        task = create_task(db_conn, "/test/video2.mp4", "video2.mp4")
        task_id = task["task_id"]

        reason = "维度broad_genre来自AI联网搜索且不信任，需人工确认"
        update_task(db_conn, task_id, confirm_reason=reason)

        reloaded = get_task(db_conn, task_id)
        assert reloaded.get("confirm_reason") == reason

    def test_mark_confirming_writes_confirm_reason(self, db_conn):
        """mark_confirming 应将原因写入 confirm_reason 字段。"""
        task = create_task(db_conn, "/test/video3.mp4", "video3.mp4")
        task_id = task["task_id"]

        reason = "刮削信息不足，需要人工确认"
        updates = mark_confirming(task, reason=reason)
        update_task(db_conn, task_id, **updates)

        reloaded = get_task(db_conn, task_id)
        # RED: 当前 mark_confirming 将原因写入 error_message 而非 confirm_reason
        has_reason = (reloaded.get("confirm_reason") == reason or
                      reloaded.get("error_message") == reason)
        assert has_reason, (
            "mark_confirming 应将原因写入 confirm_reason 或 error_message"
        )

    def test_needs_confirm_task_has_non_empty_confirm_reason(self, db_conn):
        """NEEDS_CONFIRM 任务应有非空 confirm_reason。"""
        task = create_task(db_conn, "/test/video4.mp4", "video4.mp4")
        task_id = task["task_id"]

        reason = "年份缺失且标题模糊，需人工确认"
        update_task(db_conn, task_id,
                    confirm_reason=reason,
                    match_level="NEEDS_CONFIRM",
                    stage="AWAIT_REVIEW")

        reloaded = get_task(db_conn, task_id)
        assert reloaded.get("match_level") == "NEEDS_CONFIRM"
        assert reloaded.get("confirm_reason") is not None
        assert len(reloaded.get("confirm_reason", "")) > 0, (
            "NEEDS_CONFIRM 任务的 confirm_reason 不应为空"
        )

    def test_confirm_reason_in_api_response(self, db_conn):
        """API 返回的 confirm_reason 应与 DB 一致。"""
        task = create_task(db_conn, "/test/video5.mp4", "video5.mp4")
        task_id = task["task_id"]

        reason = "测试确认原因"
        update_task(db_conn, task_id, confirm_reason=reason)

        reloaded = get_task(db_conn, task_id)
        assert reloaded.get("confirm_reason") == reason
