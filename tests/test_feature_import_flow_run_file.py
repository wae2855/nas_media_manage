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
    def __init__(self):
        self.created = []

    def create_task(self, **kwargs):
        self.created.append(kwargs)
        return {"task_id": "task-1", **kwargs}


class FakePipeline:
    def __init__(self):
        self.processed = []
        self.run_all_count = 0

    def process_one(self, task):
        self.processed.append(task)

    def run_all(self):
        self.run_all_count += 1


def test_run_batch_starts_background_processing():
    FakeThread.started_targets = []
    pipeline = FakePipeline()

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

    result = run_file_for_api(
        {
            "source_dir": str(source_dir),
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
        }
    ]
    assert pipeline.processed == [{"task_id": "task-1", **task_manager.created[0]}]


def test_run_file_requires_pipeline(tmp_path):
    result = run_file_for_api({}, FakeTaskManager(), None, str(tmp_path / "movie.mkv"))

    assert result.code == 500
    assert result.message == "Pipeline not initialized"


def test_run_file_requires_path():
    result = run_file_for_api({}, FakeTaskManager(), FakePipeline(), "")

    assert result.code == 400
    assert result.message == "Missing 'path' field"


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
