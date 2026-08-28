#!/usr/bin/env python3
import json
import logging
import os
import sys
import threading
from collections import deque
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional


class Logger:
    MAX_BUFFER_SIZE = 500

    def __init__(self, level: str = "INFO", fmt: str = "json",
                 log_dir: str = "logs", max_size_mb: int = 100,
                 backup_count: int = 5):
        self.level = self._parse_level(level)
        self.format = fmt
        self.log_dir = log_dir
        self.max_size_mb = max_size_mb
        self.backup_count = backup_count
        self._file_handler_enabled = True

        try:
            os.makedirs(log_dir, exist_ok=True)
        except (OSError, PermissionError) as e:
            print(f"WARNING: 无法创建日志目录 {log_dir}: {e}，将仅输出到控制台", file=sys.stderr)
            self._file_handler_enabled = False

        self.logger = logging.getLogger("media_importer")
        self.logger.setLevel(self.level)
        self.logger.handlers.clear()

        self._log_buffer = deque(maxlen=self.MAX_BUFFER_SIZE)
        self._buffer_lock = threading.Lock()

        if self._file_handler_enabled:
            self._setup_file_handler()
        self._setup_console_handler()

    def _parse_level(self, level_str: str) -> int:
        levels = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARN": logging.WARNING,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR
        }
        return levels.get(level_str.upper(), logging.INFO)

    def _setup_file_handler(self):
        log_file = os.path.join(self.log_dir, "media_importer.log")
        max_bytes = self.max_size_mb * 1024 * 1024

        handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        handler.setLevel(self.level)

        if self.format == "json":
            formatter = JsonFormatter()
        else:
            formatter = TextFormatter()

        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def _setup_console_handler(self):
        handler = logging.StreamHandler()
        handler.setLevel(self.level)

        formatter = TextFormatter()
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def _log(self, level: str, msg: str, **kwargs):
        extra = {
            "timestamp": datetime.now().isoformat(),
            "log_level": level.upper()
        }
        extra.update(kwargs)

        entry = {
            "time": extra["timestamp"],
            "level": level.upper(),
            "message": msg
        }
        if kwargs.get("task_id"):
            entry["task_id"] = kwargs["task_id"]
        if kwargs.get("step"):
            entry["step"] = kwargs["step"]

        with self._buffer_lock:
            self._log_buffer.append(entry)

        log_method = getattr(self.logger, level.lower())
        log_method(msg, extra=extra)

    def debug(self, msg: str, **kwargs):
        self._log("debug", msg, **kwargs)

    def info(self, msg: str, **kwargs):
        self._log("info", msg, **kwargs)

    def warn(self, msg: str, **kwargs):
        self._log("warning", msg, **kwargs)

    def warning(self, msg: str, **kwargs):
        self._log("warning", msg, **kwargs)

    def error(self, msg: str, **kwargs):
        self._log("error", msg, **kwargs)

    def step_log(self, task_id: str, step: str, level: str, message: str):
        log_entry = {
            "task_id": task_id,
            "step": step,
            "level": level.upper(),
            "message": message,
            "timestamp": datetime.now().isoformat()
        }

        if level.upper() == "DEBUG":
            self.debug(message, task_id=task_id, step=step)
        elif level.upper() == "INFO":
            self.info(message, task_id=task_id, step=step)
        elif level.upper() in ["WARN", "WARNING"]:
            self.warn(message, task_id=task_id, step=step)
        elif level.upper() == "ERROR":
            self.error(message, task_id=task_id, step=step)

        return log_entry

    def check_rotate(self):
        for handler in self.logger.handlers:
            if isinstance(handler, RotatingFileHandler):
                handler.doRollover()

    def get_recent_logs(self, limit: int = 100, task_id: Optional[str] = None) -> list:
        with self._buffer_lock:
            logs = list(self._log_buffer)
        if task_id:
            logs = [entry for entry in logs if entry.get("task_id") == task_id]
        return logs[-limit:]


class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "time": getattr(record, "timestamp", datetime.now().isoformat()),
            "level": record.levelname,
            "message": record.getMessage()
        }

        if hasattr(record, "task_id") and record.task_id:
            log_data["task_id"] = record.task_id
        if hasattr(record, "step") and record.step:
            log_data["step"] = record.step

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def format(self, record):
        timestamp = getattr(record, "timestamp", datetime.now().isoformat())

        parts = [
            f"[{timestamp}]",
            f"[{record.levelname}]",
            record.getMessage()
        ]

        if hasattr(record, "task_id") and record.task_id:
            parts.insert(2, f"[task:{record.task_id}]")
        if hasattr(record, "step") and record.step:
            parts.insert(3, f"[step:{record.step}]")

        if record.exc_info:
            parts.append("\n" + self.formatException(record.exc_info))

        return " ".join(parts)


_default_logger = None


def get_logger(config: Optional[dict] = None) -> Optional[Logger]:
    global _default_logger
    if _default_logger is None and config is not None:
        logging_config = config.get("logging", {})
        _default_logger = Logger(
            level=logging_config.get("level", "INFO"),
            fmt=logging_config.get("format", "json"),
            log_dir=config.get("log_dir", "logs"),
            max_size_mb=logging_config.get("max_size_mb", 100),
            backup_count=logging_config.get("backup_count", 5)
        )
    return _default_logger
