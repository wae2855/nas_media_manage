from media_importer.features.tasks import (
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

    def confirm_task(self, task_id, confirmed_title=None, override_source=None):
        self.confirmed.append(task_id)
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
    }
    assert result.message == "批量确认完成: 成功 1, 失败 2"
    assert task_manager.list_args == {"status": "PENDING", "stage": "AWAIT_REVIEW", "limit": 1000}


def test_confirm_all_tasks_requires_task_manager():
    result = confirm_all_tasks_for_api(FakePipeline(), None)

    assert result.code == 500
    assert result.message == "TaskManager not initialized"
