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
    task_manager = FakeTaskManager({"task_id": "t1", "status": "PROCESSING"})

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
