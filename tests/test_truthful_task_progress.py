from media_importer.core.db.connection import init_db
from media_importer.core.db.task_repo import create_task, list_tasks, update_task
from media_importer.features.import_flow.progress import TaskProgressReporter


class RecordingTaskManager:
    def __init__(self):
        self.calls = []

    def update_progress(self, task, step_num, step_name, percentage, **kwargs):
        task.update(
            current_step=step_num,
            step_name=step_name,
            percentage=percentage,
            **kwargs,
        )
        self.calls.append((step_name, percentage, kwargs))


class FailingProgressTaskManager(RecordingTaskManager):
    def update_progress(self, task, step_num, step_name, percentage, **kwargs):
        raise RuntimeError("database busy")


# Requirement: REQ-20260901-010051
def test_progress_reporter_throttles_chunk_updates_and_never_regresses():
    manager = RecordingTaskManager()
    reporter = TaskProgressReporter(
        manager,
        min_interval=999,
        min_percent_delta=10,
        min_bytes_delta=10_000,
    )
    task = {"task_id": "task-1", "percentage": 20}

    assert reporter.update(task, 2, "copy_transfer", 20, completed_bytes=0, total_bytes=100)
    assert not reporter.update(task, 2, "copy_transfer", 19, completed_bytes=5, total_bytes=100)
    assert reporter.update(task, 2, "copy_transfer", 21, completed_bytes=10, total_bytes=100)
    assert reporter.update(task, 2, "copy_verify_source", 18, completed_bytes=0, total_bytes=100)
    assert reporter.update(task, 2, "copy_verify_source", 18, completed_bytes=100, total_bytes=100)

    assert len(manager.calls) == 4
    assert [call[1] for call in manager.calls] == [20, 21, 21, 21]


# Requirement: REQ-20260901-010051
def test_task_list_query_exposes_live_progress_fields(tmp_path):
    conn = init_db(str(tmp_path / "tasks.db"))
    task = create_task(conn, str(tmp_path / "movie.mkv"), "movie.mkv")
    update_task(
        conn,
        task["task_id"],
        status="PENDING",
        stage="RUNNING",
        current_step=2,
        total_steps=10,
        step_name="copy_verify_target",
        percentage=29,
        bytes_copied=75,
        total_bytes=100,
        source_cleanup_status="WAITING",
    )

    rows, total, _pages = list_tasks(conn)

    assert total == 1
    assert rows[0]["current_step"] == 2
    assert rows[0]["total_steps"] == 10
    assert rows[0]["step_name"] == "copy_verify_target"
    assert rows[0]["bytes_copied"] == 75
    assert rows[0]["total_bytes"] == 100
    assert rows[0]["source_cleanup_status"] == "WAITING"


# Requirement: REQ-20260901-010051
def test_pipeline_progress_failure_does_not_interrupt_file_work():
    from media_importer.features.import_flow.runner import PipelineRunner

    runner = PipelineRunner.__new__(PipelineRunner)
    runner.task_manager = FailingProgressTaskManager()
    runner.logger = None
    task = {"task_id": "task-1", "percentage": 20}

    runner._update_transfer_progress(
        task,
        2,
        "copy_transfer",
        21,
        10,
        100,
    )

    assert task["percentage"] == 20
