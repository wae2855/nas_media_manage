from media_importer.features.tasks import (
    apply_scrape_candidate_for_api,
    confirm_all_tasks_for_api,
    confirm_task_for_api,
    reclassify_task_for_api,
)


class FakeTaskManager:
    def __init__(self):
        self.task = {"task_id": "task-1", "error_message": "bad metadata"}
        self.list_args = None
        self.confirming_tasks = [
            {"task_id": "task-1"},
            {"task_id": "task-2"},
            {"task_id": "task-3"},
        ]

    def get_task(self, task_id):
        if task_id == self.task["task_id"]:
            return self.task
        return None

    def list_tasks(self, status=None, stage=None, limit=20):
        self.list_args = {"status": status, "stage": stage, "limit": limit}
        return self.confirming_tasks


class FakePipeline:
    def __init__(self):
        self.confirm_results = {}
        self.confirmed = []
        self.reclassified = []
        self.confirm_exceptions = {}
        self.confirm_calls = []
        self.applied_candidates = []

    def apply_scrape_candidate(self, task_id, **selection):
        self.applied_candidates.append({"task_id": task_id, **selection})
        return {
            "task_id": task_id,
            "status": "PENDING",
            "stage": "AWAIT_REVIEW",
            "provider_id": selection["item_id"],
        }

    def confirm_task(self, task_id, confirmed_title=None, override_source=None,
                     conflict_action=None):
        self.confirmed.append(task_id)
        self.confirm_calls.append({
            "task_id": task_id,
            "confirmed_title": confirmed_title,
            "override_source": override_source,
            "conflict_action": conflict_action,
        })
        if task_id in self.confirm_exceptions:
            raise RuntimeError(self.confirm_exceptions[task_id])
        return self.confirm_results.get(task_id, True)

    def reclassify_task(self, task_id, dimensions):
        self.reclassified.append({"task_id": task_id, "dimensions": dimensions})
        return {"task_id": task_id, "dimensions": dimensions, "status": "CONFIRMING"}


def test_confirm_task_returns_success_message():
    result = confirm_task_for_api(FakePipeline(), FakeTaskManager(), "task-1")

    assert result.code == 200
    assert result.message == "任务确认入库成功"


def test_confirm_task_passes_explicit_conflict_action():
    pipeline = FakePipeline()

    result = confirm_task_for_api(
        pipeline,
        FakeTaskManager(),
        "task-1",
        conflict_action="keep_both",
    )

    assert result.code == 200
    assert pipeline.confirm_calls[-1]["conflict_action"] == "keep_both"


def test_confirm_task_includes_task_error_when_pipeline_returns_false():
    pipeline = FakePipeline()
    pipeline.confirm_results["task-1"] = False

    result = confirm_task_for_api(pipeline, FakeTaskManager(), "task-1")

    assert result.code == 500
    assert result.message == "确认入库失败: bad metadata"


def test_confirm_task_converts_pipeline_exception_to_bad_request():
    pipeline = FakePipeline()
    pipeline.confirm_exceptions["task-1"] = "cannot confirm"

    result = confirm_task_for_api(pipeline, FakeTaskManager(), "task-1")

    assert result.code == 400
    assert result.message == "cannot confirm"


def test_confirm_task_requires_pipeline():
    result = confirm_task_for_api(None, FakeTaskManager(), "task-1")

    assert result.code == 500
    assert result.message == "Pipeline not initialized"


def test_apply_scrape_candidate_returns_preview_without_confirming_task():
    pipeline = FakePipeline()

    result = apply_scrape_candidate_for_api(
        pipeline,
        "task-1",
        {
            "provider_type": "tmdb",
            "item_id": "290098",
            "media_type": "movie",
            "language": "zh-CN",
        },
    )

    assert result.code == 200
    assert result.data["task"]["stage"] == "AWAIT_REVIEW"
    assert pipeline.confirmed == []
    assert pipeline.applied_candidates == [{
        "task_id": "task-1",
        "provider_type": "tmdb",
        "item_id": "290098",
        "media_type": "movie",
        "language": "zh-CN",
    }]


def test_apply_scrape_candidate_requires_provider_identity():
    result = apply_scrape_candidate_for_api(
        FakePipeline(),
        "task-1",
        {"provider_type": "tmdb", "media_type": "movie"},
    )

    assert result.code == 400
    assert "item_id" in result.message


def test_reclassify_task_returns_updated_task_payload():
    pipeline = FakePipeline()
    dimensions = {"media_type": "movie", "genre": "action"}

    result = reclassify_task_for_api(pipeline, "task-1", dimensions)

    assert result.code == 200
    assert result.message == "重新分类完成"
    assert result.data == {
        "task": {
            "task_id": "task-1",
            "dimensions": dimensions,
            "status": "CONFIRMING",
        }
    }
    assert pipeline.reclassified == [{"task_id": "task-1", "dimensions": dimensions}]


def test_reclassify_task_requires_dimensions():
    result = reclassify_task_for_api(FakePipeline(), "task-1", {})

    assert result.code == 400
    assert result.message == "缺少 dimensions 参数"


def test_confirm_all_tasks_returns_success_and_failure_counts():
    pipeline = FakePipeline()
    pipeline.confirm_results["task-2"] = False
    pipeline.confirm_exceptions["task-3"] = "bad task"
    task_manager = FakeTaskManager()

    result = confirm_all_tasks_for_api(pipeline, task_manager)

    assert result.code == 200
    assert result.data == {
        "results": [
            {"task_id": "task-1", "success": True},
            {"task_id": "task-2", "success": False},
            {"task_id": "task-3", "success": False, "error": "bad task"},
        ],
        "total": 3,
        "success": 1,
        "failed": 2,
        "conflict_skipped": 0,
    }
    assert result.message == "批量确认完成: 成功 1, 未处理片库冲突 0, 其他失败 2"
    assert task_manager.list_args == {"status": "PENDING", "stage": "AWAIT_REVIEW", "limit": 1000}


def test_confirm_all_tasks_requires_task_manager():
    result = confirm_all_tasks_for_api(FakePipeline(), None)

    assert result.code == 500
    assert result.message == "TaskManager not initialized"


def test_confirm_all_excludes_target_library_conflicts():
    pipeline = FakePipeline()
    manager = FakeTaskManager()
    manager.confirming_tasks = [
        {
            "task_id": "conflict-1",
            "dedup_result": {"is_duplicate": True, "status": "awaiting_user"},
        },
        {"task_id": "normal-1", "dedup_result": {}},
    ]

    result = confirm_all_tasks_for_api(pipeline, manager)

    assert pipeline.confirmed == ["normal-1"]
    assert result.data["conflict_skipped"] == 1
    assert result.data["success"] == 1


def test_confirm_all_excludes_fallback_and_reorganization_tasks():
    pipeline = FakePipeline()
    manager = FakeTaskManager()
    manager.confirming_tasks = [
        {"task_id": "fallback-1", "used_fallback": 1},
        {"task_id": "reorg-1", "task_kind": "REORGANIZE"},
        {"task_id": "normal-1"},
    ]

    result = confirm_all_tasks_for_api(pipeline, manager)

    assert pipeline.confirmed == ["normal-1"]
    assert result.data["conflict_skipped"] == 2
    assert all(
        row.get("error") == "该任务必须打开详情逐项确认"
        for row in result.data["results"][:2]
    )
