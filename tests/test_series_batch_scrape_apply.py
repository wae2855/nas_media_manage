"""Requirement: REQ-20260904-115624."""

from copy import deepcopy

from media_importer.features.tasks import (
    apply_scrape_candidate_for_api,
    preview_series_batch_for_api,
)
from media_importer.features.tasks.series_batch_service import discover_series_batch


def _episode_task(index: int, **overrides) -> dict:
    task = {
        "task_id": f"north-water-{index}",
        "source_path": (
            "/downloads/北海鲸梦.第一季.2021/"
            f"北海鲸梦.第一季.2021.EP{index:02d}.HD1080P.mkv"
        ),
        "source_filename": f"北海鲸梦.第一季.2021.EP{index:02d}.HD1080P.mkv",
        "status": "PENDING",
        "stage": "AWAIT_REVIEW",
        "scrape_media_type": "tv",
        "scrape_result": {"media_type": "tv", "season": 1, "episode": index},
        "scrape_dimensions": {"media_type": "tv", "season": 1, "episode": index},
        "scrape_trace": {},
        "dedup_result": {},
    }
    task.update(overrides)
    return task


class FakeManager:
    def __init__(self, tasks):
        self.tasks = {task["task_id"]: deepcopy(task) for task in tasks}
        self.conn = object()

    def get_task(self, task_id):
        task = self.tasks.get(task_id)
        return deepcopy(task) if task else None

    def list_tasks(self, status=None, stage=None, limit=20):
        return [
            deepcopy(task)
            for task in self.tasks.values()
            if (not status or task.get("status") == status)
            and (not stage or task.get("stage") == stage)
        ][:limit]


def _selection():
    return {"provider_type": "tmdb", "item_id": "86941", "media_type": "tv"}


def test_north_water_five_episode_batch_is_previewed_in_episode_order():
    manager = FakeManager([_episode_task(index) for index in range(1, 6)])

    result = discover_series_batch(manager, "north-water-1", _selection())

    assert [item["episode"] for item in result["tasks"]] == [1, 2, 3, 4, 5]
    assert sum(item["is_anchor"] for item in result["tasks"]) == 1
    assert result["excluded"] == []


def test_series_batch_api_preview_returns_safe_tasks():
    manager = FakeManager([_episode_task(1), _episode_task(2)])

    result = preview_series_batch_for_api(manager, "north-water-1", _selection())

    assert result.code == 200
    assert [item["task_id"] for item in result.data["tasks"]] == [
        "north-water-1",
        "north-water-2",
    ]


def test_series_batch_excludes_unsafe_tasks_and_duplicate_episodes():
    tasks = [_episode_task(1), _episode_task(2)]
    tasks.extend(
        [
            _episode_task(
                3,
                task_id="other-show",
                source_filename="企鹅人.S01E03.mkv",
                source_path="/downloads/北海鲸梦.第一季.2021/企鹅人.S01E03.mkv",
            ),
            _episode_task(
                4,
                task_id="other-directory",
                source_path="/downloads/another/北海鲸梦.S01E04.mkv",
            ),
            _episode_task(5, task_id="movie", scrape_media_type="movie"),
            _episode_task(
                6,
                task_id="conflict",
                dedup_result={"is_duplicate": True, "status": "awaiting_user"},
            ),
            _episode_task(
                7,
                task_id="manual-other",
                provider_type="tmdb",
                provider_id="123",
                scrape_trace={"manual_selected": True},
            ),
            _episode_task(2, task_id="duplicate-episode"),
        ]
    )
    manager = FakeManager(tasks)

    result = discover_series_batch(manager, "north-water-1", _selection())

    assert [item["task_id"] for item in result["tasks"]] == ["north-water-1"]
    reasons = {item["task_id"]: item["reason"] for item in result["excluded"]}
    assert reasons == {
        "other-show": "different_title",
        "other-directory": "different_directory",
        "movie": "not_tv",
        "conflict": "library_conflict",
        "manual-other": "different_manual_provider",
        "north-water-2": "duplicate_episode",
        "duplicate-episode": "duplicate_episode",
    }


class FakeBatchPipeline:
    def __init__(self, manager):
        self.config = {}
        self.manager = manager
        self.calls = []

    def apply_loaded_scrape_candidate(self, task_id, **kwargs):
        if task_id == getattr(self, "fail_task_id", None):
            raise RuntimeError("state changed")
        task = self.manager.get_task(task_id)
        task["provider_id"] = kwargs["item_id"]
        task["scrape_result"] = {
            "title_cn": kwargs["selected"]["scrape_result"]["title_cn"],
            "media_type": "tv",
            "season": task["scrape_result"]["season"],
            "episode": task["scrape_result"]["episode"],
        }
        self.calls.append(task)
        return task


def test_batch_apply_revalidates_ids_loads_provider_once_and_keeps_episodes(monkeypatch):
    manager = FakeManager([_episode_task(index) for index in range(1, 6)])
    pipeline = FakeBatchPipeline(manager)
    loaded = []

    def fake_load(*args, **kwargs):
        loaded.append(kwargs)
        return {"scrape_result": {"title_cn": "北海鲸梦"}}

    monkeypatch.setattr(
        "media_importer.features.tasks.search_service.load_provider_candidate",
        fake_load,
    )

    result = apply_scrape_candidate_for_api(
        pipeline,
        "north-water-1",
        _selection(),
        task_manager=manager,
        related_task_ids=[
            "north-water-2",
            "north-water-3",
            "north-water-4",
            "north-water-5",
            "arbitrary-task",
        ],
    )

    assert result.code == 200
    assert len(loaded) == 1
    assert [task["scrape_result"]["episode"] for task in pipeline.calls] == [1, 2, 3, 4, 5]
    assert result.data["skipped"] == [
        {"task_id": "arbitrary-task", "reason": "not_in_safe_series_batch"}
    ]
    assert result.data["failed"] == []


def test_batch_apply_reports_partial_failure_without_hiding_success(monkeypatch):
    manager = FakeManager([_episode_task(1), _episode_task(2), _episode_task(3)])
    pipeline = FakeBatchPipeline(manager)
    pipeline.fail_task_id = "north-water-3"
    monkeypatch.setattr(
        "media_importer.features.tasks.search_service.load_provider_candidate",
        lambda *args, **kwargs: {"scrape_result": {"title_cn": "北海鲸梦"}},
    )

    result = apply_scrape_candidate_for_api(
        pipeline,
        "north-water-1",
        _selection(),
        task_manager=manager,
        related_task_ids=["north-water-2", "north-water-3"],
    )

    assert result.code == 200
    assert result.data["updated"] == [
        {"task_id": "north-water-1"},
        {"task_id": "north-water-2"},
    ]
    assert result.data["failed"] == [
        {"task_id": "north-water-3", "error": "state changed"}
    ]
    assert "失败 1 项" in result.message


def test_batch_apply_rejects_non_array_related_task_ids():
    result = apply_scrape_candidate_for_api(
        FakeBatchPipeline(FakeManager([_episode_task(1)])),
        "north-water-1",
        _selection(),
        task_manager=FakeManager([_episode_task(1)]),
        related_task_ids="north-water-2",
    )

    assert result.code == 400
    assert result.message == "related_task_ids 必须是数组"
