import os

from media_importer.api.handler import _cleanup_orphaned_state
from media_importer.core import db as db_module
from media_importer.core.task_manager import TaskManager
from media_importer.features.tasks import STAGE_DONE, STATUS_FAILED


class _RecordingLogger:
    def __init__(self):
        self.messages = []

    def info(self, message, *args, **kwargs):
        self.messages.append(message)

    def warning(self, message, *args, **kwargs):
        self.messages.append(message)


def make_task_manager(tmp_path, temp_dir):
    conn = db_module.init_db(str(tmp_path / "tasks.db"))
    manager = TaskManager.__new__(TaskManager)
    manager.config = {}
    manager.conn = conn
    manager._lock = __import__("threading").RLock()
    return manager, conn


def create_task(conn, status="PENDING", stage="QUEUED", **fields):
    task = db_module.create_task(
        conn,
        source_path=f"/source/{status}-{stage}.mkv",
        source_filename=f"{status}-{stage}.mkv",
        file_size_mb=120.0,
    )
    update = {"status": status, "stage": stage}
    update.update(fields)
    db_module.update_task(conn, task["task_id"], **update)
    return db_module.get_task(conn, task["task_id"])


def test_orphaned_running_marked_failed(tmp_path):
    config = {"temp_dir": str(tmp_path / "temp")}
    os.makedirs(config["temp_dir"], exist_ok=True)
    manager, conn = make_task_manager(tmp_path, config["temp_dir"])

    task = create_task(
        manager.conn,
        status="PENDING",
        stage="RUNNING",
        current_step=3,
        percentage=42,
    )
    tid = task["task_id"]

    logger = _RecordingLogger()
    _cleanup_orphaned_state(config, manager, logger)

    updated = db_module.get_task(conn, tid)
    assert updated["status"] == STATUS_FAILED
    assert updated["stage"] == STAGE_DONE
    assert updated["error_message"] == "服务中断或重启导致任务未完成，请重试"
    assert updated["file_location"] == "source"
    assert updated["current_step"] == 0
    assert updated["percentage"] == 0
    assert updated["video_path"] == ""
    assert updated["completed_at"]


def test_await_review_task_left_alone(tmp_path):
    config = {"temp_dir": str(tmp_path / "temp")}
    os.makedirs(config["temp_dir"], exist_ok=True)
    manager, conn = make_task_manager(tmp_path, config["temp_dir"])

    task = create_task(
        manager.conn,
        status="PENDING",
        stage="AWAIT_REVIEW",
        current_step=5,
        percentage=60,
    )

    logger = _RecordingLogger()
    _cleanup_orphaned_state(config, manager, logger)

    updated = db_module.get_task(conn, task["task_id"])
    assert updated["status"] == "PENDING"
    assert updated["stage"] == "AWAIT_REVIEW"
    assert updated["current_step"] == 5


def test_terminal_failed_task_left_alone(tmp_path):
    config = {"temp_dir": str(tmp_path / "temp")}
    os.makedirs(config["temp_dir"], exist_ok=True)
    manager, conn = make_task_manager(tmp_path, config["temp_dir"])

    task = create_task(
        manager.conn,
        status="FAILED",
        stage="DONE",
        error_message="原始错误",
    )

    logger = _RecordingLogger()
    _cleanup_orphaned_state(config, manager, logger)

    updated = db_module.get_task(conn, task["task_id"])
    assert updated["error_message"] == "原始错误"


# Requirement: REQ-20260831-004019
def test_orphaned_running_task_never_deletes_file_already_in_library(tmp_path):
    temp_dir = tmp_path / "temp"
    library_dir = tmp_path / "library"
    temp_dir.mkdir()
    library_dir.mkdir()
    library_video = library_dir / "Movie.2026.mkv"
    library_video.write_bytes(b"library-bytes-must-survive")
    config = {
        "temp_dir": str(temp_dir),
        "library_roots": [
            {"id": "movies", "name": "电影", "path": str(library_dir), "enabled": True}
        ],
    }
    manager, conn = make_task_manager(tmp_path, str(temp_dir))
    task = create_task(
        conn,
        status="PENDING",
        stage="RUNNING",
        file_location="temp",
        video_path=str(library_video),
        import_video_path=str(library_video),
        import_success=1,
    )

    _cleanup_orphaned_state(config, manager, _RecordingLogger())

    assert library_video.read_bytes() == b"library-bytes-must-survive"
    updated = db_module.get_task(conn, task["task_id"])
    assert updated["status"] == "SUCCESS"
    assert updated["stage"] == STAGE_DONE
    assert updated["file_location"] == "import"
    assert updated["import_video_path"] == str(library_video)


# Requirement: REQ-20260831-004019
def test_disabled_library_root_still_blocks_orphan_temp_cleanup(tmp_path):
    library_dir = tmp_path / "library"
    library_dir.mkdir()
    library_video = library_dir / "Movie.2026.mkv"
    library_video.write_bytes(b"disabled-library-must-survive")
    config = {
        "temp_dir": str(library_dir),
        "library_roots": [
            {"id": "old", "name": "停用片库", "path": str(library_dir), "enabled": False}
        ],
    }
    manager, conn = make_task_manager(tmp_path, str(library_dir))
    task = create_task(
        conn,
        status="PENDING",
        stage="RUNNING",
        file_location="temp",
        video_path=str(library_video),
        import_success=0,
    )

    _cleanup_orphaned_state(config, manager, _RecordingLogger())

    assert library_video.read_bytes() == b"disabled-library-must-survive"
    updated = db_module.get_task(conn, task["task_id"])
    assert updated["status"] == STATUS_FAILED
    assert updated["video_path"] == str(library_video)
