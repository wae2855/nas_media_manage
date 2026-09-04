import threading
import time
from contextlib import contextmanager

from media_importer.features.import_flow.concurrency import (
    TaskConcurrencyGate,
    effective_max_concurrent,
)
from media_importer.features.import_flow.confirm import ConfirmMixin
from media_importer.features.import_flow.runner import PipelineRunner


# Requirement: REQ-20260904-122646
def test_effective_max_concurrent_clamps_legacy_and_invalid_values():
    assert effective_max_concurrent({}) == 1
    assert effective_max_concurrent({"task_queue": {"max_concurrent": 1}}) == 1
    assert effective_max_concurrent({"task_queue": {"max_concurrent": 2}}) == 2
    assert effective_max_concurrent({"task_queue": {"max_concurrent": 99}}) == 2
    assert effective_max_concurrent({"task_queue": {"max_concurrent": 0}}) == 1
    assert effective_max_concurrent({"task_queue": {"max_concurrent": True}}) == 1
    assert effective_max_concurrent({"task_queue": {"max_concurrent": "bad"}}) == 1
    assert effective_max_concurrent({"task_queue": "bad"}) == 1


# Requirement: REQ-20260904-122646
def test_gate_releases_slot_when_worker_raises():
    gate = TaskConcurrencyGate(lambda: {"task_queue": {"max_concurrent": 1}})

    try:
        with gate.slot():
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert gate.active_count == 0
    with gate.slot():
        assert gate.active_count == 1


# Requirement: REQ-20260904-122646
def test_gate_with_limit_one_allows_only_one_active_worker():
    gate = TaskConcurrencyGate(lambda: {"task_queue": {"max_concurrent": 1}})
    release = threading.Event()
    lock = threading.Lock()
    entered = 0
    active = 0
    peak = 0

    def worker():
        nonlocal entered, active, peak
        with gate.slot():
            with lock:
                entered += 1
                active += 1
                peak = max(peak, active)
            release.wait(timeout=2)
            with lock:
                active -= 1

    workers = [threading.Thread(target=worker) for _ in range(3)]
    for thread in workers:
        thread.start()
    deadline = time.monotonic() + 1
    while entered < 1 and time.monotonic() < deadline:
        time.sleep(0.01)

    assert entered == 1
    release.set()
    for thread in workers:
        thread.join(timeout=2)
    assert peak == 1


class _FakeTaskManager:
    def __init__(self, tasks):
        self.conn = object()
        self._tasks = list(tasks)
        self._lock = threading.Lock()
        self.claimed = []

    def get_next_pending(self):
        with self._lock:
            return self._tasks[0] if self._tasks else None

    def list_tasks(self, **_kwargs):
        with self._lock:
            return list(self._tasks)

    def claim_next_pending(self):
        with self._lock:
            if not self._tasks:
                return None
            task = self._tasks.pop(0)
            task["status"] = "RUNNING"
            self.claimed.append(task["task_id"])
            return task


def _bare_runner(config, manager):
    runner = PipelineRunner.__new__(PipelineRunner)
    runner.config = config
    runner.task_manager = manager
    runner.notifier = None
    runner.logger = None
    runner._paused = threading.Event()
    runner._run_all_lock = threading.Lock()
    runner._task_concurrency = TaskConcurrencyGate(lambda: runner.config)
    return runner


# Requirement: REQ-20260904-122646
def test_run_all_processes_two_tasks_without_preclaiming_third(monkeypatch):
    tasks = [{"task_id": f"task-{index}", "status": "PENDING"} for index in range(3)]
    manager = _FakeTaskManager(tasks)
    runner = _bare_runner({"task_queue": {"max_concurrent": 2}}, manager)
    release = threading.Event()
    entered = []
    active = 0
    peak = 0
    lock = threading.Lock()

    def process(task, *, claimed):
        nonlocal active, peak
        assert claimed is True
        with lock:
            active += 1
            peak = max(peak, active)
            entered.append(task["task_id"])
        release.wait(timeout=2)
        with lock:
            active -= 1
        task["status"] = "SUCCESS"
        return True

    runner._process_one_impl = process
    monkeypatch.setattr(
        "media_importer.features.configuration.inspect_processing_support_readiness",
        lambda _config: {"state": "READY", "blocking": []},
    )
    monkeypatch.setattr(
        "media_importer.features.import_flow.runner.db_count_subs",
        lambda *_args: (0, 0),
    )

    worker = threading.Thread(target=runner.run_all)
    worker.start()
    deadline = time.monotonic() + 2
    while len(entered) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)

    assert len(entered) == 2
    assert manager.claimed == ["task-0", "task-1"]
    release.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert len(entered) == 3
    assert peak == 2


# Requirement: REQ-20260904-122646
def test_duplicate_run_all_is_ignored_while_first_loop_is_active():
    runner = _bare_runner({}, _FakeTaskManager([]))
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def run_once():
        calls.append("run")
        entered.set()
        release.wait(timeout=2)

    runner._run_all_once = run_once
    worker = threading.Thread(target=runner.run_all)
    worker.start()
    assert entered.wait(timeout=1)

    assert runner.run_all() is False
    assert calls == ["run"]
    release.set()
    worker.join(timeout=2)
    assert not worker.is_alive()


# Requirement: REQ-20260904-122646
def test_confirm_entry_uses_pipeline_task_slot():
    events = []

    class FakePipeline:
        @contextmanager
        def task_slot(self):
            events.append("enter")
            try:
                yield
            finally:
                events.append("exit")

    pipeline = FakePipeline()
    pipeline._confirm_task_impl = lambda *_args, **_kwargs: events.append("confirm") or True

    assert ConfirmMixin.confirm_task(pipeline, "task-1") is True
    assert events == ["enter", "confirm", "exit"]


# Requirement: REQ-20260904-122646
def test_process_and_confirm_entries_share_same_limit():
    runner = _bare_runner(
        {"task_queue": {"max_concurrent": 1}},
        _FakeTaskManager([]),
    )
    process_entered = threading.Event()
    confirm_entered = threading.Event()
    release = threading.Event()

    def process(_task, *, claimed):
        assert claimed is True
        process_entered.set()
        release.wait(timeout=2)
        return True

    runner._process_one_impl = process
    runner._confirm_task_impl = (
        lambda *_args, **_kwargs: confirm_entered.set() or True
    )
    process_worker = threading.Thread(
        target=runner.process_one,
        args=({"task_id": "task-process"},),
        kwargs={"claimed": True},
    )
    confirm_worker = threading.Thread(
        target=runner.confirm_task,
        args=("task-confirm",),
    )

    process_worker.start()
    assert process_entered.wait(timeout=1)
    confirm_worker.start()
    assert not confirm_entered.wait(timeout=0.1)
    release.set()
    process_worker.join(timeout=2)
    confirm_worker.join(timeout=2)

    assert confirm_entered.is_set()
    assert not process_worker.is_alive()
    assert not confirm_worker.is_alive()
