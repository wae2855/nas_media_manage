from unittest.mock import patch

from media_importer.features.tasks import list_tasks_for_api


class FakeTaskManager:
    conn = object()

    def count_by_status(self):
        return {
            "PENDING": 3,
            "FAILED": 3,
            "SUCCESS": 5,
        }


class FakeLogger:
    def __init__(self):
        self.messages = []

    def warning(self, message):
        self.messages.append(message)


def test_list_tasks_for_api_builds_pagination_payload():
    with patch(
        "media_importer.features.tasks.list_service.db_list_tasks",
        return_value=([{"task_id": "t1"}], 1, 1),
    ) as patched:
        result = list_tasks_for_api(
            {"limit": ["10"], "offset": ["20"], "status": ["pending"]},
            FakeTaskManager(),
        )

    patched.assert_called_once_with(
        FakeTaskManager.conn,
        page=3,
        page_size=10,
        statuses=["PENDING"],
        stage=None,
    )
    assert result.code == 200
    assert result.data["tasks"] == [{"task_id": "t1"}]
    assert result.data["active_count"] == 6


def test_list_tasks_for_api_rejects_invalid_status():
    logger = FakeLogger()

    result = list_tasks_for_api(
        {"status": ["bad"]},
        FakeTaskManager(),
        logger=logger,
    )

    assert result.code == 400
    assert result.message == "Invalid status: BAD"
    assert logger.messages


def test_list_tasks_for_api_preserves_text_format_mode():
    with patch(
        "media_importer.features.tasks.list_service.db_list_tasks",
        return_value=([], 0, 1),
    ):
        result = list_tasks_for_api(
            {"format": ["text"]},
            FakeTaskManager(),
        )

    assert result.code == 200
    assert result.format_mode == "text"
