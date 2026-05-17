#!/usr/bin/env python3
import json
import os
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dataclasses import asdict

from config_loader import load_config, mask_sensitive
from task_manager import TaskManager, VALID_STATUSES
from pipeline import PipelineRunner
from metrics import Metrics, get_metrics
from logger import get_logger, Logger
from hermes_hook import HermesNotifier
from file_watcher import FileWatcher


_global_pipeline = None
_global_task_manager = None
_global_metrics = None
_global_logger = None
_global_notifier = None
_config = None


def json_response(handler, code: int, data=None, message: str = "", code_str: str = None):
    status_map = {
        200: "success",
        201: "created",
        400: "bad_request",
        404: "not_found",
        500: "internal_error"
    }
    status = code_str or status_map.get(code, "error")
    body = {
        "code": code,
        "status": status,
        "message": message,
        "data": data
    }
    body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body_bytes)))
    handler.send_header("X-Request-ID", getattr(handler, "_request_id", ""))
    handler.end_headers()
    handler.wfile.write(body_bytes)
    handler.wfile.flush()


def read_json_body(handler) -> dict:
    try:
        length = int(handler.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        body = handler.rfile.read(length)
        return json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


class APIHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/health":
            self._health()
        elif path == "/api/metrics":
            self._metrics()
        elif path == "/api/config":
            self._config()
        elif path == "/api/tasks":
            self._list_tasks(query)
        elif path.startswith("/api/tasks/"):
            parts = path.split("/")
            if len(parts) >= 5:
                task_id = parts[3]
                self._get_task(task_id)
            else:
                json_response(self, 404, message="Not found")
        elif path == "/api/queue/status":
            self._queue_status()
        elif path == "/api/logs":
            self._logs(query)
        else:
            json_response(self, 404, message=f"Endpoint not found: {path}")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = read_json_body(self)

        if path == "/api/run":
            self._run_batch()
        elif path == "/api/run/file":
            self._run_file(body)
        elif path.startswith("/api/tasks/") and path.endswith("/retry"):
            parts = path.split("/")
            if len(parts) >= 5:
                task_id = parts[3]
                self._retry_task(task_id)
            else:
                json_response(self, 400, message="Invalid retry path")
        elif path == "/api/tasks/clear":
            self._clear_tasks(body)
        elif path == "/api/queue/pause":
            self._queue_pause()
        elif path == "/api/queue/resume":
            self._queue_resume()
        elif path == "/api/queue/retry-all":
            self._queue_retry_all()
        elif path == "/api/config/reload":
            self._config_reload()
        else:
            json_response(self, 404, message=f"Endpoint not found: {path}")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/tasks/"):
            suffix = path[len("/api/tasks/"):]
            if "/" in suffix:
                json_response(self, 404, message=f"Endpoint not found: {path}")
                return
            task_id = suffix
            if not task_id:
                json_response(self, 400, message="Missing task_id")
                return
            self._delete_task(task_id)
        else:
            json_response(self, 404, message=f"Endpoint not found: {path}")

    def _health(self):
        from safety import check_write_permission, check_read_permission
        checks = {}
        overall = "ok"

        try:
            source_dir = _config.get("source_dir", "")
            if os.path.isdir(source_dir):
                ok, _ = check_read_permission(os.path.join(source_dir, "."))
                checks["source_dir"] = "ok" if ok else "no_read_permission"
            else:
                checks["source_dir"] = "error"
        except Exception:
            checks["source_dir"] = "error"
            overall = "degraded"

        try:
            temp_dir = _config.get("temp_dir", "")
            if os.path.isdir(temp_dir):
                ok, _ = check_write_permission(temp_dir)
                checks["temp_dir"] = "ok" if ok else "no_write_permission"
            else:
                checks["temp_dir"] = "error"
        except Exception:
            checks["temp_dir"] = "error"
            overall = "degraded"

        try:
            llm_config = _config.get("llm", {})
            api_key = llm_config.get("api_key", "")
            checks["llm_api"] = "ok" if api_key else "error"
        except Exception:
            checks["llm_api"] = "error"
            overall = "degraded"

        try:
            hermes_enabled = _config.get("hermes", {}).get("enabled", False)
            checks["hermes"] = "ok" if hermes_enabled else "disabled"
        except Exception:
            checks["hermes"] = "error"
            overall = "degraded"

        try:
            disk_check_dir = _config.get("temp_dir", "/tmp")
            stat = os.statvfs(disk_check_dir)
            free_gb = stat.f_bavail * stat.f_frsize / (1024**3)
            checks["disk_space"] = "ok" if free_gb > 1 else "low"
        except Exception:
            checks["disk_space"] = "error"
            overall = "degraded"

        if "error" in checks.values():
            overall = "degraded"

        json_response(self, 200, data={
            "status": overall,
            "checks": checks,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        }, message=f"Health check: {overall}")

    def _metrics(self):
        m = get_metrics()
        counts = _global_task_manager.count_by_status() if _global_task_manager else {}
        json_response(self, 200, data={
            **m.to_dict(),
            "queue_by_status": counts
        })

    def _config(self):
        masked = mask_sensitive(_config) if _config else {}
        json_response(self, 200, data={"config": masked})

    def _list_tasks(self, query):
        status = query.get("status", [None])[0]
        limit = int(query.get("limit", [20])[0])
        offset = int(query.get("offset", [0])[0])

        if status and status.lower() != "all" and status not in VALID_STATUSES:
            json_response(self, 400, message=f"Invalid status: {status}")
            return

        if status and status.lower() == "all":
            status = None

        tasks = _global_task_manager.list_tasks(status=status, limit=limit, offset=offset)
        total = len(_global_task_manager._tasks)
        json_response(self, 200, data={
            "tasks": [t.to_dict() for t in tasks],
            "total": total,
            "limit": limit,
            "offset": offset
        })

    def _get_task(self, task_id: str):
        task = _global_task_manager.get_task(task_id)
        if task is None:
            json_response(self, 404, message=f"Task not found: {task_id}")
            return
        json_response(self, 200, data={"task": task.to_dict()})

    def _delete_task(self, task_id: str):
        task = _global_task_manager.get_task(task_id)
        if task is None:
            json_response(self, 404, message=f"Task not found: {task_id}")
            return
        _global_task_manager._tasks.pop(task_id, None)
        _global_task_manager._save_tasks()
        json_response(self, 200, data={"deleted": task_id}, message="Task deleted")

    def _clear_tasks(self, body: dict):
        status = body.get("status")
        if status and status not in VALID_STATUSES:
            json_response(self, 400, message=f"Invalid status: {status}")
            return
        _global_task_manager.clear_tasks(status=status)
        json_response(self, 200, message="Tasks cleared", data={"status": status or "all"})

    def _retry_task(self, task_id: str):
        task = _global_task_manager.retry_task(task_id)
        if task is None:
            json_response(self, 404, message=f"Task not found or cannot retry: {task_id}")
            return
        json_response(self, 200, data={"task": task.to_dict()}, message="Task retry scheduled")

    def _queue_retry_all(self):
        retried = _global_task_manager.retry_all_failed()
        json_response(self, 200, data={
            "retried_count": len(retried),
            "task_ids": [t.task_id for t in retried]
        }, message=f"Retried {len(retried)} failed tasks")

    def _queue_pause(self):
        if _global_pipeline:
            _global_pipeline.pause()
        if _global_metrics:
            _global_metrics.set_queue_paused(True)
        json_response(self, 200, message="Queue paused")

    def _queue_resume(self):
        if _global_pipeline:
            _global_pipeline.resume()
        if _global_metrics:
            _global_metrics.set_queue_paused(False)
        json_response(self, 200, message="Queue resumed")

    def _queue_status(self):
        paused = _global_pipeline.is_paused() if _global_pipeline else False
        counts = _global_task_manager.count_by_status() if _global_task_manager else {}
        json_response(self, 200, data={
            "paused": paused,
            "by_status": counts
        })

    def _config_reload(self):
        global _config
        try:
            config_path = _config.get("_config_path") if _config else None
            _config = load_config(config_path) if config_path else load_config()
            json_response(self, 200, message="Config reloaded")
        except Exception as e:
            json_response(self, 500, message=f"Config reload failed: {e}")

    def _run_batch(self):
        if _global_pipeline is None:
            json_response(self, 500, message="Pipeline not initialized")
            return

        def run_background():
            _global_pipeline.run_all()

        thread = threading.Thread(target=run_background, daemon=True)
        thread.start()
        json_response(self, 202, message="Batch processing started in background")

    def _run_file(self, body: dict):
        if _global_pipeline is None:
            json_response(self, 500, message="Pipeline not initialized")
            return
        file_path = body.get("path", "")
        if not file_path:
            json_response(self, 400, message="Missing 'path' field")
            return

        if not os.path.isfile(file_path):
            json_response(self, 404, message=f"File not found: {file_path}")
            return

        def run_one():
            from file_scanner import find_video_files
            video_file = os.path.basename(file_path)
            from task_manager import Task
            task = _global_task_manager.create_task(
                video_path=file_path,
                video_file=video_file,
                subtitle_files=[],
                file_size_mb=os.path.getsize(file_path) / (1024 * 1024)
            )
            _global_pipeline.process_one(task)

        thread = threading.Thread(target=run_one, daemon=True)
        thread.start()
        json_response(self, 202, message=f"Processing started: {file_path}")

    def _logs(self, query: dict):
        log_dir = _config.get("log_dir", "logs") if _config else "logs"
        log_file = os.path.join(log_dir, "media_importer.log")

        if not os.path.exists(log_file):
            json_response(self, 200, data={"logs": []})
            return

        limit = int(query.get("limit", [100])[0])
        task_id = query.get("task_id", [None])[0]

        try:
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            json_response(self, 200, data={"logs": []})
            return

        result_lines = []
        for line in lines[-limit:]:
            try:
                entry = json.loads(line)
                if task_id is None or entry.get("task_id") == task_id:
                    result_lines.append(entry)
            except json.JSONDecodeError:
                result_lines.append({"raw": line.strip()})

        json_response(self, 200, data={"logs": result_lines[-limit:]})

    def log_message(self, protocol, fmt, *args):
        pass


def start_server(host: str, port: int, config: dict):
    global _global_pipeline, _global_task_manager, _global_metrics, _global_logger, _global_notifier, _config

    _config = config
    persistence_path = config.get("task_queue", {}).get("persistence_path",
        os.path.join(os.path.dirname(__file__), "..", "data", "tasks.json"))

    persistence_dir = os.path.dirname(persistence_path)
    if persistence_dir:
        os.makedirs(persistence_dir, exist_ok=True)
    _global_task_manager = TaskManager(persistence_path, config)
    _global_metrics = get_metrics()
    _global_logger = get_logger(config)

    hermes_cfg = config.get("hermes", {})
    if hermes_cfg.get("enabled", False):
        _global_notifier = HermesNotifier(hermes_cfg, _global_logger)

    _global_pipeline = PipelineRunner(
        config=config,
        task_manager=_global_task_manager,
        metrics=_global_metrics,
        logger=_global_logger,
        notifier=_global_notifier
    )

    def on_new_files(new_files):
        if _global_pipeline and not _global_pipeline.is_paused():
            _global_pipeline.run_all()

    watcher = FileWatcher(config, on_new_files=on_new_files, logger=_global_logger)
    watcher.start()

    server_address = (host, port)
    httpd = HTTPServer(server_address, APIHandler)
    print(f"HTTP API 服务启动: http://{host}:{port}")
    print("端点列表:")
    print("  GET  /api/health           - 健康检查")
    print("  GET  /api/metrics          - 指标统计")
    print("  GET  /api/config           - 当前配置")
    print("  POST /api/config/reload    - 重载配置")
    print("  GET  /api/tasks            - 任务列表")
    print("  GET  /api/tasks/{id}       - 任务详情")
    print("  DELETE /api/tasks/{id}      - 删除任务")
    print("  POST /api/tasks/{id}/retry - 重试任务")
    print("  POST /api/tasks/clear      - 清空任务")
    print("  POST /api/queue/pause      - 暂停队列")
    print("  POST /api/queue/resume     - 恢复队列")
    print("  POST /api/queue/retry-all  - 重试所有失败")
    print("  GET  /api/queue/status     - 队列状态")
    print("  GET  /api/logs             - 查询日志")
    print("  POST /api/run              - 触发批量处理")
    print("  POST /api/run/file         - 处理指定文件")
    if watcher.enabled:
        print(f"  文件监控: 已启用 (轮询间隔 {watcher.poll_interval}s)")
    print("")
    print("按 Ctrl+C 停止服务")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        watcher.stop()
        print("\n服务已停止")
        httpd.shutdown()
