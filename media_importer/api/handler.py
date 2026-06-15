import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from media_importer.features.configuration import load_config, mask_sensitive
from media_importer.features.tasks import TaskManager
from media_importer.features.import_flow import PipelineRunner
from media_importer.core.metrics import Metrics, get_metrics
from media_importer.core.logger import get_logger
from media_importer.notify.hermes_hook import HermesNotifier
from media_importer.monitor.file_watcher import FileWatcher
from media_importer.core.db import (
    update_task as db_update_task,
)
from media_importer.core.task_lifecycle import FILE_LOCATION_SOURCE, mark_failed

from .utils import json_response, read_json_body, ThreadingHTTPServer, format_tasks_to_text
from .static_server import StaticServerMixin
from .task_handlers import TaskHandlersMixin
from .config_handlers import ConfigHandlersMixin
from .connectivity_handlers import ConnectivityHandlersMixin
from .tmdb_handlers import TMDbHandlersMixin
from .dimension_handlers import DimensionHandlersMixin
from .prompt_handlers import PromptHandlersMixin
from .provider_handlers import ProviderHandlersMixin
from .source_cleaner_handlers import SourceCleanerHandlers
from .recycle_handlers import RecycleHandlers
from .thumbnail_handlers import ThumbnailHandlersMixin
from .routes import match_route
from . import globals


class APIHandler(
    StaticServerMixin,
    TaskHandlersMixin,
    ConfigHandlersMixin,
    ConnectivityHandlersMixin,
    TMDbHandlersMixin,
    DimensionHandlersMixin,
    PromptHandlersMixin,
    ProviderHandlersMixin,
    SourceCleanerHandlers,
    RecycleHandlers,
    ThumbnailHandlersMixin,
    BaseHTTPRequestHandler
):
    protocol_version = "HTTP/1.1"

    def _check_auth(self) -> bool:
        api_key = globals._config.get("server", {}).get("api_key", "") if globals._config else ""
        if not api_key:
            return True
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if token == api_key:
                return True
        return False

    def _auth_required(self):
        json_response(self, 401, code_str="unauthorized", message="认证失败：请提供有效的 API Key")

    def _dispatch_api_route(self, method: str, path: str, query=None, body=None) -> bool:
        match = match_route(method, path)
        if not match:
            return False
        if match.route.auth_required and not self._check_auth():
            self._auth_required()
            return True

        handler = getattr(self, match.route.handler_name)
        handler(
            body=body or {},
            params=match.params,
            query=query or {},
        )
        return True

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/":
            self._serve_static_file("index.html")
        elif path.startswith("/css/") or path.startswith("/js/"):
            self._serve_static_file(path.lstrip("/"))
        elif path.startswith("/api/"):
            if not self._dispatch_api_route("GET", path, query=query):
                json_response(self, 404, message=f"Endpoint not found: {path}")
        else:
            self._serve_static_file(path.lstrip("/"))

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        body = read_json_body(self)

        if path.startswith("/api/"):
            if not self._dispatch_api_route("POST", path, query=query, body=body):
                json_response(self, 404, message=f"Endpoint not found: {path}")
        else:
            json_response(self, 404, message=f"Endpoint not found: {path}")

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = read_json_body(self)

        if path.startswith("/api/"):
            if not self._dispatch_api_route("PUT", path, body=body):
                json_response(self, 404, message=f"Endpoint not found: {path}")
        else:
            json_response(self, 404, message=f"Endpoint not found: {path}")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/"):
            if not self._dispatch_api_route("DELETE", path):
                json_response(self, 404, message=f"Endpoint not found: {path}")
        else:
            json_response(self, 404, message=f"Endpoint not found: {path}")


def _cleanup_orphaned_state(config: dict, task_manager: TaskManager, logger):
    temp_dir = config.get('temp_dir', '')
    failed_count = 0
    cleaned_temp_count = 0

    all_tasks = task_manager.list_tasks(limit=10000)
    active_temp_files = set()

    for task in all_tasks:
        status = task.get("status", "")
        stage = task.get("stage", "")
        tid = task.get("task_id", "")

        # PENDING/RUNNING 任务 → 标记为 FAILED
        if status == "PENDING" and stage == "RUNNING":
            temp_video = task.get("video_path", "")
            if temp_video and os.path.exists(temp_video):
                try:
                    os.remove(temp_video)
                    cleaned_temp_count += 1
                except OSError:
                    pass
            for sub in (task.get("subtitle_files") or []):
                sub_str = str(sub) if sub else ""
                if sub_str and os.path.exists(sub_str):
                    try:
                        os.remove(sub_str)
                    except OSError:
                        pass
            fields = mark_failed(
                task,
                "服务中断或重启导致任务未完成，请重试",
                file_location=FILE_LOCATION_SOURCE,
                video_path="",
            )
            fields.update({
                "current_step": 0,
                "percentage": 0,
            })
            db_update_task(task_manager.conn, tid, **fields)
            failed_count += 1

        # PENDING/AWAIT_REVIEW 任务 → 保护 temp 文件不被清理
        elif status == "PENDING" and stage == "AWAIT_REVIEW":
            temp_video = task.get("video_path", "")
            if temp_video:
                active_temp_files.add(os.path.abspath(temp_video))
            for sub in (task.get("subtitle_files") or []):
                sub_str = str(sub) if sub else ""
                if sub_str:
                    active_temp_files.add(os.path.abspath(sub_str))

    if temp_dir and os.path.isdir(temp_dir):
        for f in os.listdir(temp_dir):
            fpath = os.path.abspath(os.path.join(temp_dir, f))
            if os.path.isfile(fpath) and fpath not in active_temp_files:
                try:
                    os.remove(fpath)
                    cleaned_temp_count += 1
                except OSError:
                    pass

    if failed_count > 0 or cleaned_temp_count > 0:
        msg_parts = []
        if failed_count > 0:
            msg_parts.append(f"将 {failed_count} 个中断的运行中任务标记为 FAILED")
        if cleaned_temp_count > 0:
            msg_parts.append(f"清理 {cleaned_temp_count} 个孤立临时文件")
        logger.info("启动清理: " + ", ".join(msg_parts))


def start_server(host: str, port: int, config: dict):
    globals._config = config
    data_dir = config.get("_data_dir",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "data"))

    try:
        os.makedirs(data_dir, exist_ok=True)
    except (OSError, PermissionError) as e:
        print(f"WARNING: 无法创建数据目录 {data_dir}: {e}", file=sys.stderr)
    globals._global_task_manager = TaskManager(data_dir, config)
    globals._global_metrics = get_metrics()
    globals._global_logger = get_logger(config)

    hermes_cfg = config.get("hermes", {})
    if hermes_cfg.get("enabled", False):
        globals._global_notifier = HermesNotifier(config)

    globals._global_pipeline = PipelineRunner(
        config=config,
        task_manager=globals._global_task_manager,
        metrics=globals._global_metrics,
        logger=globals._global_logger,
        notifier=globals._global_notifier
    )

    globals._global_logger.info("API 服务初始化完成")

    _cleanup_orphaned_state(config, globals._global_task_manager, globals._global_logger)

    def notify_error(error_type: str, error_message: str, extra_data: dict = None):
        if globals._global_notifier:
            globals._global_notifier.notify_program_error(error_type, error_message, extra_data)

    def on_new_files(new_files):
        if globals._global_pipeline and not globals._global_pipeline.is_paused():
            try:
                globals._global_pipeline.run_all()
            except Exception as e:
                globals._global_logger.error(f"批量处理异常: {e}")
                notify_error("batch_error", str(e), {"new_files": list(new_files)})

        if globals._config_dirty and not globals._global_task_manager.has_running_tasks():
            globals._config_dirty = False
            try:
                config_path = globals._config.get("_config_path") if globals._config else None
                if config_path:
                    new_config = load_config(config_path)
                    globals._config.clear()
                    globals._config.update(new_config)
                    if globals._global_pipeline:
                        globals._global_pipeline.config = globals._config
                    globals._global_logger.info("任务完成后自动重载配置")
            except Exception as e:
                globals._global_logger.error(f"自动重载配置失败: {e}")

    watcher_cfg = config.get("file_watcher", {})
    if watcher_cfg.get("enabled", False):
        globals._global_watcher = FileWatcher(config, on_new_files=on_new_files, logger=globals._global_logger)
        globals._global_watcher.start()
        globals._global_logger.info(f"文件监控已启用 (轮询间隔 {watcher_cfg.get('poll_interval', 60)}s)")

        source_dir = config.get("source_dir", "")
        if source_dir and os.path.isdir(source_dir):
            from media_importer.features.import_flow import scan_source_dir
            try:
                groups = scan_source_dir(source_dir, config)
                if groups:
                    globals._global_logger.info(f"启动时发现 {len(groups)} 个待处理文件")
                    def run_initial_batch():
                        globals._global_pipeline.run_all()
                        if globals._config_dirty and not globals._global_task_manager.has_running_tasks():
                            globals._config_dirty = False
                            try:
                                config_path = globals._config.get("_config_path") if globals._config else None
                                if config_path:
                                    new_config = load_config(config_path)
                                    globals._config.clear()
                                    globals._config.update(new_config)
                                    if globals._global_pipeline:
                                        globals._global_pipeline.config = globals._config
                                    globals._global_logger.info("任务完成后自动重载配置")
                            except Exception as e:
                                globals._global_logger.error(f"自动重载配置失败: {e}")
                    threading.Thread(target=run_initial_batch, daemon=True).start()
            except Exception as e:
                globals._global_logger.error(f"启动扫描失败: {e}")
    else:
        globals._global_watcher = None
        globals._global_logger.info("文件监控未启用，跳过启动扫描")

    server_address = (host, port)
    server_cls = HTTPServer if os.environ.get("NAS_E2E_SINGLE_THREAD") == "1" else ThreadingHTTPServer
    httpd = server_cls(server_address, APIHandler)
    print(f"HTTP API 服务启动: http://{host}:{port}")
    print("端点列表:")
    print("  GET  /                      - Web UI 首页")
    print("  GET  /css/*                 - 样式文件")
    print("  GET  /js/*                  - JavaScript 文件")
    print("  GET  /api/health           - 健康检查")
    print("  GET  /api/metrics          - 指标统计")
    print("  GET  /api/config           - 当前配置")
    print("  POST /api/config           - 保存配置")
    print("  POST /api/config/reload    - 重载配置")
    print("  GET  /api/config/validate  - 配置检测（路径、API连通性等）")
    print("  GET  /api/tasks            - 任务列表 (支持 ?page=&page_size=&status=)")
    print("  GET  /api/tasks/{id}       - 任务详情")
    print("  GET  /api/tasks/{id}/subtitles - 字幕列表")
    print("  GET  /api/tasks/stats      - 任务统计")
    print("  DELETE /api/tasks/{id}      - 删除任务(仅DB记录)")
    print("  POST /api/tasks/{id}/delete - 删除任务(可选删除文件, body: {delete_files: bool})")
    print("  POST /api/tasks/{id}/retry - 重试任务")
    print("  POST /api/tasks/{id}/confirm - 确认入库 (AWAIT_REVIEW → SUCCESS)")
    print("  POST /api/tasks/{id}/reclassify - 重新分类 (带 dimensions 参数)")
    print("  POST /api/tasks/{id}/ignore - 忽略任务")
    print("  POST /api/tasks/clear      - 清空任务")
    print("  POST /api/tasks/confirm-all - 批量确认所有待确认任务")
    print("  POST /api/queue/pause      - 暂停队列")
    print("  POST /api/queue/resume     - 恢复队列")
    print("  POST /api/queue/retry-all  - 重试所有失败")
    print("  GET  /api/queue/status     - 队列状态")
    print("  GET  /api/logs             - 查询日志")
    print("  POST /api/run              - 触发批量处理")
    print("  POST /api/run/file         - 处理指定文件")
    print("  GET  /api/skill            - 获取Hermes SKILL.md")
    print("  GET  /api/skills           - 获取所有可用Skills列表")
    if globals._global_watcher and globals._global_watcher.enabled:
        print(f"  文件监控: 已启用 (轮询间隔 {globals._global_watcher.poll_interval}s)")
    print("")
    print("按 Ctrl+C 停止服务")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        if globals._global_watcher:
            globals._global_watcher.stop()
        print("\n服务已停止")
        httpd.shutdown()
