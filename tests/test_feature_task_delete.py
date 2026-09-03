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
    assert result.message == "任务尚未结束，请先使用“结束处理”决定新资源如何处理"


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
