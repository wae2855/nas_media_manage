import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from media_importer.core.config_loader import load_config, mask_sensitive
from media_importer.core.task_manager import TaskManager
from media_importer.pipeline import PipelineRunner
from media_importer.core.metrics import Metrics, get_metrics
from media_importer.core.logger import get_logger
from media_importer.notify.hermes_hook import HermesNotifier
from media_importer.monitor.file_watcher import FileWatcher
from media_importer.core.db import (
    update_task as db_update_task,
    delete_task as db_delete_task,
    VALID_STATUSES,
)

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

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path.startswith("/api/") and path != "/api/health":
            if not self._check_auth():
                self._auth_required()
                return

        if path == "/":
            self._serve_static_file("index.html")
        elif path.startswith("/css/") or path.startswith("/js/"):
            self._serve_static_file(path.lstrip("/"))
        elif path == "/api/health":
            self._health()
        elif path == "/api/metrics":
            self._metrics()
        elif path == "/api/config":
            self._config()
        elif path == "/api/config/validate":
            self._config_validate()
        elif path == "/api/config/prompts":
            prompts_data = self._load_prompts_for_ui()
            json_response(self, 200, data=prompts_data)
        elif path == "/api/config/prompts/reset":
            self._config_reset_prompts()
        elif path == "/api/watcher/status":
            self._watcher_status()
        elif path == "/api/tasks":
            self._list_tasks(query)
        elif path == "/api/tasks/stats":
            self._task_stats()
        elif path.startswith("/api/tasks/"):
            parts = path.split("/")
            if len(parts) >= 5 and parts[4] == "subtitles":
                task_id = parts[3]
                self._task_subtitles(task_id)
            elif len(parts) >= 4:
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
        elif path == "/api/dimensions":
            self._dimensions_list()
        elif path == "/api/dimensions/enabled":
            self._dimensions_enabled()
        elif path == "/api/providers":
            self._providers_list()
        elif path.startswith("/api/providers/"):
            parts = path.split("/")
            if len(parts) >= 5:
                provider_type = parts[3]
                action = parts[4]
                if action == "genres":
                    self._provider_genres_list(provider_type)
                elif action == "prompts":
                    self._provider_prompts_get(provider_type)
                else:
                    json_response(self, 404, message=f"Not found: {path}")
            else:
                json_response(self, 404, message=f"Not found: {path}")
        elif path.startswith("/api/dimensions/"):
            dim_name = path.split("/api/dimensions/")[1].rstrip("/")
            self._dimension_get(dim_name)
        elif path == "/api/source-cleaner/preview":
            self.source_cleaner_preview(self)
        elif path == "/api/source-cleaner/records":
            self.source_cleaner_records(self)
        elif path == "/api/source-cleaner/status":
            self.source_cleaner_status(self)
        elif path == "/api/source-cleaner/ai-preview":
            self.source_cleaner_ai_preview(self)
        elif path == "/api/recycle/list":
            self.recycle_list(self)
        else:
            self._serve_static_file(path.lstrip("/"))

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        body = read_json_body(self)

        if path.startswith("/api/"):
            if not self._check_auth():
                self._auth_required()
                return

        if path == "/api/run":
            self._run_batch()
        elif path == "/api/restart":
            self._restart_service()
        elif path == "/api/watcher/control":
            self._watcher_control(query)
        elif path == "/api/run/file":
            self._run_file(body)
        elif path == "/api/tasks/clear":
            self._clear_tasks(body)
        elif path == "/api/tasks/confirm-all":
            self._task_confirm_all()
        elif path.startswith("/api/tasks/") and path.endswith("/retry"):
            parts = path.split("/")
            if len(parts) >= 5:
                task_id = parts[3]
                self._retry_task(task_id)
            else:
                json_response(self, 400, message="Invalid retry path")
        elif path.startswith("/api/tasks/") and path.endswith("/confirm"):
            parts = path.split("/")
            if len(parts) >= 5:
                task_id = parts[3]
                self._task_confirm(task_id)
            else:
                json_response(self, 400, message="Invalid confirm path")
        elif path.startswith("/api/tasks/") and path.endswith("/reclassify"):
            parts = path.split("/")
            if len(parts) >= 5:
                task_id = parts[3]
                self._task_reclassify(task_id, body)
            else:
                json_response(self, 400, message="Invalid reclassify path")
        elif path.startswith("/api/tasks/") and path.endswith("/ignore"):
            parts = path.split("/")
            if len(parts) >= 5:
                task_id = parts[3]
                self._task_ignore(task_id)
            else:
                json_response(self, 400, message="Invalid ignore path")
        elif path.startswith("/api/tasks/") and path.endswith("/rename"):
            parts = path.split("/")
            if len(parts) >= 5:
                task_id = parts[3]
                self._task_rename(task_id, body)
            else:
                json_response(self, 400, message="Invalid rename path")
        elif path.startswith("/api/tasks/") and path.endswith("/delete"):
            parts = path.split("/")
            if len(parts) >= 5:
                task_id = parts[3]
                delete_files = bool(body.get("delete_files", False)) if body else False
                self._delete_task(task_id, delete_files=delete_files)
            else:
                json_response(self, 400, message="Invalid delete path")
        elif path == "/api/queue/pause":
            self._queue_pause()
        elif path == "/api/queue/resume":
            self._queue_resume()
        elif path == "/api/queue/retry-all":
            self._queue_retry_all()
        elif path == "/api/config/reload":
            self._config_reload()
        elif path == "/api/config/test-llm":
            self._config_test_llm(body)
        elif path == "/api/config/test-hermes":
            self._config_test_hermes(body)
        elif path == "/api/scrape/preview":
            self._scrape_preview(body)
        elif path.startswith("/api/providers/"):
            parts = path.split("/")
            if len(parts) >= 5:
                provider_type = parts[3]
                action = parts[4]
                if action == "test":
                    self._provider_test(body, provider_type)
                elif action == "preview":
                    self._provider_preview(body, provider_type)
                elif action == "search":
                    self._provider_search(body, provider_type)
                elif action == "details":
                    self._provider_details(body, provider_type)
                elif action == "prompts":
                    if len(parts) >= 6 and parts[5] == "reset":
                        self._provider_prompts_reset(body, provider_type)
                    else:
                        self._provider_prompts_save(body, provider_type)
                else:
                    json_response(self, 404, message=f"Not found: {path}")
            else:
                json_response(self, 404, message=f"Not found: {path}")
        elif path == "/api/config/check-permission":
            self._config_check_permission(body)
        elif path == "/api/path/test":
            self._path_test(body)
        elif path == "/api/config/section":
            self._config_save_section(body)
        elif path == "/api/config":
            self._config_save(body)
        elif path == "/api/config/prompts":
            self._config_save_prompts(body)
        elif path == "/api/config/prompts/reset":
            self._config_reset_prompts()
        elif path.startswith("/api/dimensions/") and path.endswith("/enable"):
            dim_name = path.split("/api/dimensions/")[1].replace("/enable", "")
            self._dimension_enable(dim_name)
        elif path.startswith("/api/dimensions/") and path.endswith("/disable"):
            dim_name = path.split("/api/dimensions/")[1].replace("/disable", "")
            self._dimension_disable(dim_name)
        elif path.startswith("/api/dimensions/") and path.endswith("/reset"):
            dim_name = path.split("/api/dimensions/")[1].replace("/reset", "")
            self._dimension_reset(dim_name)
        elif path == "/api/source-cleaner/execute":
            self.source_cleaner_execute(self)
        elif path == "/api/recycle/restore":
            self.recycle_restore(self)
        elif path == "/api/recycle/delete":
            self.recycle_delete(self)
        else:
            json_response(self, 404, message=f"Endpoint not found: {path}")

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = read_json_body(self)

        if path.startswith("/api/"):
            if not self._check_auth():
                self._auth_required()
                return

        if path.startswith("/api/dimensions/"):
            dim_name = path.split("/api/dimensions/")[1].rstrip("/")
            self._dimension_update(dim_name, body)
        else:
            json_response(self, 404, message=f"Endpoint not found: {path}")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/"):
            if not self._check_auth():
                self._auth_required()
                return

        if path.startswith("/api/tasks/"):
            suffix = path[len("/api/tasks/"):]
            if "/" in suffix:
                json_response(self, 404, message=f"Endpoint not found: {path}")
                return
            task_id = suffix
            if not task_id:
                json_response(self, 400, message="Missing task_id")
                return
            self._delete_task(task_id, delete_files=False)
        else:
            json_response(self, 404, message=f"Endpoint not found: {path}")


def _cleanup_orphaned_state(config: dict, task_manager: TaskManager, logger):
    temp_dir = config.get('temp_dir', '')
    reset_count = 0
    cleaned_temp_count = 0

    all_tasks = task_manager.list_tasks(limit=10000)
    active_temp_files = set()

    for task in all_tasks:
        status = task.get("status", "")
        tid = task.get("task_id", "")

        if status == "PROCESSING":
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
            db_update_task(task_manager.conn, tid,
                           status="PENDING", file_location="source",
                           video_path="", current_step=0, percentage=0)
            reset_count += 1

        elif status == "CONFIRMING":
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

    if reset_count > 0 or cleaned_temp_count > 0:
        msg_parts = []
        if reset_count > 0:
            msg_parts.append(f"重置 {reset_count} 个崩溃任务为 PENDING")
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
    else:
        globals._global_watcher = None
        globals._global_logger.info("文件监控未启用")

    source_dir = config.get("source_dir", "")
    if source_dir and os.path.isdir(source_dir):
        from media_importer.storage.file_scanner import scan_source_dir
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

    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, APIHandler)
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
    print("  POST /api/tasks/{id}/confirm - 确认入库 (CONFIRMING → SUCCESS)")
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
