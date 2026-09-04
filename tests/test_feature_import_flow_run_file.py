import threading

from media_importer.core.task_manager import TaskManager
from media_importer.features.import_flow import run_batch_for_api, run_file_for_api


class FakeThread:
    started_targets = []

    def __init__(self, target, daemon):
        self.target = target
        self.daemon = daemon

    def start(self):
        self.started_targets.append(self.target)
        self.target()


class FakeTaskManager:
    def __init__(self, existing=None):
        self.created = []
        self.existing = existing

    def create_or_reuse_source_task(self, **kwargs):
        if self.existing:
            return {
                "created": False,
                "task": self.existing,
                "task_id": self.existing["task_id"],
                "old_status": self.existing["status"],
                "action": "SKIP",
                "reason": "同一路径已有失败任务，请在原任务上手动重试",
            }
        self.created.append(kwargs)
        task = {"task_id": "task-1", **kwargs}
        return {"created": True, "task": task, "action": "CREATE"}


class FakePipeline:
    def __init__(self, config=None):
        self.processed = []
        self.run_all_count = 0
        self.config = config or {}

    def process_one(self, task):
        self.processed.append(task)

    def run_all(self):
        self.run_all_count += 1


def test_run_batch_starts_background_processing():
    FakeThread.started_targets = []
    import tempfile
    from pathlib import Path

    base = Path(tempfile.mkdtemp())
    directories = [base / name for name in ("source", "recycle", "target")]
    for directory in directories:
        directory.mkdir()
    pipeline = FakePipeline({
        "source_dir": str(directories[0]),
        "source_policy": {"recycle_dir": str(directories[1])},
        "fallback_dir": str(directories[2]),
    })

    result = run_batch_for_api(pipeline, thread_factory=FakeThread)

    assert result.code == 202
    assert result.message == "已启动批量扫描，新任务稍后会出现在工作台"
    assert len(FakeThread.started_targets) == 1
    assert pipeline.run_all_count == 1


def test_run_batch_requires_pipeline():
    result = run_batch_for_api(None)

    assert result.code == 500
    assert result.message == "Pipeline not initialized"


def test_run_file_starts_single_file_processing(tmp_path):
    FakeThread.started_targets = []
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    video_path = source_dir / "movie.mkv"
    video_path.write_text("video")
    task_manager = FakeTaskManager()
    pipeline = FakePipeline()

    recycle_dir = tmp_path / "recycle"
    target_dir = tmp_path / "target"
    for directory in (recycle_dir, target_dir):
        directory.mkdir()

    result = run_file_for_api(
        {
            "source_dir": str(source_dir),
            "source_policy": {"recycle_dir": str(recycle_dir)},
            "fallback_dir": str(target_dir),
            "video_extensions": ["mkv"],
            "subtitle_extensions": ["srt"],
        },
        task_manager,
        pipeline,
        str(video_path),
        thread_factory=FakeThread,
    )

    assert result.code == 202
    assert result.message == f"已启动处理: {video_path}"
    assert len(FakeThread.started_targets) == 1
    assert task_manager.created == [
        {
            "video_path": str(video_path),
            "video_file": "movie.mkv",
            "subtitle_files": [],
            "file_size_mb": video_path.stat().st_size / (1024 * 1024),
            "source_unit_id": "",
            "source_fingerprint": task_manager.created[0]["source_fingerprint"],
            "source_file_size": video_path.stat().st_size,
            "source_mtime": task_manager.created[0]["source_mtime"],
        }
    ]
    assert pipeline.processed == [{"task_id": "task-1", **task_manager.created[0]}]
    assert result.data == {"task_id": "task-1"}


def test_run_file_reuses_existing_task_without_starting_worker(tmp_path):
    FakeThread.started_targets = []
    source_dir = tmp_path / "source"
    recycle_dir = tmp_path / "recycle"
    target_dir = tmp_path / "target"
    for directory in (source_dir, recycle_dir, target_dir):
        directory.mkdir()
    video_path = source_dir / "Episode.S01E04.mkv"
    video_path.write_text("video")
    existing = {
        "task_id": "failed-task",
        "status": "FAILED",
        "stage": "DONE",
    }
    task_manager = FakeTaskManager(existing=existing)
    pipeline = FakePipeline()

    result = run_file_for_api(
        {
            "source_dir": str(source_dir),
            "source_policy": {"recycle_dir": str(recycle_dir)},
            "fallback_dir": str(target_dir),
            "video_extensions": ["mkv"],
        },
        task_manager,
        pipeline,
        str(video_path),
        thread_factory=FakeThread,
    )

    assert result.code == 409
    assert result.data == {
        "task_id": "failed-task",
        "status": "FAILED",
        "stage": "DONE",
        "action": "SKIP",
    }
    assert "原任务" in result.message
    assert FakeThread.started_targets == []
    assert pipeline.processed == []


def test_scan_and_manual_creation_race_reuses_one_task(tmp_path):
    FakeThread.started_targets = []
    source_dir = tmp_path / "source"
    recycle_dir = tmp_path / "recycle"
    target_dir = tmp_path / "target"
    data_dir = tmp_path / "data"
    for directory in (source_dir, recycle_dir, target_dir, data_dir):
        directory.mkdir()
    video_path = source_dir / "Episode.S01E05.mkv"
    video_path.write_bytes(b"stable-video")
    config = {
        "source_dir": str(source_dir),
        "source_policy": {"recycle_dir": str(recycle_dir)},
        "fallback_dir": str(target_dir),
        "video_extensions": ["mkv"],
    }
    task_manager = TaskManager(str(data_dir), config=config)
    pipeline = FakePipeline(config)
    barrier = threading.Barrier(2)
    outcomes = []

    def manual_entry():
        barrier.wait()
        outcomes.append(run_file_for_api(
            config,
            task_manager,
            pipeline,
            str(video_path),
            thread_factory=FakeThread,
        ))

    def scanner_entry():
        barrier.wait()
        stat = video_path.stat()
        outcomes.append(task_manager.create_or_reuse_source_task(
            video_path=str(video_path),
            video_file=video_path.name,
            file_size_mb=stat.st_size / (1024 * 1024),
            source_fingerprint="scanner-fingerprint",
            source_file_size=stat.st_size,
        ))

    threads = [threading.Thread(target=manual_entry), threading.Thread(target=scanner_entry)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    rows = task_manager.list_all_tasks(limit=20)
    assert len(outcomes) == 2
    assert len(rows) == 1
    assert {getattr(item, "code", None) for item in outcomes if hasattr(item, "code")} <= {
        202,
        409,
    }
    assert len(FakeThread.started_targets) <= 1


def test_run_file_requires_pipeline(tmp_path):
    result = run_file_for_api({}, FakeTaskManager(), None, str(tmp_path / "movie.mkv"))

    assert result.code == 500
    assert result.message == "Pipeline not initialized"


def test_run_file_requires_path():
    result = run_file_for_api({}, FakeTaskManager(), FakePipeline(), "")

    assert result.code == 400
    assert result.message == "Missing 'path' field"


def test_run_file_blocks_when_storage_is_not_ready(tmp_path):
    video_path = tmp_path / "movie.mkv"
    video_path.write_text("video")

    result = run_file_for_api(
        {"source_dir": str(tmp_path), "video_extensions": ["mkv"]},
        FakeTaskManager(),
        FakePipeline(),
        str(video_path),
    )

    assert result.code == 409
    assert "存储检查" in result.message


def test_run_file_rejects_file_outside_source_dir(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    video_path = other_dir / "movie.mkv"
    video_path.write_text("video")

    result = run_file_for_api(
        {"source_dir": str(source_dir), "video_extensions": ["mkv"]},
        FakeTaskManager(),
        FakePipeline(),
        str(video_path),
    )

    assert result.code == 400
    assert result.message == "路径校验失败: Path not in allowed directories"


def test_run_file_rejects_invalid_extension(tmp_path):
    video_path = tmp_path / "movie.txt"
    video_path.write_text("video")

    result = run_file_for_api(
        {"video_extensions": ["mkv"]},
        FakeTaskManager(),
        FakePipeline(),
        str(video_path),
    )

    assert result.code == 400
    assert result.message.startswith("文件类型校验失败: 不允许的文件扩展名: .txt")


def test_run_file_rejects_missing_file(tmp_path):
    video_path = tmp_path / "missing.mkv"

    result = run_file_for_api(
        {"video_extensions": ["mkv"]},
        FakeTaskManager(),
        FakePipeline(),
        str(video_path),
    )

    assert result.code == 404
    assert result.message == f"File not found: {video_path}"
