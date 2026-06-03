from pathlib import Path

from media_importer.features.tasks import rename_task_file_for_api


class FakeTaskManager:
    def __init__(self, task):
        self.task = task
        self.conn = object()

    def get_task(self, task_id):
        if self.task and self.task.get("task_id") == task_id:
            return self.task
        return None


def test_rename_source_task_file_updates_source_path(tmp_path, monkeypatch):
    current = tmp_path / "old.mkv"
    current.write_text("video")
    task = {
        "task_id": "task-1",
        "file_location": "source",
        "source_path": str(current),
        "source_filename": "old.mkv",
    }
    task_manager = FakeTaskManager(task)
    calls = []

    def fake_update_task(conn, task_id, **fields):
        calls.append((conn, task_id, fields))
        task.update(fields)

    monkeypatch.setattr(
        "media_importer.features.tasks.file_lifecycle_service.update_task_record",
        fake_update_task,
    )

    result = rename_task_file_for_api(task_manager, "task-1", "new.mkv")

    expected_path = tmp_path / "new.mkv"
    assert result.code == 200
    assert result.message == "文件重命名成功"
    assert result.data == {"task": task}
    assert expected_path.exists()
    assert not current.exists()
    assert calls == [
        (
            task_manager.conn,
            "task-1",
            {"source_filename": "new.mkv", "source_path": str(expected_path)},
        )
    ]


def test_rename_import_task_file_updates_import_fields(tmp_path, monkeypatch):
    current = tmp_path / "old.mkv"
    current.write_text("video")
    task = {
        "task_id": "task-1",
        "file_location": "import",
        "import_video_path": str(current),
        "source_filename": "old.mkv",
    }
    task_manager = FakeTaskManager(task)
    calls = []

    def fake_update_task(conn, task_id, **fields):
        calls.append(fields)
        task.update(fields)

    monkeypatch.setattr(
        "media_importer.features.tasks.file_lifecycle_service.update_task_record",
        fake_update_task,
    )

    result = rename_task_file_for_api(task_manager, "task-1", "final.mkv")

    assert result.code == 200
    assert calls == [
        {
            "source_filename": "final.mkv",
            "import_video_path": str(tmp_path / "final.mkv"),
            "final_filename": "final.mkv",
        }
    ]


def test_rename_temp_task_file_updates_video_path(tmp_path, monkeypatch):
    current = tmp_path / "old.mkv"
    current.write_text("video")
    task = {
        "task_id": "task-1",
        "file_location": "temp",
        "video_path": str(current),
        "source_filename": "old.mkv",
    }
    task_manager = FakeTaskManager(task)
    calls = []

    monkeypatch.setattr(
        "media_importer.features.tasks.file_lifecycle_service.update_task_record",
        lambda conn, task_id, **fields: calls.append(fields) or task.update(fields),
    )

    result = rename_task_file_for_api(task_manager, "task-1", "temp-new.mkv")

    assert result.code == 200
    assert calls == [
        {
            "source_filename": "temp-new.mkv",
            "video_path": str(tmp_path / "temp-new.mkv"),
        }
    ]


def test_rename_rejects_path_traversal_filename(tmp_path):
    current = tmp_path / "old.mkv"
    current.write_text("video")
    task_manager = FakeTaskManager({
        "task_id": "task-1",
        "file_location": "source",
        "source_path": str(current),
    })

    result = rename_task_file_for_api(task_manager, "task-1", "../escape.mkv")

    assert result.code == 400
    assert result.message == "new_filename 只能是文件名，不能包含路径"
    assert current.exists()
    assert not Path(tmp_path.parent / "escape.mkv").exists()


def test_rename_rejects_existing_target(tmp_path):
    current = tmp_path / "old.mkv"
    current.write_text("video")
    target = tmp_path / "exists.mkv"
    target.write_text("other")
    task_manager = FakeTaskManager({
        "task_id": "task-1",
        "file_location": "source",
        "source_path": str(current),
    })

    result = rename_task_file_for_api(task_manager, "task-1", "exists.mkv")

    assert result.code == 400
    assert result.message == "目标文件名已存在: exists.mkv"
    assert current.exists()
    assert target.read_text() == "other"


def test_rename_rejects_deleted_task():
    task_manager = FakeTaskManager({"task_id": "task-1", "file_location": "deleted"})

    result = rename_task_file_for_api(task_manager, "task-1", "new.mkv")

    assert result.code == 400
    assert result.message == "文件已删除，无法重命名"


def test_rename_rejects_missing_task():
    result = rename_task_file_for_api(FakeTaskManager(None), "missing", "new.mkv")

    assert result.code == 404
    assert result.message == "Task not found: missing"
