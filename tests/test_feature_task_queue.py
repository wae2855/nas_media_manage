from media_importer.features.tasks import (
    clear_tasks_for_api,
    get_queue_status_for_api,
    pause_queue_for_api,
    resume_queue_for_api,
    retry_all_failed_for_api,
    retry_task_for_api,
)


class FakeThread:
    started_targets = []

    def __init__(self, target, daemon):
        self.target = target
        self.daemon = daemon

    def start(self):
        self.started_targets.append(self.target)
        self.target()


class FakeTaskManager:
    def __init__(self):
        self.cleared_status = "unset"
        self.retry_result = {"task_id": "task-1", "status": "PENDING"}
        self.retry_all_result = [
            {"task_id": "task-1", "status": "PENDING"},
            {"task_id": "task-2", "status": "PENDING"},
        ]
        self.counts = {"PENDING": 2, "FAILED": 0}

    def clear_tasks(self, status=None, stage=None):
        self.cleared_status = status
        self.cleared_stage = stage

    def retry_task(self, task_id):
        if task_id == "missing":
            return None
        return self.retry_result

    def retry_all_failed(self):
        return self.retry_all_result

    def count_by_status(self):
        return self.counts


class FakePipeline:
    def __init__(self, paused=False):
        self.paused = paused
        self.processed = []
        self.run_all_count = 0
        self.pause_count = 0
        self.resume_count = 0

    def is_paused(self):
        return self.paused

    def process_one(self, task):
        self.processed.append(task)

    def run_all(self):
        self.run_all_count += 1

    def pause(self):
        self.pause_count += 1
        self.paused = True

    def resume(self):
        self.resume_count += 1
        self.paused = False


class FakeMetrics:
    def __init__(self):
        self.queue_paused = None

    def set_queue_paused(self, paused):
        self.queue_paused = paused


def test_clear_tasks_normalizes_all_status():
    task_manager = FakeTaskManager()

    result = clear_tasks_for_api(task_manager, "all")

    assert result.code == 200
    assert result.data == {"status": "all", "stage": None}
    assert task_manager.cleared_status is None


def test_clear_tasks_rejects_invalid_status():
    task_manager = FakeTaskManager()

    result = clear_tasks_for_api(task_manager, "wat")

    assert result.code == 400
    assert result.message == "Invalid status: WAT"
    assert task_manager.cleared_status == "unset"


def test_retry_task_starts_pipeline_when_available():
    FakeThread.started_targets = []
    task_manager = FakeTaskManager()
    pipeline = FakePipeline(paused=False)

    result = retry_task_for_api(
        task_manager,
        pipeline,
        "task-1",
        thread_factory=FakeThread,
    )

    assert result.code == 200
    assert result.data == {"task": task_manager.retry_result}
    assert pipeline.processed == [task_manager.retry_result]
    assert len(FakeThread.started_targets) == 1


def test_retry_task_does_not_start_paused_pipeline():
    FakeThread.started_targets = []
    task_manager = FakeTaskManager()
    pipeline = FakePipeline(paused=True)

    result = retry_task_for_api(
        task_manager,
        pipeline,
        "task-1",
        thread_factory=FakeThread,
    )

    assert result.code == 200
    assert pipeline.processed == []
    assert FakeThread.started_targets == []


def test_retry_task_returns_bad_request_for_missing_task():
    result = retry_task_for_api(FakeTaskManager(), FakePipeline(), "missing")

    assert result.code == 400
    assert result.message == "任务不存在或当前状态不可重试: missing"


def test_retry_all_failed_starts_batch_and_returns_task_ids():
    FakeThread.started_targets = []
    task_manager = FakeTaskManager()
    pipeline = FakePipeline(paused=False)

    result = retry_all_failed_for_api(
        task_manager,
        pipeline,
        thread_factory=FakeThread,
    )

    assert result.code == 200
    assert result.data == {"retried_count": 2, "task_ids": ["task-1", "task-2"]}
    assert result.message == "已重试 2 个失败任务并开始执行"
    assert pipeline.run_all_count == 1
    assert len(FakeThread.started_targets) == 1


def test_pause_resume_and_status_payloads():
    pipeline = FakePipeline(paused=False)
    metrics = FakeMetrics()
    task_manager = FakeTaskManager()

    pause_result = pause_queue_for_api(pipeline, metrics)
    status_result = get_queue_status_for_api(pipeline, task_manager)

    assert pause_result.code == 200
    assert pause_result.message == "Queue paused"
    assert pipeline.pause_count == 1
    assert metrics.queue_paused is True
    assert status_result.data == {"paused": True, "by_status": task_manager.counts}

    resume_result = resume_queue_for_api(pipeline, metrics)

    assert resume_result.code == 200
    assert resume_result.message == "Queue resumed"
    assert pipeline.resume_count == 1
    assert metrics.queue_paused is False
