import threading

from media_importer.features.tasks.review_service import queue_confirm_task_for_api


class _TaskManager:
    def __init__(self, task):
        self.task = task

    def get_task(self, task_id):
        return self.task if task_id == self.task["task_id"] else None


def test_confirm_returns_before_background_file_work_finishes():
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    class Pipeline:
        def confirm_task(self, *_args, **_kwargs):
            started.set()
            release.wait(timeout=2)
            finished.set()
            return True

    manager = _TaskManager({
        "task_id": "background-1",
        "status": "PENDING",
        "stage": "AWAIT_REVIEW",
        "dedup_result": {},
    })
    result = queue_confirm_task_for_api(Pipeline(), manager, "background-1")

    assert result.code == 202
    assert result.data["queued"] is True
    assert started.wait(timeout=1)
    assert not finished.is_set()
    release.set()
    assert finished.wait(timeout=1)


def test_duplicate_confirm_click_does_not_start_second_worker():
    started = threading.Event()
    release = threading.Event()
    calls = []

    class Pipeline:
        def confirm_task(self, *_args, **_kwargs):
            calls.append("started")
            started.set()
            release.wait(timeout=2)
            return True

    manager = _TaskManager({
        "task_id": "background-2",
        "status": "PENDING",
        "stage": "AWAIT_REVIEW",
        "dedup_result": {},
    })
    first = queue_confirm_task_for_api(Pipeline(), manager, "background-2")
    assert started.wait(timeout=1)
    second = queue_confirm_task_for_api(Pipeline(), manager, "background-2")
    release.set()

    assert first.code == 202
    assert second.code == 202
    assert "已在后台" in second.message
    assert calls == ["started"]


def test_subtitle_bundle_conflict_cannot_select_unsupported_replace():
    manager = _TaskManager({
        "task_id": "background-3",
        "status": "PENDING",
        "stage": "AWAIT_REVIEW",
        "dedup_result": {
            "is_duplicate": True,
            "status": "awaiting_user",
            "replace_allowed": False,
        },
    })
    result = queue_confirm_task_for_api(
        object(), manager, "background-3", conflict_action="replace_existing"
    )
    assert result.code == 400
    assert "字幕冲突" in result.message
