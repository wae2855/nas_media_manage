#!/usr/bin/env python3
import os
import threading
from file_scanner import scan_source_dir


class FileWatcher:
    def __init__(self, config: dict, on_new_files=None, logger=None):
        watcher_cfg = config.get("file_watcher", {})
        self.enabled = watcher_cfg.get("enabled", False)
        self.poll_interval = watcher_cfg.get("poll_interval", 10)
        self.ignore_patterns = watcher_cfg.get("ignore_patterns", [])
        self.source_dir = config.get("source_dir", "")
        self.config = config
        self.on_new_files = on_new_files
        self.logger = logger
        self._stop_event = threading.Event()
        self._thread = None
        self._known_files = set()
        self._scan_count = 0

    def _log(self, level: str, message: str):
        if self.logger:
            log_method = getattr(self.logger, level.lower(), self.logger.info)
            log_method(message)

    def _scan_known_files(self) -> set:
        if not self.source_dir or not os.path.isdir(self.source_dir):
            return set()
        known = set()
        try:
            groups = scan_source_dir(self.source_dir, self.config)
            for group in groups:
                known.add(group["video"])
                for sub in group.get("subtitles", []):
                    known.add(sub)
        except Exception as e:
            self._log("warn", f"文件监控扫描失败: {e}")
        return known

    def start(self):
        if not self.enabled:
            self._log("info", "文件监控未启用")
            return

        if self._thread is not None and self._thread.is_alive():
            return

        if not self.source_dir or not os.path.isdir(self.source_dir):
            self._log("warn", f"源目录不存在，文件监控未启动: {self.source_dir}")
            return

        self._known_files = self._scan_known_files()
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
        while not self._stop_event.is_set():
            self._stop_event.wait(self.poll_interval)
            if self._stop_event.is_set():
                break
            self._check_changes()

    def _check_changes(self):
        self._scan_count += 1
        current_files = self._scan_known_files()
        new_files = current_files - self._known_files

        if new_files:
            self._log("info", f"检测到 {len(new_files)} 个新文件")
            for f in new_files:
                self._log("info", f"  新文件: {os.path.basename(f)}")

            self._known_files = current_files

            if self.on_new_files:
                try:
                    self.on_new_files(new_files)
                except Exception as e:
                    self._log("warn", f"新文件回调执行失败: {e}")
        else:
            removed = self._known_files - current_files
            if removed:
                self._known_files = current_files

    @property
    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "running": self._thread is not None and self._thread.is_alive(),
            "source_dir": self.source_dir,
            "poll_interval": self.poll_interval,
            "known_files": len(self._known_files),
            "scan_count": self._scan_count
        }
