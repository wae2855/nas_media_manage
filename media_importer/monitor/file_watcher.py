#!/usr/bin/env python3
import os
import threading
import time

from media_importer.features.import_flow import scan_source_dir
from media_importer.features.recycle import recycle_cleanup

RECYCLE_MAINTENANCE_INTERVAL_SECONDS = 24 * 60 * 60


class FileWatcher:
    def __init__(
        self,
        config: dict,
        on_new_files=None,
        on_maintenance=None,
        logger=None,
    ):
        watcher_cfg = config.get("file_watcher", {})
        self.enabled = watcher_cfg.get("enabled", False)
        try:
            poll_interval = int(watcher_cfg.get("poll_interval", 300))
        except (TypeError, ValueError):
            poll_interval = 300
        self.poll_interval = max(
            10,
            min(3600, poll_interval),
        )
        self.stability_window_seconds = max(
            30,
            min(1800, int(watcher_cfg.get("stability_window_seconds", 120))),
        )
        self.ignore_patterns = watcher_cfg.get("ignore_patterns", [])
        self.source_dir = config.get("source_dir", "")
        self.config = config
        self.on_new_files = on_new_files
        self.on_maintenance = on_maintenance
        self.logger = logger
        self._stop_event = threading.Event()
        self._thread = None
        self._known_files = set()
        self._scan_count = 0
        self._observations = {}
        self._source_online = False
        self._support_ready = False
        self._support_blocking_reasons = []
        self._source_blocking_reasons = []
        self._next_recycle_maintenance = (
            time.monotonic() + RECYCLE_MAINTENANCE_INTERVAL_SECONDS
        )

    def _log(self, level: str, message: str):
        if self.logger:
            log_method = getattr(self.logger, level.lower(), self.logger.info)
            log_method(message)

    def _scan_known_files(self):
        if not self.source_dir or not os.path.isdir(self.source_dir):
            return None
        known = set()
        try:
            groups = scan_source_dir(self.source_dir, self.config)
            for group in groups:
                known.add(group["video_path"])
                for sub in group.get("subtitles", []):
                    known.add(sub)
        except Exception as e:
            self._log("warn", f"文件监控扫描失败: {e}")
            return None
        if self.ignore_patterns:
            import fnmatch
            known = {
                p for p in known
                if not any(fnmatch.fnmatch(os.path.basename(p), pat) or
                           fnmatch.fnmatch(p, pat) for pat in self.ignore_patterns)
            }
        return known

    @staticmethod
    def _readiness_reasons(readiness: dict) -> list[str]:
        from media_importer.features.configuration import automatic_blocking_reasons

        return automatic_blocking_reasons(readiness)

    def _source_ready_for_scan(self) -> bool:
        from media_importer.features.configuration import inspect_source_scan_readiness

        readiness = inspect_source_scan_readiness(self.config)
        if readiness.get("automatic_allowed"):
            self._source_blocking_reasons = []
            return True
        self._source_blocking_reasons = self._readiness_reasons(readiness)
        self._log("error", "来源目录挂载身份或读取权限已变化，自动扫描已暂停")
        return False

    def _processing_support_ready(self) -> bool:
        from media_importer.features.configuration import (
            inspect_processing_support_readiness,
        )

        readiness = inspect_processing_support_readiness(self.config)
        self._support_ready = bool(readiness.get("automatic_allowed"))
        self._support_blocking_reasons = self._readiness_reasons(readiness)
        if self._support_ready:
            return True
        self._log("error", "来源处理、回收或应用目录状态已变化，本次候选保留并等待恢复")
        return False

    def _stable_new_files(self, candidates: set, now: float) -> set:
        stable = set()
        for path in candidates:
            try:
                stat = os.stat(path, follow_symlinks=False)
            except OSError:
                self._observations.pop(path, None)
                continue
            version = (stat.st_size, stat.st_mtime_ns)
            previous = self._observations.get(path)
            if not previous or previous[0] != version:
                self._observations[path] = (version, now, 1)
                continue
            observed_at = previous[1]
            observation_count = previous[2] + 1
            self._observations[path] = (version, observed_at, observation_count)
            if observation_count >= 2 and now - observed_at >= self.stability_window_seconds:
                stable.add(path)
        return stable

    def start(self):
        if not self.enabled:
            self._log("info", "文件监控未启用")
            return

        if self._thread is not None and self._thread.is_alive():
            return

        if not self.source_dir or not os.path.isdir(self.source_dir):
            self._log("warn", f"源目录不存在，文件监控未启动: {self.source_dir}")
            return
        if not self._processing_support_ready():
            return

        initial_files = self._scan_known_files()
        if initial_files is None:
            self._log("warn", f"源目录当前不可读取，文件监控未启动: {self.source_dir}")
            return
        self._known_files = initial_files
        self._source_online = True
        self._log("info",
            f"文件监控启动: 目录={self.source_dir}, "
            f"轮询间隔={self.poll_interval}s, "
            f"已知文件={len(self._known_files)}")

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._log("info", "文件监控已停止")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _watch_loop(self):
        self._run_maintenance()
        while not self._stop_event.is_set():
            self._stop_event.wait(self.poll_interval)
            if self._stop_event.is_set():
                break
            self._check_changes()

    def _check_changes(self):
        self._scan_count += 1
        if not self._source_ready_for_scan():
            self._source_online = False
            return
        current_files = self._scan_known_files()
        if current_files is None:
            if self._source_online:
                self._log("error", f"源目录离线或挂载不可读，暂停扫描且保留已知文件: {self.source_dir}")
            self._source_online = False
            return

        if not self._source_online:
            self._log("info", f"源目录恢复，重新核对文件: {self.source_dir}")
        self._source_online = True
        candidates = current_files - self._known_files
        now = time.monotonic()
        new_files = self._stable_new_files(candidates, now)

        if new_files:
            if not self._processing_support_ready():
                return
            self._log("info", f"检测到 {len(new_files)} 个新文件")
            for f in new_files:
                self._log("info", f"  新文件: {os.path.basename(f)}")

            if self.on_new_files:
                try:
                    self.on_new_files(new_files)
                except Exception as e:
                    self._log("warn", f"新文件回调执行失败: {e}")
                    return
            self._known_files.update(new_files)
            for path in new_files:
                self._observations.pop(path, None)
        else:
            removed = self._known_files - current_files
            if removed:
                self._known_files.difference_update(removed)
            for path in list(self._observations):
                if path not in current_files:
                    self._observations.pop(path, None)

        self._maybe_cleanup_recycle(now=now)
        self._run_maintenance()

    def _run_maintenance(self):
        if not self.on_maintenance:
            return
        try:
            self.on_maintenance()
        except Exception as error:
            self._log("warn", f"来源处置维护失败，文件已保留并等待下次重试: {error}")

    def _maybe_cleanup_recycle(self, *, now: float | None = None):
        current = time.monotonic() if now is None else now
        if current < self._next_recycle_maintenance:
            return
        self._next_recycle_maintenance = current + RECYCLE_MAINTENANCE_INTERVAL_SECONDS
        recycle_dir = self.config.get("source_policy", {}).get("recycle_dir", "")
        retention_days = self.config.get("source_policy", {}).get("recycle_retention_days", 0)
        if recycle_dir and retention_days > 0:
            from media_importer.features.configuration.storage_topology import (
                configured_library_roots,
            )

            deleted = recycle_cleanup(
                recycle_dir,
                retention_days,
                protected_roots=configured_library_roots(self.config),
                protected_roots_canonical=True,
            )
            if deleted:
                self._log("info", f"回收站过期清理: 删除 {len(deleted)} 个文件")

    @property
    def status(self) -> dict:
        running = self._thread is not None and self._thread.is_alive()
        automatic_allowed = bool(running and self._source_online and self._support_ready)
        blocking_reasons = (
            self._source_blocking_reasons
            if not self._source_online else self._support_blocking_reasons
        )
        return {
            "enabled": self.enabled,
            "running": running,
            "automatic_allowed": automatic_allowed,
            "blocking_reasons": list(blocking_reasons),
            "source_dir": self.source_dir,
            "poll_interval": self.poll_interval,
            "known_files": len(self._known_files),
            "scan_count": self._scan_count,
            "source_online": self._source_online,
            "stability_window_seconds": self.stability_window_seconds,
        }
