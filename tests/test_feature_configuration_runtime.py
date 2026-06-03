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
        self.copier = FakeCopier("old")
        self.notifier = None
        self.run_count = 0
        self.paused = False

    def is_paused(self):
        return self.paused

    def run_all(self):
        self.run_count += 1


class FakeCopier:
    def __init__(self, temp_dir):
        self.temp_dir = temp_dir


class FakeWatcher:
    def __init__(self, config, on_new_files=None, logger=None):
        self.config = config
        self.on_new_files = on_new_files
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


def test_restart_watcher_starts_new_watcher_and_callback_runs_pipeline():
    pipeline = FakePipeline()

    watcher = restart_watcher(
        {"file_watcher": {"enabled": True, "poll_interval": 3}},
        pipeline=pipeline,
        logger=FakeLogger(),
        watcher_factory=FakeWatcher,
    )
    watcher.on_new_files({"a.mkv"})

    assert watcher.started is True
    assert pipeline.run_count == 1


def test_apply_runtime_config_refreshes_pipeline_notifier_and_watcher():
    pipeline = FakePipeline()
    config = {
        "temp_dir": "/tmp/new",
        "hermes": {"enabled": True},
        "file_watcher": {"enabled": True},
    }

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
    assert pipeline.copier.temp_dir == "/tmp/new"
    assert pipeline.notifier == {"notifier_config": config}
    assert components.notifier == {"notifier_config": config}
    assert isinstance(components.watcher, FakeWatcher)
    assert components.watcher.started is True
