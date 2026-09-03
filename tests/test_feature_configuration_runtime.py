from media_importer.features.configuration import (
    apply_runtime_config,
    build_notifier,
    restart_watcher,
)


class FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(("info", message))

    def error(self, message):
        self.messages.append(("error", message))


class FakePipeline:
    def __init__(self):
        self.config = None
        self.scraper = None
        self.notifier = None
        self.run_count = 0
        self.cleanup_retry_count = 0
        self.paused = False

    def is_paused(self):
        return self.paused

    def run_all(self):
        self.run_count += 1

    def retry_pending_source_cleanup(self):
        self.cleanup_retry_count += 1
        return []


class FakeWatcher:
    def __init__(self, config, on_new_files=None, on_maintenance=None, logger=None):
        self.config = config
        self.on_new_files = on_new_files
        self.on_maintenance = on_maintenance
        self.logger = logger
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class FakeScraper:
    def __init__(self, config):
        self.config = config


def _ready_config(tmp_path, *, enabled=True):
    paths = [tmp_path / name for name in ("source", "recycle", "target")]
    for path in paths:
        path.mkdir()
    return {
        "source_dir": str(paths[0]),
        "source_policy": {"recycle_dir": str(paths[1])},
        "fallback_dir": str(paths[2]),
        "file_watcher": {"enabled": enabled, "poll_interval": 3},
    }


def test_build_notifier_returns_none_when_disabled():
    assert build_notifier({"hermes": {"enabled": False}}, notifier_factory=object) is None


def test_restart_watcher_stops_existing_and_returns_none_when_disabled():
    old_watcher = FakeWatcher({})
    logger = FakeLogger()

    watcher = restart_watcher(
        {"file_watcher": {"enabled": False}},
        current_watcher=old_watcher,
        logger=logger,
        watcher_factory=FakeWatcher,
    )

    assert watcher is None
    assert old_watcher.stopped is True
    assert ("info", "文件监控已停用（配置 enabled=false）") in logger.messages


def test_restart_watcher_starts_new_watcher_and_callback_runs_pipeline(tmp_path):
    pipeline = FakePipeline()

    watcher = restart_watcher(
        _ready_config(tmp_path),
        pipeline=pipeline,
        logger=FakeLogger(),
        watcher_factory=FakeWatcher,
    )
    watcher.on_new_files({"a.mkv"})
    watcher.on_maintenance()

    assert watcher.started is True
    assert pipeline.run_count == 1
    assert pipeline.cleanup_retry_count == 1


# Requirement: REQ-20260901-001019-2
def test_restart_watcher_starts_for_recognized_remote_source(tmp_path, monkeypatch):
    from media_importer.features.configuration.storage_readiness import MountIdentity

    config = _ready_config(tmp_path)
    source_path = config["source_dir"]
    module = __import__(
        "media_importer.features.configuration.storage_readiness",
        fromlist=["inspect_mount"],
    )
    original = module.inspect_mount

    def source_is_remote(path):
        if str(path) == source_path:
            return MountIdentity(
                realpath=str(path), device=1, filesystem_type="fuse.rclone",
                mount_point=str(path), mount_source="remote:test", locality="remote",
            )
        return original(path)

    monkeypatch.setattr(module, "inspect_mount", source_is_remote)

    watcher = restart_watcher(
        config,
        pipeline=FakePipeline(),
        logger=FakeLogger(),
        watcher_factory=FakeWatcher,
    )

    assert watcher is not None
    assert watcher.started is True


def test_apply_runtime_config_refreshes_pipeline_notifier_and_watcher(tmp_path):
    pipeline = FakePipeline()
    config = _ready_config(tmp_path)

    components = apply_runtime_config(
        config,
        pipeline,
        logger=FakeLogger(),
        notifier_factory=lambda cfg: {"notifier_config": cfg},
        watcher_factory=FakeWatcher,
        scraper_factory=FakeScraper,
    )

    assert pipeline.config is config
    assert isinstance(pipeline.scraper, FakeScraper)
    # Hermes 通知已移除（简洁化 Phase 1）：notifier 恒为 None
    assert pipeline.notifier is None
    assert components.notifier is None
    assert isinstance(components.watcher, FakeWatcher)
    assert components.watcher.started is True


def test_restart_watcher_blocks_when_storage_is_not_green(tmp_path):
    logger = FakeLogger()
    config = {
        "file_watcher": {"enabled": True},
        "source_dir": str(tmp_path / "missing"),
    }

    watcher = restart_watcher(config, logger=logger, watcher_factory=FakeWatcher)

    assert watcher is None
    assert any("保持停用" in message for _level, message in logger.messages)
