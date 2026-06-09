from pathlib import Path

from media_importer.features.tasks import ignore_task_for_api, rename_task_file_for_api


class FakeTaskManager:
    def __init__(self, task):
        self.task = task
        self.conn = object()
        self.recycle_calls = []

    def get_task(self, task_id):
        if self.task and self.task.get("task_id") == task_id:
            return self.task
        return None

    def move_to_recycle_bin(self, **kwargs):
        self.recycle_calls.append(kwargs)


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


def test_ignore_temp_task_cleans_temp_files_and_recycles_source(tmp_path, monkeypatch):
    temp_dir = tmp_path / "temp"
    source_dir = tmp_path / "source"
    recycle_dir = tmp_path / "recycle"
    temp_dir.mkdir()
    source_dir.mkdir()
    recycle_dir.mkdir()
    temp_video = temp_dir / "working.mkv"
    temp_sub = temp_dir / "working.srt"
    source_video = source_dir / "movie.mkv"
    temp_video.write_text("temp video")
    temp_sub.write_text("temp sub")
    source_video.write_text("source video")
    task = {
        "task_id": "task-1",
        "status": "PENDING",
        "stage": "AWAIT_REVIEW",
        "file_location": "temp",
        "video_path": str(temp_video),
        "source_path": str(source_video),
        "subtitle_files": [str(temp_sub)],
    }
    task_manager = FakeTaskManager(task)
    task_updates = []
    subtitle_updates = []

    monkeypatch.setattr(
        "media_importer.features.tasks.file_lifecycle_service.update_task_record",
        lambda conn, task_id, **fields: task_updates.append(fields) or task.update(fields),
    )
    monkeypatch.setattr(
        "media_importer.features.tasks.file_lifecycle_service.update_subtitles_by_task_record",
        lambda conn, task_id, **fields: subtitle_updates.append((task_id, fields)),
    )

    result = ignore_task_for_api(
        task_manager,
        {
            "temp_dir": str(temp_dir),
            "source_policy": {
                "cleanup_source_after_done": True,
                "recycle_dir": str(recycle_dir),
            },
        },
        "task-1",
    )

    assert result.code == 200
    assert result.message == "任务已忽略"
    assert not temp_video.exists()
    assert not temp_sub.exists()
    assert source_video.exists()
    assert subtitle_updates == [("task-1", {"status": "FAILED", "target_path": ""})]
    assert task_manager.recycle_calls == [
        {
            "task_id": "task-1",
            "source_path": str(source_video),
            "subtitle_paths": [str(temp_sub)],
            "recycle_dir": str(recycle_dir),
        }
    ]
    assert task_updates == [
        {
            "status": "SKIPPED",
            "stage": "DONE",
            "skip_reason": "用户忽略",
            "file_location": "recycle",
            "video_path": "",
            "error_message": f"已移入回收站: {recycle_dir}",
        }
    ]


def test_ignore_temp_task_does_not_delete_files_outside_temp_dir(tmp_path, monkeypatch):
    temp_dir = tmp_path / "temp"
    outside_dir = tmp_path / "temp-other"
    temp_dir.mkdir()
    outside_dir.mkdir()
    outside_video = outside_dir / "outside.mkv"
    outside_video.write_text("outside")
    task = {
        "task_id": "task-1",
        "status": "PENDING",
        "stage": "AWAIT_REVIEW",
        "file_location": "temp",
        "video_path": str(outside_video),
        "source_path": "",
        "subtitle_files": [],
    }
    task_manager = FakeTaskManager(task)

    monkeypatch.setattr(
        "media_importer.features.tasks.file_lifecycle_service.update_task_record",
        lambda conn, task_id, **fields: task.update(fields),
    )
    monkeypatch.setattr(
        "media_importer.features.tasks.file_lifecycle_service.update_subtitles_by_task_record",
        lambda conn, task_id, **fields: None,
    )

    result = ignore_task_for_api(task_manager, {"temp_dir": str(temp_dir)}, "task-1")

    assert result.code == 200
    assert outside_video.exists()
    assert task["file_location"] == "source"
    assert task["video_path"] == ""


def test_ignore_source_task_recycles_source_when_cleanup_enabled(tmp_path, monkeypatch):
    source_file = tmp_path / "movie.mkv"
    source_file.write_text("source video")
    recycle_dir = tmp_path / "recycle"
    recycle_dir.mkdir()
    task = {
        "task_id": "task-1",
        "status": "FAILED",
        "file_location": "source",
        "source_path": str(source_file),
        "subtitle_files": ["subtitle.srt"],
    }
    task_manager = FakeTaskManager(task)
    task_updates = []

    monkeypatch.setattr(
        "media_importer.features.tasks.file_lifecycle_service.update_task_record",
        lambda conn, task_id, **fields: task_updates.append(fields) or task.update(fields),
    )

    result = ignore_task_for_api(
        task_manager,
        {
            "source_policy": {
                "cleanup_source_after_done": True,
                "recycle_dir": str(recycle_dir),
            }
        },
        "task-1",
    )

    assert result.code == 200
    assert task_manager.recycle_calls == [
        {
            "task_id": "task-1",
            "source_path": str(source_file),
            "subtitle_paths": ["subtitle.srt"],
            "recycle_dir": str(recycle_dir),
        }
    ]
    assert task_updates == [
        {
            "status": "SKIPPED",
            "stage": "DONE",
            "skip_reason": "用户忽略",
            "error_message": f"已移入回收站: {recycle_dir}",
        }
    ]


def test_ignore_task_rejects_invalid_status():
    task_manager = FakeTaskManager({
        "task_id": "task-1",
        "status": "PENDING",
        "file_location": "source",
    })

    result = ignore_task_for_api(task_manager, {}, "task-1")

    assert result.code == 400
    assert result.message == "当前状态不可忽略: PENDING"
    assert task_manager.recycle_calls == []


def test_ignore_task_rejects_missing_task():
    result = ignore_task_for_api(FakeTaskManager(None), {}, "missing")

    assert result.code == 404
    assert result.message == "Task not found: missing"
