from media_importer.features.tasks import (
    get_task_for_api,
    get_task_stats_for_api,
    get_task_subtitles_for_api,
)


class FakeTaskManager:
    def __init__(self):
        self.conn = object()
        self.counts = {"PENDING": 2, "FAILED": 1}
        self.task = {"task_id": "task-1", "status": "PENDING"}

    def count_by_status(self):
        return self.counts

    def get_task(self, task_id):
        if task_id == self.task["task_id"]:
            return self.task
        return None


def test_get_task_returns_payload():
    task_manager = FakeTaskManager()

    result = get_task_for_api(task_manager, "task-1")

    assert result.code == 200
    assert result.data == {"task": task_manager.task}


def test_get_task_returns_not_found():
    result = get_task_for_api(FakeTaskManager(), "missing")

    assert result.code == 404
    assert result.message == "Task not found: missing"


def test_get_task_requires_task_manager():
    result = get_task_for_api(None, "task-1")

    assert result.code == 500
    assert result.message == "TaskManager not initialized"


def test_get_task_subtitles_returns_payload(monkeypatch):
    task_manager = FakeTaskManager()
    subtitles = [{"path": "movie.zh.srt"}, {"path": "movie.en.srt"}]

    monkeypatch.setattr(
        "media_importer.features.tasks.detail_service.get_subtitles_by_task",
        lambda conn, task_id: subtitles,
    )

    result = get_task_subtitles_for_api(task_manager, "task-1")

    assert result.code == 200
    assert result.data == {"subtitles": subtitles, "total": 2}


def test_get_task_subtitles_requires_task_manager():
    result = get_task_subtitles_for_api(None, "task-1")

    assert result.code == 500
    assert result.message == "TaskManager not initialized"


def test_get_task_stats_returns_status_counts():
    task_manager = FakeTaskManager()

    result = get_task_stats_for_api(task_manager)

    assert result.code == 200
    assert result.data == {"by_status": task_manager.counts}


def test_get_task_stats_requires_task_manager():
    result = get_task_stats_for_api(None)

    assert result.code == 500
    assert result.message == "TaskManager not initialized"
