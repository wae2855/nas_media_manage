from media_importer.features.tasks import delete_task


class FakeTaskManager:
    def __init__(self, task):
        self.task = task
        self.conn = object()

    def get_task(self, task_id):
        if self.task and self.task.get("task_id") == task_id:
            return self.task
        return None


def test_delete_task_rejects_processing_task():
    task_manager = FakeTaskManager({"task_id": "t1", "status": "PENDING", "stage": "RUNNING"})

    result = delete_task(task_manager, {}, "t1")

    assert result.status_code == 400
    assert result.message == "任务正在处理中，无法删除，请等待处理完成"


def test_delete_task_cleans_temp_file_and_deletes_record(tmp_path, monkeypatch):
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    video_path = temp_dir / "movie.mkv"
    video_path.write_text("video")

    calls = []
    monkeypatch.setattr(
        "media_importer.features.tasks.delete_service.delete_task_record",
        lambda conn, task_id: calls.append((conn, task_id)) or True,
    )

    task_manager = FakeTaskManager({
        "task_id": "t1",
        "status": "PENDING",
        "file_location": "temp",
        "video_path": str(video_path),
        "subtitle_files": [],
    })

    result = delete_task(task_manager, {"temp_dir": str(temp_dir)}, "t1")

    assert result.status_code == 200
    assert result.data["deleted"] == "t1"
    assert result.data["deleted_files"] == ["movie.mkv"]
    assert not video_path.exists()
    assert calls == [(task_manager.conn, "t1")]


# Requirement: REQ-20260831-004019
def test_delete_task_rejects_file_action_for_imported_library_file(tmp_path, monkeypatch):
    library = tmp_path / "library"
    recycle = tmp_path / "recycle"
    library.mkdir()
    recycle.mkdir()
    video = library / "Movie.mkv"
    video.write_bytes(b"library-must-survive")
    calls = []
    monkeypatch.setattr(
        "media_importer.features.tasks.delete_service.delete_task_record",
        lambda conn, task_id: calls.append(task_id) or True,
    )
    task_manager = FakeTaskManager({
        "task_id": "t1",
        "status": "SUCCESS",
        "stage": "DONE",
        "file_location": "import",
        "import_video_path": str(video),
        "subtitle_files": [],
    })

    result = delete_task(
        task_manager,
        {
            "library_roots": [{"id": "movies", "path": str(library), "enabled": True}],
            "source_policy": {"recycle_dir": str(recycle)},
        },
        "t1",
        delete_files=True,
    )

    assert result.status_code == 400
    assert "片库文件" in result.message
    assert video.read_bytes() == b"library-must-survive"
    assert calls == []


# Requirement: REQ-20260831-004019
def test_delete_task_does_not_follow_temp_symlink_into_library(tmp_path, monkeypatch):
    temp_dir = tmp_path / "temp"
    library = tmp_path / "library"
    temp_dir.mkdir()
    library.mkdir()
    video = library / "Movie.mkv"
    video.write_bytes(b"library-must-survive")
    linked = temp_dir / "Movie.mkv"
    linked.symlink_to(video)
    calls = []
    monkeypatch.setattr(
        "media_importer.features.tasks.delete_service.delete_task_record",
        lambda conn, task_id: calls.append(task_id) or True,
    )
    task_manager = FakeTaskManager({
        "task_id": "t1",
        "status": "FAILED",
        "file_location": "temp",
        "video_path": str(linked),
        "subtitle_files": [],
    })

    result = delete_task(
        task_manager,
        {
            "temp_dir": str(temp_dir),
            "library_roots": [{"id": "movies", "path": str(library), "enabled": True}],
        },
        "t1",
    )

    assert result.status_code == 200
    assert video.read_bytes() == b"library-must-survive"
    assert linked.is_symlink()
    assert calls == ["t1"]


# Requirement: REQ-20260831-004019
def test_delete_task_rejects_mislabeled_source_path_inside_library(tmp_path, monkeypatch):
    library = tmp_path / "library"
    recycle = tmp_path / "recycle"
    library.mkdir()
    recycle.mkdir()
    video = library / "Movie.mkv"
    video.write_bytes(b"library-must-survive")
    calls = []
    monkeypatch.setattr(
        "media_importer.features.tasks.delete_service.delete_task_record",
        lambda conn, task_id: calls.append(task_id) or True,
    )
    config = {
        "library_roots": [{"id": "movies", "path": str(library), "enabled": True}],
        "source_policy": {"recycle_dir": str(recycle)},
    }
    task_manager = FakeTaskManager({
        "task_id": "legacy",
        "status": "FAILED",
        "file_location": "source",
        "source_path": str(video),
        "subtitle_files": [],
    })

    result = delete_task(task_manager, config, "legacy", delete_files=True)

    assert result.status_code == 400
    assert video.read_bytes() == b"library-must-survive"
    assert list(recycle.iterdir()) == []
    assert calls == []
