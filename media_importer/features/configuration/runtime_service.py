from dataclasses import dataclass
from typing import Callable


@dataclass
class RuntimeComponents:
    notifier: object = None
    watcher: object = None


def apply_runtime_config(
    config: dict,
    pipeline,
    current_watcher=None,
    logger=None,
    notifier_factory: Callable = None,
    watcher_factory: Callable = None,
    scraper_factory: Callable = None,
) -> RuntimeComponents:
    if pipeline:
        pipeline.config = config
        scraper_cls = scraper_factory or _default_scraper_factory()
        pipeline.scraper = scraper_cls(config)
        if getattr(pipeline, "copier", None) is not None:
            pipeline.copier = type(pipeline.copier)(config.get("temp_dir", ""))

    notifier = build_notifier(config, notifier_factory=notifier_factory)
    if pipeline:
        pipeline.notifier = notifier

    watcher = restart_watcher(
        config,
        current_watcher=current_watcher,
        pipeline=pipeline,
        logger=logger,
        watcher_factory=watcher_factory,
    )
    return RuntimeComponents(notifier=notifier, watcher=watcher)


def build_notifier(config: dict, notifier_factory: Callable = None):
    hermes_cfg = config.get("hermes", {})
    if not hermes_cfg.get("enabled", False):
        return None
    factory = notifier_factory or _default_notifier_factory()
    return factory(config)


def restart_watcher(
    config: dict,
    current_watcher=None,
    pipeline=None,
    logger=None,
    watcher_factory: Callable = None,
):
    if current_watcher:
        current_watcher.stop()

    watcher_cfg = config.get("file_watcher", {})
    if not watcher_cfg.get("enabled", False):
        _log(logger, "info", "文件监控已停用（配置 enabled=false）")
        return None

    def on_new_files(new_files):
        if pipeline and not pipeline.is_paused():
            try:
                pipeline.run_all()
            except Exception as exc:
                _log(logger, "error", "批量处理异常: " + str(exc))

    factory = watcher_factory or _default_watcher_factory()
    watcher = factory(config, on_new_files=on_new_files, logger=logger)
    watcher.start()
    _log(
        logger,
        "info",
        "文件监控已应用新配置并重启: "
        f"enabled={watcher_cfg.get('enabled')}, "
        f"poll_interval={watcher_cfg.get('poll_interval')}s",
    )
    return watcher


def _log(logger, level: str, message: str):
    if not logger:
        return
    log_method = getattr(logger, level, None) or getattr(logger, "info", None)
    if log_method:
        log_method(message)


def _default_notifier_factory():
    from media_importer.notify.hermes_hook import HermesNotifier
    return HermesNotifier


def _default_watcher_factory():
    from media_importer.monitor.file_watcher import FileWatcher
    return FileWatcher


def _default_scraper_factory():
    from media_importer.features.scraping import LLMScraper
    return LLMScraper
