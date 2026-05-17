#!/usr/bin/env python3
import json
import os
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


from config_loader import load_config, mask_sensitive
from task_manager import TaskManager, VALID_STATUSES
from pipeline import PipelineRunner
from metrics import Metrics, get_metrics
from logger import get_logger
from hermes_hook import HermesNotifier
from file_watcher import FileWatcher


_global_pipeline = None
_global_task_manager = None
_global_metrics = None
_global_logger = None
_global_notifier = None
_global_watcher = None
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

    def _watcher_status(self):
        """获取轮询状态"""
        if not _global_watcher:
            json_response(self, 200, data={"enabled": False, "status": "not_started"})
            return
        json_response(self, 200, data={
            "enabled": _global_watcher.is_running(),
            "poll_interval": _global_watcher.poll_interval,
            "status": "running" if _global_watcher.is_running() else "stopped"
        })

    def _watcher_control(self, query):
        """控制轮询开关"""
        action = query.get("action", [None])[0]
        if not _global_watcher:
            json_response(self, 400, message="Watcher not initialized")
            return

        if action == "pause":
            _global_watcher.stop()
            json_response(self, 200, message="轮询已暂停")
        elif action == "resume":
            _global_watcher.start()
            json_response(self, 200, message="轮询已恢复")
        elif action == "status":
            self._watcher_status()
        else:
            json_response(self, 400, message="Invalid action: use pause/resume/status")

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
        elif path == "/api/watcher/status":
            self._watcher_status()
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
        elif path == "/api/skill":
            self._skill()
        elif path == "/api/skills":
            self._skills_list()
        else:
            json_response(self, 404, message=f"Endpoint not found: {path}")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        body = read_json_body(self)

        if path == "/api/run":
            self._run_batch()
        elif path == "/api/watcher/control":
            self._watcher_control(query)
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

    def _skill(self):
        skill_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "hermes", "skills", "nas-ops", "nas-media-importer", "SKILL.md"
        )
        skill_path = os.path.normpath(skill_path)
        if not os.path.isfile(skill_path):
            json_response(self, 404, message="SKILL.md not found")
            return
        try:
            with open(skill_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            json_response(self, 500, message=f"Failed to read SKILL.md: {e}")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        body_bytes = content.encode("utf-8")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body_bytes)
        self.wfile.flush()

    def _skills_list(self):
        skills_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "hermes", "skills"
        )
        skills_dir = os.path.normpath(skills_dir)
        skills = []
        if os.path.isdir(skills_dir):
            for root, dirs, files in os.walk(skills_dir):
                for f in files:
                    if f == "SKILL.md":
                        rel = os.path.relpath(root, skills_dir)
                        skill_file = os.path.join(root, f)
                        try:
                            with open(skill_file, "r", encoding="utf-8") as fh:
                                header = fh.read(512)
                            name = ""
                            for line in header.split("\n"):
                                if line.startswith("name:"):
                                    name = line.split(":", 1)[1].strip()
                                    break
                            skills.append({"path": rel, "name": name or rel})
                        except Exception:
                            skills.append({"path": rel, "name": rel})
        json_response(self, 200, data={"skills": skills, "total": len(skills)})

    def _health(self):
        from safety import check_write_permission
        checks = {}
        overall = "ok"

        try:
            source_dir = _config.get("source_dir", "")
            if os.path.isdir(source_dir):
                if os.access(source_dir, os.R_OK):
                    checks["source_dir"] = "ok"
                else:
                    checks["source_dir"] = "no_read_permission"
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
        show_all = query.get("all", ["false"])[0].lower() == "true"
        format_mode = query.get("format", ["json"])[0].lower()  # json | text

        if status and status.lower() != "all" and status not in VALID_STATUSES:
            json_response(self, 400, message=f"Invalid status: {status}")
            return

        if status and status.lower() == "all":
            status = None
        elif not status and show_all:
            status = None

        exclude_completed = not show_all
        tasks = _global_task_manager.list_tasks(
            status=status, limit=limit, offset=offset,
            exclude_completed=exclude_completed if not status else None
        )
        total = len(_global_task_manager._tasks)
        active_count = sum(1 for t in _global_task_manager._tasks.values()
                          if t.status in ["PENDING", "PROCESSING", "FAILED"])

        # 1. 构建标准JSON数据（基础）
        json_data = {
            "tasks": [t.to_dict() for t in tasks],
            "total": total,
            "active_count": active_count,
            "limit": limit,
            "offset": offset
        }

        # 2. 根据format_mode决定返回方式
        if format_mode == "text":
            text_output = format_tasks_to_text(json_data)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(text_output.encode("utf-8"))))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(text_output.encode("utf-8"))
            self.wfile.flush()
        else:
            json_response(self, 200, data=json_data)


def format_tasks_to_text(json_data: dict) -> str:
    """
    将任务JSON数据格式化为可读文本
    完全基于JSON数据，与内部实现解耦
    """
    lines = []
    active_count = json_data.get("active_count", 0)
    total = json_data.get("total", 0)
    tasks = json_data.get("tasks", [])

    lines.append("+--------------------------------------------------------------------------------------------+")
    lines.append(f"|  NAS影视入库系统 - 活跃任务                                                                   |")
    lines.append(f"|  活跃任务: {active_count}{' ' * 6}总记录: {total}{' ' * 54} |")
    lines.append("+--------------------------------------------------------------------------------------------+")
    lines.append("")

    if not tasks:
        lines.append("  没有活跃任务，所有任务已处理完毕")
    else:
        def status_label(s):
            if s == "SUCCESS":
                return "成功"
            if s == "FAILED":
                return "失败"
            if s == "PROCESSING":
                return "处理中"
            if s == "PENDING":
                return "待处理"
            if s == "SKIPPED":
                return "跳过"
            return s

        def format_error(msg, max_len=20):
            if not msg:
                return ""
            if len(msg) > max_len:
                return msg[:max_len-2] + ".."
            return msg

        lines.append(f'{"文件名":.<28} {"状态":^8} {"进度":^6} {"刮削结果":.<18} {"错误原因":.<20}')
        lines.append(f'{"-" * 28} {"-" * 8} {"-" * 6} {"-" * 18} {"-" * 20}')

        for t in tasks:
            name = t.get("video_file", "")
            name_short = (name[:25] + "...") if len(name) > 28 else name
            status = t.get("status", "")
            pct = t.get("percentage", 0)
            scraped = t.get("scraped_info", {})
            error_msg = format_error(t.get("error_message", ""), 20)
            
            title_cn = scraped.get("title_cn", "") or scraped.get("title_en", "") or "?"
            year = scraped.get("year", "")
            result = f"{title_cn}({year})" if year else title_cn
            result_short = (result[:16] + "..") if len(result) > 18 else result
            
            lines.append(f"{name_short:<28} {status_label(status):^8} {pct:>3}%   {result_short:<18} {error_msg:<20}")
    
    return "\n".join(lines)



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
        _global_notifier = HermesNotifier(config)

    _global_pipeline = PipelineRunner(
        config=config,
        task_manager=_global_task_manager,
        metrics=_global_metrics,
        logger=_global_logger,
        notifier=_global_notifier
    )

    def notify_error(error_type: str, error_message: str, extra_data: dict = None):
        """通知程序错误到Hermes"""
        if _global_notifier:
            _global_notifier.notify_program_error(error_type, error_message, extra_data)

    def on_new_files(new_files):
        if _global_pipeline and not _global_pipeline.is_paused():
            try:
                _global_pipeline.run_all()
            except Exception as e:
                _global_logger.error(f"批量处理异常: {e}")
                notify_error("batch_error", str(e), {"new_files": list(new_files)})

    watcher = FileWatcher(config, on_new_files=on_new_files, logger=_global_logger)
    watcher.start()
    global _global_watcher
    _global_watcher = watcher

    source_dir = config.get("source_dir", "")
    if source_dir and os.path.isdir(source_dir):
        from file_scanner import scan_source_dir
        try:
            groups = scan_source_dir(source_dir, config)
            if groups:
                _global_logger.info(f"启动时发现 {len(groups)} 个待处理文件")
                def run_initial_batch():
                    _global_pipeline.run_all()
                threading.Thread(target=run_initial_batch, daemon=True).start()
        except Exception as e:
            _global_logger.error(f"启动扫描失败: {e}")

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
    print("  GET  /api/skill            - 获取Hermes SKILL.md")
    print("  GET  /api/skills           - 获取所有可用Skills列表")
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
