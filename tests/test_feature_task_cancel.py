import os
import threading

from media_importer.core import db as db_module
from media_importer.features.tasks import (
    STAGE_DONE,
    STAGE_QUEUED,
    STATUS_CANCELLED,
    STATUS_PENDING,
    TaskManager,
    cancel_task_for_api,
    mark_cancelled,
)


def make_task_manager(tmp_path):
    conn = db_module.init_db(str(tmp_path / "tasks.db"))
    manager = TaskManager.__new__(TaskManager)
    manager.config = {}
    manager.conn = conn
    manager._lock = threading.RLock()
    return manager


def create_task(conn, status="PENDING", stage="QUEUED", **fields):
    source_path = fields.pop("source_path", f"/source/{status.lower()}-{stage.lower()}.mkv")
    source_filename = fields.pop("source_filename", os.path.basename(source_path))
    task = db_module.create_task(
        conn,
        source_path=source_path,
        source_filename=source_filename,
        file_size_mb=100.0,
    )
    db_module.update_task(conn, task["task_id"], status=status, stage=stage, **fields)
    return db_module.get_task(conn, task["task_id"])


def test_mark_cancelled_sets_terminal_contract():
    task = {
        "task_id": "task-1",
        "status": "PENDING",
        "stage": "QUEUED",
        "file_location": "source",
    }

    fields = mark_cancelled(task, "用户取消测试")

    assert fields["status"] == STATUS_CANCELLED
    assert fields["stage"] == STAGE_DONE
    assert fields["error_message"] == "用户取消测试"
    assert fields["file_location"] == "source"
    assert fields["video_path"] == ""
    assert fields["completed_at"]
    assert task["status"] == STATUS_CANCELLED
    assert task["stage"] == STAGE_DONE


def test_cancel_queued_task_success(tmp_path):
    manager = make_task_manager(tmp_path)
    task = create_task(manager.conn, status="PENDING", stage="QUEUED")

    result = manager.cancel_task(task["task_id"], reason="手动取消")

    assert result["status"] == STATUS_CANCELLED
    assert result["stage"] == STAGE_DONE
    assert result["error_message"] == "手动取消"
    assert result["completed_at"]
    assert result["file_location"] == "source"
    manager.conn.close()


def test_cancel_rejects_running_task(tmp_path):
    manager = make_task_manager(tmp_path)
    task = create_task(manager.conn, status="PENDING", stage="RUNNING")

    result = manager.cancel_task(task["task_id"])

    assert result == {"error": "当前状态不可取消: PENDING/RUNNING"}
    updated = db_module.get_task(manager.conn, task["task_id"])
    assert updated["status"] == "PENDING"
    assert updated["stage"] == "RUNNING"
    manager.conn.close()


def test_cancel_rejects_terminal_task(tmp_path):
    manager = make_task_manager(tmp_path)
    task = create_task(manager.conn, status="SUCCESS", stage="DONE")

    result = manager.cancel_task(task["task_id"])

    assert result == {"error": "当前状态不可取消: SUCCESS/DONE"}
    manager.conn.close()


def test_cancel_missing_task_returns_none(tmp_path):
    manager = make_task_manager(tmp_path)

    result = manager.cancel_task("missing")

    assert result is None
    manager.conn.close()


def test_cancelled_task_can_retry(tmp_path):
    manager = make_task_manager(tmp_path)
    task = create_task(manager.conn, status="PENDING", stage="QUEUED")
    cancelled = manager.cancel_task(task["task_id"])

    result = manager.retry_task(cancelled["task_id"])

    assert result["status"] == STATUS_PENDING
    assert result["stage"] == STAGE_QUEUED
    assert result["retry_count"] == 1
    assert result["error_message"] == ""
    manager.conn.close()


def test_cancel_task_for_api_success(tmp_path):
    manager = make_task_manager(tmp_path)
    task = create_task(manager.conn, status="PENDING", stage="QUEUED")

    result = cancel_task_for_api(manager, task["task_id"])

    assert result.code == 200
    assert result.message == "任务已取消"
    assert result.data["task"]["status"] == STATUS_CANCELLED
    manager.conn.close()


def test_cancel_task_for_api_invalid_status(tmp_path):
    manager = make_task_manager(tmp_path)
    task = create_task(manager.conn, status="PENDING", stage="AWAIT_REVIEW")

    result = cancel_task_for_api(manager, task["task_id"])

    assert result.code == 400
    assert result.message == "当前状态不可取消: PENDING/AWAIT_REVIEW"
    manager.conn.close()


def test_cancel_task_for_api_missing_task(tmp_path):
    manager = make_task_manager(tmp_path)

    result = cancel_task_for_api(manager, "missing")

    assert result.code == 404
    assert result.message == "Task not found: missing"
    manager.conn.close()


def test_list_cancelled_tasks_after_cancel(tmp_path):
    manager = make_task_manager(tmp_path)
    task = create_task(manager.conn, status="PENDING", stage="QUEUED")
    manager.cancel_task(task["task_id"])

    rows, total, total_pages = db_module.list_tasks(
        manager.conn,
        page=1,
        page_size=20,
        status="CANCELLED",
    )

    assert total == 1
    assert total_pages == 1
    assert rows[0]["task_id"] == task["task_id"]
    assert rows[0]["status"] == STATUS_CANCELLED
    manager.conn.close()
