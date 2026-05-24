#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

WEBUI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webui")


from config_loader import load_config, mask_sensitive
from config_validator import validate_config
from task_manager import TaskManager
from db import VALID_STATUSES
from pipeline import PipelineRunner
from metrics import Metrics, get_metrics
from logger import get_logger
from hermes_hook import HermesNotifier
from file_watcher import FileWatcher
from db import (
    update_task as db_update_task,
    delete_task as db_delete_task,
    get_subtitles_by_task as db_get_subtitles,
    update_subtitles_by_task as db_update_subtitles_by_task,
    update_subtitle as db_update_subtitle,
    count_by_status as db_count_by_status,
    count_by_specific_status as db_count_specific,
    get_all_dimensions as db_get_all_dimensions,
    get_enabled_dimensions as db_get_enabled_dimensions,
    get_dimension as db_get_dimension,
    update_dimension as db_update_dimension,
    enable_dimension as db_enable_dimension,
    disable_dimension as db_disable_dimension,
    reset_dimension as db_reset_dimension,
)
from dimension_manager import check_tier_access


_global_pipeline = None
_global_task_manager = None
_global_metrics = None
_global_logger = None
_global_notifier = None
_global_watcher = None
_config = None
_config_dirty = False


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


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class APIHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _check_auth(self) -> bool:
        api_key = _config.get("server", {}).get("api_key", "") if _config else ""
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
        json_response(self, 200, data={"task": task})

    def _delete_task(self, task_id: str, delete_files: bool = False):
        task = _global_task_manager.get_task(task_id)
        if task is None:
            json_response(self, 404, message=f"Task not found: {task_id}")
            return

        current_status = task.get("status", "")
        if current_status == "PROCESSING":
            json_response(self, 400, message="任务正在处理中，无法删除，请等待处理完成")
            return

        deleted_files = []
        missing_files = []
        file_location = task.get("file_location", "source")

        temp_files_to_cleanup = []
        if file_location == "temp":
            vp = task.get("video_path", "")
            if vp:
                if os.path.exists(vp):
                    temp_files_to_cleanup.append(vp)
                else:
                    missing_files.append(os.path.basename(vp))
            for sub in (task.get("subtitle_files") or []):
                sub_str = str(sub) if sub else ""
                if sub_str:
                    if os.path.exists(sub_str):
                        temp_files_to_cleanup.append(sub_str)
                    else:
                        missing_files.append(os.path.basename(sub_str))

        temp_dir = _config.get('temp_dir', '') if _config else ''
        for f in temp_files_to_cleanup:
            try:
                f_abs = os.path.abspath(f)
                if temp_dir and f_abs.startswith(os.path.abspath(temp_dir) + os.sep):
                    if os.path.exists(f):
                        os.remove(f)
                        deleted_files.append(os.path.basename(f))
                    else:
                        missing_files.append(os.path.basename(f))
            except OSError:
                pass

        if delete_files:
            files_to_delete = []
            files_to_check = []

            if file_location == "import":
                ivp = task.get("import_video_path", "")
                if ivp:
                    files_to_check.append(ivp)
                for sub in (task.get("subtitle_files") or []):
                    sub_str = str(sub) if sub else ""
                    if sub_str:
                        files_to_check.append(sub_str)
            elif file_location == "quarantine":
                sp = task.get("source_path", "")
                if sp:
                    files_to_check.append(sp)
                for sub in (task.get("subtitle_files") or []):
                    sub_str = str(sub) if sub else ""
                    if sub_str:
                        files_to_check.append(sub_str)
            elif file_location == "source":
                sp = task.get("source_path", "")
                if sp:
                    files_to_check.append(sp)
                for sub in (task.get("subtitle_files") or []):
                    sub_str = str(sub) if sub else ""
                    if sub_str:
                        files_to_check.append(sub_str)

            # 先记录哪些文件存在/不存在
            for f in files_to_check:
                if os.path.exists(f):
                    files_to_delete.append(f)
                else:
                    missing_files.append(os.path.basename(f))

            source_policy = _config.get("source_policy", {}) if _config else {}
            import_dirs = []
            for rule in (_config.get("path_rules", []) if _config else []):
                tpl = rule.get("template", "")
                if tpl:
                    import_dirs.append(tpl)

            allowed_dirs = [
                _config.get("source_dir", "") if _config else "",
                _config.get("temp_dir", "") if _config else "",
                source_policy.get("quarantine_dir", ""),
            ] + import_dirs

            for f in files_to_delete:
                try:
                    f_abs = os.path.abspath(f)
                    allowed = any(
                        d and f_abs.startswith(os.path.abspath(d) + os.sep)
                        for d in allowed_dirs
                    )
                    if allowed and os.path.exists(f):
                        os.remove(f)
                        deleted_files.append(os.path.basename(f))
                except OSError:
                    pass

        db_delete_task(_global_task_manager.conn, task_id)

        location_labels = {
            "source": "源文件", "quarantine": "隔离区文件",
            "import": "入库文件", "temp": "中转文件",
        }
        loc_label = location_labels.get(file_location, "文件")
        result = {"deleted": task_id, "file_location": file_location}
        
        msg_parts = ["任务已删除"]
        
        if deleted_files:
            result["deleted_files"] = deleted_files
            msg_parts.append(f"已删除 {len(deleted_files)} 个{loc_label}")
        
        if missing_files and delete_files:
            result["missing_files"] = missing_files
            msg_parts.append(f"{len(missing_files)} 个文件已不存在")

        json_response(self, 200, data=result, message="，".join(msg_parts))

    def _clear_tasks(self, body: dict):
        status = body.get("status")
        if status:
            status = str(status).strip().upper()
        if status and status != "ALL" and status not in VALID_STATUSES:
            if _global_logger:
                _global_logger.warning(f"Invalid status filter: {status}, VALID_STATUSES={VALID_STATUSES}")
            json_response(self, 400, message=f"Invalid status: {status}")
            return
        if status and status == "ALL":
            status = None
        _global_task_manager.clear_tasks(status=status)
        json_response(self, 200, message="Tasks cleared", data={"status": status or "all"})

    def _retry_task(self, task_id: str):
        task = _global_task_manager.retry_task(task_id)
        if task is None:
            json_response(self, 400, message=f"任务不存在或当前状态不可重试: {task_id}")
            return

        if _global_pipeline and not _global_pipeline.is_paused():
            def run_retry():
                try:
                    _global_pipeline.process_one(task)
                except Exception as e:
                    _global_logger.error(f"重试任务执行异常: {e}")
            threading.Thread(target=run_retry, daemon=True).start()

        json_response(self, 200, data={"task": task}, message="任务已重试并开始执行")

    def _queue_retry_all(self):
        retried = _global_task_manager.retry_all_failed()

        if retried and _global_pipeline and not _global_pipeline.is_paused():
            def run_retry_all():
                try:
                    _global_pipeline.run_all()
                except Exception as e:
                    _global_logger.error(f"批量重试执行异常: {e}")
            threading.Thread(target=run_retry_all, daemon=True).start()

        json_response(self, 200, data={
            "retried_count": len(retried),
            "task_ids": [t.get("task_id", "") for t in retried]
        }, message=f"已重试 {len(retried)} 个失败任务并开始执行")

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

    def _restart_service(self):
        try:
            if _global_pipeline:
                _global_pipeline.pause()
            if _global_watcher:
                _global_watcher.stop()

            trim_pkgvar = os.environ.get("TRIM_PKGVAR", "")
            if trim_pkgvar:
                cmd_main = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                        "..", "cmd", "main")
                if not os.path.isfile(cmd_main):
                    cmd_main = "/var/apps/nas-media-importer/cmd/main"

                def do_fnos_restart():
                    time.sleep(0.5)
                    try:
                        subprocess.run([cmd_main, "stop"], timeout=15, capture_output=True)
                        time.sleep(1)
                        subprocess.run([cmd_main, "start"], timeout=15, capture_output=True)
                    except Exception:
                        pass

                json_response(self, 200, message="服务正在重启，请等待约5秒后刷新页面...")
                threading.Thread(target=do_fnos_restart, daemon=True).start()
            else:
                json_response(self, 200, message="服务正在重启...")
                threading.Timer(1.0, lambda: os.execv(sys.executable, [sys.executable] + sys.argv)).start()
        except Exception as e:
            json_response(self, 500, message="重启失败: " + str(e))

    def _config_reload(self):
        global _config, _global_pipeline, _global_notifier, _global_watcher
        try:
            config_path = _config.get("_config_path") if _config else None
            new_config = load_config(config_path) if config_path else load_config()

            if _global_task_manager and _global_task_manager.has_running_tasks():
                json_response(self, 400, message="当前有任务正在执行，请等待任务完成后再重载配置")
                return

            _config.clear()
            _config.update(new_config)

            if _global_pipeline:
                _global_pipeline.config = _config
                from media_importer.llm_scraper import LLMScraper
                _global_pipeline.scraper = LLMScraper(_config)
                _global_pipeline.copier = type(_global_pipeline.copier)(_config.get('temp_dir', ''))

            hermes_cfg = _config.get("hermes", {})
            if hermes_cfg.get("enabled", False):
                _global_notifier = HermesNotifier(_config)
            else:
                _global_notifier = None

            if _global_pipeline:
                _global_pipeline.notifier = _global_notifier

            self._reload_watcher()

            json_response(self, 200, message="配置已重载并生效")
        except Exception as e:
            json_response(self, 500, message="配置重载失败: " + str(e))

    def _reload_watcher(self):
        global _global_watcher
        if _global_watcher:
            _global_watcher.stop()
            _global_watcher = None

        watcher_cfg = _config.get("file_watcher", {})
        if watcher_cfg.get("enabled", False):
            def on_new_files(new_files):
                if _global_pipeline and not _global_pipeline.is_paused():
                    try:
                        _global_pipeline.run_all()
                    except Exception as e:
                        _global_logger.error("批量处理异常: " + str(e))

            _global_watcher = FileWatcher(_config, on_new_files=on_new_files, logger=_global_logger)
            _global_watcher.start()
            _global_logger.info("文件监控已应用新配置并重启: "
                                f"enabled={watcher_cfg.get('enabled')}, "
                                f"poll_interval={watcher_cfg.get('poll_interval')}s")
        else:
            _global_logger.info("文件监控已停用（配置 enabled=false）")

    def _get_real_config_value(self, *path) -> str:
        if _config:
            value = _config
            for key in path:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    value = ""
                    break
            if isinstance(value, str) and not self._is_masked_value(value) and value:
                return value
        config_path = _config.get("_config_path") if _config else None
        if not config_path or not os.path.isfile(config_path):
            return ""
        try:
            import yaml as _yaml
            with open(config_path, "r", encoding="utf-8") as f:
                file_config = _yaml.safe_load(f)
            value = file_config
            for key in path:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    return ""
            return value if isinstance(value, str) else str(value) if value else ""
        except Exception:
            return ""

    def _config_test_llm(self, body: dict):
        base_url = body.get("base_url", "")
        api_key = body.get("api_key", "")
        model = body.get("model", "")
        provider = body.get("provider", "openai")

        if not api_key or self._is_masked_value(api_key):
            api_key = self._get_real_config_value("llm", "api_key")
            if not api_key:
                json_response(self, 200, data={"success": False, "message": "API Key 未配置"})
                return

        if not base_url or self._is_masked_value(base_url):
            base_url = self._get_real_config_value("llm", "base_url")
            if not base_url:
                json_response(self, 200, data={"success": False, "message": "API 地址未配置"})
                return

        if not model:
            model = self._get_real_config_value("llm", "model")
            if not model:
                json_response(self, 200, data={"success": False, "message": "模型名称未配置"})
                return

        try:
            from config_validator import test_llm_api
            ok, msg = test_llm_api(base_url, api_key, model, timeout=15)
            json_response(self, 200, data={"success": ok, "message": msg})
        except Exception as e:
            json_response(self, 200, data={"success": False, "message": "测试异常: " + str(e)})

    def _config_test_hermes(self, body: dict):
        base_url = body.get("base_url", "")
        route_name = body.get("route_name", "")
        secret = body.get("secret", "")

        if not base_url or self._is_masked_value(base_url):
            base_url = self._get_real_config_value("hermes", "webhook", "base_url")
        if not route_name:
            route_name = self._get_real_config_value("hermes", "webhook", "route_name")
        if not secret or self._is_masked_value(secret):
            secret = self._get_real_config_value("hermes", "webhook", "secret")

        if not base_url:
            json_response(self, 200, data={"success": False, "message": "Webhook 地址未配置"})
            return

        if not route_name:
            json_response(self, 200, data={"success": False, "message": "路由名称未配置"})
            return

        try:
            from config_validator import test_hermes_webhook
            ok, msg = test_hermes_webhook(base_url, route_name, secret, timeout=15)
            json_response(self, 200, data={"success": ok, "message": msg})
        except Exception as e:
            json_response(self, 200, data={"success": False, "message": "测试异常: " + str(e)})

    def _config_test_tmdb(self, body: dict):
        api_key = body.get("api_key", "")

        if not api_key or self._is_masked_value(api_key):
            api_key = self._get_real_config_value("metadata", "tmdb", "api_key")
            if not api_key:
                json_response(self, 200, data={"success": False, "message": "API Key 未配置"})
                return

        try:
            from tmdb_client import TMDbClient
            client = TMDbClient(api_key)
            ok = client.test_connection()
            msg = "连接成功" if ok else "连接失败，请检查 API Key 是否正确"
            json_response(self, 200, data={"success": ok, "message": msg})
        except Exception as e:
            json_response(self, 200, data={"success": False, "message": "测试异常: " + str(e)})

    def _config_check_permission(self, body: dict):
        try:
            from permission_checker import check_config_permissions
            cfg_to_check = body if body else (_config or {})
            result = check_config_permissions(cfg_to_check)
            json_response(self, 200, data=result, message="权限检测完成")
        except Exception as e:
            json_response(self, 500, message=f"权限检测异常: {e}")

    def _path_test(self, body: dict):
        try:
            path = (body or {}).get("path", "").strip()
            need_write = bool((body or {}).get("need_write", True))
            if not path:
                json_response(self, 400, message="path 参数必填")
                return
            from permission_checker import check_path_permission, get_current_user
            result = check_path_permission(path, need_write=need_write)
            result["user"] = get_current_user()
            json_response(self, 200, data=result, message=result["message"])
        except Exception as e:
            json_response(self, 500, message=f"路径测试异常: {e}")

    def _config_validate(self):
        """基础配置验证：路径、格式、有效性检查（不含LLM和Hermes连通性）"""
        try:
            results = validate_config(_config, test_llm=False, test_hermes=False)
            json_response(self, 200, data=results, message="配置验证完成: " + results['overall'])
        except Exception as e:
            json_response(self, 500, message="配置验证失败: " + str(e))

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

        from safety import validate_path_safety, validate_file_ext, ALLOWED_MEDIA_EXTS

        source_dir = _config.get("source_dir", "") if _config else ""
        allowed_dirs = [source_dir] if source_dir else []

        ok, msg = validate_path_safety(file_path, allowed_base_dirs=allowed_dirs)
        if not ok:
            json_response(self, 400, message=f"路径校验失败: {msg}")
            return

        ok, msg = validate_file_ext(file_path, ALLOWED_MEDIA_EXTS)
        if not ok:
            json_response(self, 400, message=f"文件类型校验失败: {msg}")
            return

        if not os.path.isfile(file_path):
            json_response(self, 404, message=f"File not found: {file_path}")
            return

        def run_one():
            video_file = os.path.basename(file_path)
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

    def _task_confirm(self, task_id: str):
        if _global_pipeline is None:
            json_response(self, 500, message="Pipeline not initialized")
            return
        try:
            ok = _global_pipeline.confirm_task(task_id)
            if ok:
                json_response(self, 200, message="任务确认入库成功")
            else:
                task = _global_task_manager.get_task(task_id)
                err = task.get("error_message", "") if task else ""
                json_response(self, 500, message="确认入库失败" + (f": {err}" if err else ""))
        except Exception as e:
            json_response(self, 400, message=str(e))

    def _task_reclassify(self, task_id: str, body: dict):
        if _global_pipeline is None:
            json_response(self, 500, message="Pipeline not initialized")
            return
        dimensions = body.get("dimensions", {})
        if not dimensions:
            json_response(self, 400, message="缺少 dimensions 参数")
            return
        try:
            task = _global_pipeline.reclassify_task(task_id, dimensions)
            json_response(self, 200, data={"task": task}, message="重新分类完成")
        except Exception as e:
            json_response(self, 400, message=str(e))

    def _task_ignore(self, task_id: str):
        task = _global_task_manager.get_task(task_id)
        if task is None:
            json_response(self, 404, message=f"Task not found: {task_id}")
            return
        current_status = task.get("status", "")
        if current_status not in ("FAILED", "CONFIRMING"):
            json_response(self, 400, message=f"当前状态不可忽略: {current_status}")
            return
        source_policy = _config.get("source_policy", {}) if _config else {}
        quarantine_dir = source_policy.get("quarantine_dir", "")
        file_location = task.get("file_location", "source")

        if file_location == "temp":
            temp_video = task.get("video_path", "")
            if quarantine_dir and temp_video and os.path.exists(temp_video):
                os.makedirs(quarantine_dir, exist_ok=True)
                dest_video = TaskManager._resolve_dest_path(
                    quarantine_dir, os.path.basename(temp_video))
                try:
                    shutil.move(temp_video, dest_video)
                except (OSError, shutil.Error):
                    dest_video = temp_video
                subtitle_paths = task.get("subtitle_files", [])
                new_sub_paths = {}
                for sub in subtitle_paths:
                    if sub and os.path.exists(sub):
                        dest_sub = TaskManager._resolve_dest_path(
                            quarantine_dir, os.path.basename(sub))
                        try:
                            shutil.move(sub, dest_sub)
                            new_sub_paths[os.path.basename(sub)] = dest_sub
                        except (OSError, shutil.Error):
                            pass
                if new_sub_paths:
                    subs = db_get_subtitles(_global_task_manager.conn, task_id)
                    for sub in subs:
                        sub_basename = os.path.basename(
                            sub.get("source_path", "") or sub.get("target_path", ""))
                        if sub_basename in new_sub_paths:
                            db_update_subtitle(
                                _global_task_manager.conn, sub["id"],
                                target_path=new_sub_paths[sub_basename])
                db_update_task(_global_task_manager.conn, task_id,
                               status="SKIPPED",
                               skip_reason="用户忽略",
                               source_path=dest_video,
                               source_filename=os.path.basename(dest_video),
                               file_location="quarantine",
                               video_path="")
            else:
                temp_dir = _config.get('temp_dir', '') if _config else ''
                if temp_video and temp_dir and str(temp_video).startswith(temp_dir) and os.path.exists(temp_video):
                    try:
                        os.remove(temp_video)
                    except OSError:
                        pass
                    for sub in (task.get("subtitle_files") or []):
                        sub_str = str(sub) if sub else ""
                        if sub_str and os.path.exists(sub_str) and temp_dir in sub_str:
                            try:
                                os.remove(sub_str)
                            except OSError:
                                pass
                db_update_subtitles_by_task(
                    _global_task_manager.conn, task_id,
                    status="FAILED", target_path="")
                db_update_task(_global_task_manager.conn, task_id,
                               status="SKIPPED",
                               skip_reason="用户忽略",
                               file_location="source")
        else:
            source_path = task.get("source_path", "")
            subtitle_paths = task.get("subtitle_files", [])
            if quarantine_dir and source_path and os.path.exists(source_path):
                _global_task_manager.move_to_quarantine(
                    task_id=task_id,
                    source_path=source_path,
                    subtitle_paths=subtitle_paths if isinstance(subtitle_paths, list) else [],
                    quarantine_dir=quarantine_dir,
                )
                db_update_task(_global_task_manager.conn, task_id,
                               status="SKIPPED",
                               skip_reason="用户忽略",
                               error_message=f"已移入隔离区: {quarantine_dir}")
            else:
                db_update_task(_global_task_manager.conn, task_id,
                               status="SKIPPED",
                               skip_reason="用户忽略")
        json_response(self, 200, message="任务已忽略")

    def _task_subtitles(self, task_id: str):
        subs = db_get_subtitles(_global_task_manager.conn, task_id)
        json_response(self, 200, data={"subtitles": subs, "total": len(subs)})

    def _task_rename(self, task_id: str, body: dict):
        new_filename = (body.get("new_filename") or "").strip()
        if not new_filename:
            json_response(self, 400, message="new_filename 参数必填")
            return
        task = _global_task_manager.get_task(task_id)
        if task is None:
            json_response(self, 404, message=f"Task not found: {task_id}")
            return
        file_location = task.get("file_location", "source")
        if file_location == "deleted":
            json_response(self, 400, message="文件已删除，无法重命名")
            return
        if file_location == "import":
            current_path = task.get("import_video_path", "")
        elif file_location == "temp":
            current_path = task.get("video_path", "")
        elif file_location == "quarantine":
            current_path = task.get("source_path", "")
        else:
            current_path = task.get("source_path", "")
        if not current_path or not os.path.exists(current_path):
            json_response(self, 400, message=f"当前文件路径不存在: {current_path}")
            return
        current_dir = os.path.dirname(current_path)
        new_path = os.path.join(current_dir, new_filename)
        if os.path.exists(new_path) and new_path != current_path:
            json_response(self, 400, message=f"目标文件名已存在: {new_filename}")
            return
        try:
            os.rename(current_path, new_path)
        except OSError as e:
            json_response(self, 500, message=f"重命名失败: {e}")
            return
        update_fields = {"source_filename": new_filename}
        if file_location == "import":
            update_fields["import_video_path"] = new_path
            update_fields["final_filename"] = new_filename
        elif file_location == "temp":
            update_fields["video_path"] = new_path
        elif file_location in ("source", "quarantine"):
            update_fields["source_path"] = new_path
        db_update_task(_global_task_manager.conn, task_id, **update_fields)
        updated_task = _global_task_manager.get_task(task_id)
        json_response(self, 200, data={"task": updated_task}, message="文件重命名成功")

    def _task_confirm_all(self):
        if _global_pipeline is None:
            json_response(self, 500, message="Pipeline not initialized")
            return
        confirming_tasks = _global_task_manager.list_tasks(status="CONFIRMING", limit=1000)
        results = []
        for t in confirming_tasks:
            tid = t.get("task_id", "")
            try:
                ok = _global_pipeline.confirm_task(tid)
                results.append({"task_id": tid, "success": ok})
            except Exception as e:
                results.append({"task_id": tid, "success": False, "error": str(e)})
        success_count = sum(1 for r in results if r["success"])
        json_response(self, 200, data={
            "results": results,
            "total": len(results),
            "success": success_count,
            "failed": len(results) - success_count,
        }, message=f"批量确认完成: 成功 {success_count}, 失败 {len(results) - success_count}")

    def _task_stats(self):
        if _global_task_manager is None:
            json_response(self, 500, message="TaskManager not initialized")
            return
        counts = _global_task_manager.count_by_status()
        json_response(self, 200, data={"by_status": counts})

    def _logs(self, query: dict):
        limit = int(query.get("limit", [100])[0])
        task_id = query.get("task_id", [None])[0]

        if _global_logger:
            result_lines = _global_logger.get_recent_logs(limit=limit, task_id=task_id)
        else:
            result_lines = []

        json_response(self, 200, data={"logs": result_lines})

    def log_message(self, protocol, fmt, *args):
        pass

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
        elif path == "/api/config/prompts/tmdb":
            prompts_data = self._load_tmdb_prompts_for_ui()
            json_response(self, 200, data=prompts_data)
        elif path == "/api/config/prompts/reset":
            self._config_reset_prompts()
        elif path == "/api/config/prompts/tmdb/reset":
            self._config_reset_tmdb_prompts()
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
        elif path.startswith("/api/dimensions/"):
            dim_name = path.split("/api/dimensions/")[1].rstrip("/")
            self._dimension_get(dim_name)
        else:
            self._serve_static_file(path.lstrip("/"))

    def _serve_static_file(self, filename):
        file_path = os.path.join(WEBUI_DIR, filename)
        real_path = os.path.realpath(file_path)
        if not real_path.startswith(os.path.realpath(WEBUI_DIR)):
            json_response(self, 403, message="Access denied")
            return
        if not os.path.isfile(file_path):
            json_response(self, 404, message=f"File not found: {filename}")
            return

        try:
            with open(file_path, "rb") as f:
                content = f.read()
        except Exception as e:
            json_response(self, 500, message=f"Failed to read file: {e}")
            return

        content_type = "text/html"
        if filename.endswith(".css"):
            content_type = "text/css"
        elif filename.endswith(".js"):
            content_type = "application/javascript"
        elif filename.endswith(".png"):
            content_type = "image/png"
        elif filename.endswith(".svg"):
            content_type = "image/svg+xml"

        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Frame-Options", "ALLOWALL")
        self.send_header("Content-Security-Policy", "frame-ancestors *")
        self.end_headers()
        self.wfile.write(content)
        self.wfile.flush()

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
        elif path == "/api/config/test-tmdb":
            self._config_test_tmdb(body)
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
        elif path == "/api/config/prompts/tmdb":
            self._config_save_tmdb_prompts(body)
        elif path == "/api/config/prompts/reset":
            self._config_reset_prompts()
        elif path == "/api/config/prompts/tmdb/reset":
            self._config_reset_tmdb_prompts()
        elif path.startswith("/api/dimensions/") and path.endswith("/enable"):
            dim_name = path.split("/api/dimensions/")[1].replace("/enable", "")
            self._dimension_enable(dim_name)
        elif path.startswith("/api/dimensions/") and path.endswith("/disable"):
            dim_name = path.split("/api/dimensions/")[1].replace("/disable", "")
            self._dimension_disable(dim_name)
        elif path.startswith("/api/dimensions/") and path.endswith("/reset"):
            dim_name = path.split("/api/dimensions/")[1].replace("/reset", "")
            self._dimension_reset(dim_name)
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

    def _config_save_section(self, body: dict):
        section = body.get("section", "")
        data = body.get("data", {})

        if not section or not data:
            json_response(self, 400, message="缺少 section 或 data 参数")
            return

        section_map = {
            "basic": ["source_dir", "temp_dir", "source_policy"],
            "path_rules": ["path_rules", "fallback_dir"],
            "import_options": ["manual_review", "duplicate_handling", "filename_templates"],
            "metadata.tmdb": ["metadata"],
            "llm": ["llm"],
            "server": ["server"],
            "hermes": ["hermes"],
            "file_watcher": ["file_watcher"],
            "advanced": ["log_dir", "task_queue"],
        }

        if section not in section_map:
            json_response(self, 400, message=f"未知的配置区块: {section}")
            return

        try:
            section_body = {}
            for key in section_map[section]:
                if key in data:
                    section_body[key] = data[key]

            if not section_body:
                json_response(self, 400, message="区块数据为空")
                return

            self._config_save(section_body)
        except Exception as e:
            json_response(self, 500, message=f"保存区块配置失败: {str(e)}")

    def _config_save(self, body: dict):
        """保存配置到文件，保留原有格式和注释"""
        global _config
        if not body:
            json_response(self, 400, message="Empty config")
            return

        try:
            config_path = _config.get("_config_path") if _config else None
            if not config_path:
                json_response(self, 500, message="Config path not found")
                return

            from ruamel.yaml import YAML
            from ruamel.yaml.comments import CommentedMap
            from ruamel.yaml.scalarstring import SingleQuotedScalarString, DoubleQuotedScalarString

            yaml = YAML()
            yaml.preserve_quotes = True
            yaml.width = 120

            with open(config_path, "r", encoding="utf-8") as f:
                config_doc = yaml.load(f)

            config_to_save = self._filter_sensitive_fields(body, config_doc)

            YAML_RESERVED_WORDS = {'true', 'false', 'yes', 'no', 'on', 'off', 'null', '~'}
            YAML_SPECIAL_CHARS = set('{}:#&*!|>\'\"')

            def _needs_quote(value):
                if not isinstance(value, str):
                    return False
                if value.lower() in YAML_RESERVED_WORDS:
                    return True
                if any(c in value for c in YAML_SPECIAL_CHARS):
                    return True
                if ' ' in value:
                    return True
                if value and value[0].isdigit():
                    try:
                        float(value)
                        return True
                    except ValueError:
                        pass
                return False

            def _quote_value(value):
                if isinstance(value, str) and _needs_quote(value):
                    return SingleQuotedScalarString(value)
                return value

            def _was_quoted(value):
                return isinstance(value, (SingleQuotedScalarString, DoubleQuotedScalarString))

            def _process_list(new_list, old_list=None):
                result = []
                for i, item in enumerate(new_list):
                    old_item = None
                    if old_list and i < len(old_list):
                        old_item = old_list[i]
                    if isinstance(item, dict):
                        old_dict = old_item if isinstance(old_item, (dict, CommentedMap)) else None
                        result.append(_process_dict(item, old_dict))
                    elif isinstance(item, str):
                        result.append(_quote_value(item))
                    elif isinstance(item, bool):
                        result.append(item)
                    else:
                        result.append(item)
                return result

            def _process_dict(new_dict, old_dict=None):
                result = CommentedMap()
                for k, v in new_dict.items():
                    old_val = None
                    if old_dict and k in old_dict:
                        old_val = old_dict[k]
                    if isinstance(v, dict):
                        old_sub = old_val if isinstance(old_val, (dict, CommentedMap)) else None
                        result[k] = _process_dict(v, old_sub)
                    elif isinstance(v, list):
                        old_sub_list = old_val if isinstance(old_val, list) else None
                        result[k] = _process_list(v, old_sub_list)
                    elif isinstance(v, str):
                        result[k] = _quote_value(v)
                    elif isinstance(v, bool):
                        result[k] = v
                    else:
                        result[k] = v
                return result

            def update_nested(target, source):
                for key, value in source.items():
                    if key == "_config_path":
                        continue
                    if key == "hooks":
                        continue
                    if isinstance(value, dict):
                        if key in target and isinstance(target.get(key), (dict, CommentedMap)):
                            update_nested(target[key], value)
                        else:
                            target[key] = _process_dict(value)
                    elif isinstance(value, list):
                        old_list = target.get(key) if isinstance(target, (dict, CommentedMap)) else None
                        target[key] = _process_list(value, old_list)
                    elif isinstance(value, str):
                        target[key] = _quote_value(value)
                    elif isinstance(value, bool):
                        target[key] = value
                    else:
                        target[key] = value

            update_nested(config_doc, config_to_save)

            def _normalize_quotes(doc):
                if isinstance(doc, (dict, CommentedMap)):
                    for key in list(doc.keys()):
                        value = doc[key]
                        if isinstance(value, bool):
                            doc[key] = value
                        elif isinstance(value, str) and not _was_quoted(value):
                            if _needs_quote(value):
                                doc[key] = SingleQuotedScalarString(value)
                        elif isinstance(value, list):
                            _normalize_list_quotes(value)
                        elif isinstance(value, (dict, CommentedMap)):
                            _normalize_quotes(value)

            def _normalize_list_quotes(lst):
                for i in range(len(lst)):
                    item = lst[i]
                    if isinstance(item, (dict, CommentedMap)):
                        _normalize_quotes(item)
                    elif isinstance(item, bool):
                        lst[i] = item
                    elif isinstance(item, str) and not _was_quoted(item):
                        if _needs_quote(item):
                            lst[i] = SingleQuotedScalarString(item)

            _normalize_quotes(config_doc)

            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config_doc, f)

            has_running_tasks = _global_task_manager and _global_task_manager.has_running_tasks()

            if has_running_tasks:
                global _config_dirty
                _config_dirty = True
                json_response(self, 200, message="配置已保存到文件。当前有任务正在执行，任务完成后自动同步内存配置，或点击「重载配置」立即生效（可能影响正在执行的任务）")
            else:
                if isinstance(_config, dict):
                    self._update_config_safely(_config, body)
                quarantine_dir = _config.get("source_policy", {}).get("quarantine_dir", "")
                if quarantine_dir and not os.path.exists(quarantine_dir):
                    try:
                        os.makedirs(quarantine_dir, exist_ok=True)
                    except OSError:
                        pass

                if "file_watcher" in body:
                    try:
                        self._reload_watcher()
                        json_response(self, 200, message="轮询监控配置已保存并立即生效")
                        return
                    except Exception as e:
                        _global_logger.error(f"文件监控配置更新后重启失败: {e}")

                json_response(self, 200, message="配置已保存并生效")
        except Exception as e:
            import traceback
            error_msg = f"保存配置失败: {e}\n{traceback.format_exc()}"
            json_response(self, 500, message=error_msg)

    def _filter_sensitive_fields(self, body: dict, original_config: dict) -> dict:
        """
        过滤敏感字段：如果前端传入的敏感字段值是掩码形式，
        则从请求体中删除该字段，保留原配置文件中的值；
        同时禁止通过API修改hooks配置（防止RCE）
        """
        import copy
        filtered = copy.deepcopy(body)
        
        sensitive_fields = [
            ("server", "api_key"),
            ("llm", "api_key"),
            ("metadata", "tmdb", "api_key"),
            ("hermes", "webhook", "secret"),
        ]
        
        for field_path in sensitive_fields:
            current_value = self._get_nested_value(filtered, field_path)
            if current_value and self._is_masked_value(current_value):
                self._delete_nested_path(filtered, field_path)
        
        if "hooks" in filtered:
            del filtered["hooks"]
        
        return filtered
    
    def _get_nested_value(self, obj: dict, path: tuple) -> any:
        """获取嵌套字典中的值"""
        current = obj
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current
    
    def _delete_nested_path(self, obj: dict, path: tuple):
        """删除嵌套字典中的路径"""
        if len(path) == 0:
            return
        
        current = obj
        for key in path[:-1]:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return
        
        if len(path) == 1:
            if path[0] in current:
                del current[path[0]]
        else:
            last_key = path[-1]
            if last_key in current:
                del current[last_key]
    
    def _is_masked_value(self, value: str) -> bool:
        if not isinstance(value, str):
            return False
        return "***" in value

    def _update_config_safely(self, target: dict, source: dict):
        if not isinstance(target, dict) or not isinstance(source, dict):
            return
        for key, value in source.items():
            if key == "_config_path":
                continue
            if key == "hooks":
                continue
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                self._update_config_safely(target[key], value)
            elif isinstance(value, str) and self._is_masked_value(value):
                pass
            else:
                target[key] = value

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

    def _dimensions_list(self):
        try:
            dims = db_get_all_dimensions(_global_task_manager.conn)
            json_response(self, 200, data={"dimensions": dims, "total": len(dims)})
        except Exception as e:
            json_response(self, 500, message=f"获取维度列表失败: {e}")

    def _dimensions_enabled(self):
        try:
            dims = db_get_enabled_dimensions(_global_task_manager.conn)
            json_response(self, 200, data={"dimensions": dims, "total": len(dims)})
        except Exception as e:
            json_response(self, 500, message=f"获取已启用维度失败: {e}")

    def _dimension_get(self, name: str):
        try:
            dim = db_get_dimension(_global_task_manager.conn, name)
            if dim is None:
                json_response(self, 404, message=f"维度不存在: {name}")
                return
            json_response(self, 200, data=dim)
        except Exception as e:
            json_response(self, 500, message=f"获取维度失败: {e}")

    def _dimension_update(self, name: str, body: dict):
        try:
            dim = db_get_dimension(_global_task_manager.conn, name)
            if dim is None:
                json_response(self, 404, message=f"维度不存在: {name}")
                return
            allowed = {}
            for key in ("label", "ai_prompt", "tmdb_field", "value_list", "color", "description"):
                if key in body:
                    allowed[key] = body[key]
            if not allowed:
                json_response(self, 400, message="无有效更新字段")
                return
            updated = db_update_dimension(_global_task_manager.conn, name, **allowed)
            json_response(self, 200, data=updated, message="维度配置已更新")
        except Exception as e:
            json_response(self, 500, message=f"更新维度失败: {e}")

    def _dimension_enable(self, name: str):
        try:
            dim = db_get_dimension(_global_task_manager.conn, name)
            if dim is None:
                json_response(self, 404, message=f"维度不存在: {name}")
                return
            required_tier = dim.get("required_tier", "free")
            if required_tier != "free" and not check_tier_access(required_tier):
                json_response(self, 403, message=f"该维度需要 {required_tier.upper()} 许可")
                return
            updated = db_enable_dimension(_global_task_manager.conn, name)
            json_response(self, 200, data=updated, message=f"维度 {dim.get('label', name)} 已启用")
        except Exception as e:
            json_response(self, 500, message=f"启用维度失败: {e}")

    def _dimension_disable(self, name: str):
        try:
            dim = db_get_dimension(_global_task_manager.conn, name)
            if dim is None:
                json_response(self, 404, message=f"维度不存在: {name}")
                return
            updated = db_disable_dimension(_global_task_manager.conn, name)
            json_response(self, 200, data=updated, message=f"维度 {dim.get('label', name)} 已禁用")
        except Exception as e:
            json_response(self, 500, message=f"禁用维度失败: {e}")

    def _dimension_reset(self, name: str):
        try:
            dim = db_get_dimension(_global_task_manager.conn, name)
            if dim is None:
                json_response(self, 404, message=f"维度不存在: {name}")
                return
            updated = db_reset_dimension(_global_task_manager.conn, name)
            if updated is None:
                json_response(self, 500, message="恢复默认失败: 缺少默认配置")
                return
            json_response(self, 200, data=updated, message=f"维度 {dim.get('label', name)} 已恢复默认配置")
        except Exception as e:
            json_response(self, 500, message=f"恢复默认失败: {e}")

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
            log_dir = _config.get("log_dir", "") if _config else ""
            checks["log_dir_path"] = log_dir
            if os.path.isdir(log_dir):
                ok, _ = check_write_permission(log_dir)
                checks["log_dir"] = "ok" if ok else "no_write_permission"
            else:
                checks["log_dir"] = "error"
        except Exception:
            checks["log_dir"] = "error"
            overall = "degraded"

        try:
            llm_config = _config.get("llm", {})
            api_key = llm_config.get("api_key", "")
            checks["llm_api"] = "ok" if api_key else "skipped"
        except Exception:
            checks["llm_api"] = "skipped"

        try:
            hermes_enabled = _config.get("hermes", {}).get("enabled", False)
            checks["hermes"] = "ok" if hermes_enabled else "disabled"
        except Exception:
            checks["hermes"] = "disabled"

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
        prompts_data = self._load_prompts_for_ui()
        tmdb_data = self._load_tmdb_prompts_for_ui()
        prompts_data["tmdb_system_prompt"] = tmdb_data.get("system_prompt", "")
        json_response(self, 200, data={"config": masked, "prompts": prompts_data})

    def _load_prompts_for_ui(self) -> dict:
        """
        读取提示词上半部返回前端展示。
        优先级：scraper_prompts.md（用户） > scraper_prompts.example.md（出厂默认）
        """
        try:
            config_path = _config.get("_config_path") if _config else None
            if config_path:
                prompts_dir = os.path.dirname(os.path.dirname(os.path.abspath(config_path)))
            else:
                prompts_dir = os.path.dirname(os.path.abspath(__file__))

            user_file = os.path.join(prompts_dir, "config", "scraper_prompts.md")
            example_file = os.path.join(prompts_dir, "config", "scraper_prompts.example.md")

            import yaml as _yaml

            sp = ""
            using_custom = False

            if os.path.isfile(user_file):
                with open(user_file, "r", encoding="utf-8") as f:
                    content = f.read()
                if "system_prompt:" in content:
                    data = _yaml.safe_load(content)
                    if data and isinstance(data, dict):
                        sp = (data.get("system_prompt") or "").strip()
                        using_custom = bool(sp)

            if not sp and os.path.isfile(example_file):
                data = _yaml.safe_load(open(example_file, "r", encoding="utf-8").read())
                if data and isinstance(data, dict):
                    sp = (data.get("system_prompt") or "").strip()
                    using_custom = False

            if not sp:
                from media_importer.llm_scraper import LLMScraper
                ds = LLMScraper.DEFAULT_SYSTEM_PROMPT
                SEP = "【维度判断】\n当前需要判断的维度："
                if ds.endswith(SEP):
                    ds = ds[:-len(SEP)]
                return {"system_prompt": ds, "using_custom": False}

            return {"system_prompt": sp, "using_custom": using_custom}
        except Exception as e:
            import sys, traceback
            print(f"[ERROR] _load_prompts_for_ui failed: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            return {"system_prompt": "", "using_custom": False}

    def _load_tmdb_prompts_for_ui(self) -> dict:
        try:
            config_path = _config.get("_config_path") if _config else None
            if config_path:
                prompts_dir = os.path.dirname(os.path.dirname(os.path.abspath(config_path)))
            else:
                prompts_dir = os.path.dirname(os.path.abspath(__file__))

            user_file = os.path.join(prompts_dir, "config", "tmdb_prompts.md")

            import yaml as _yaml

            sp = ""
            using_custom = False

            if os.path.isfile(user_file):
                with open(user_file, "r", encoding="utf-8") as f:
                    content = f.read()
                if "system_prompt:" in content:
                    data = _yaml.safe_load(content)
                    if data and isinstance(data, dict):
                        sp = (data.get("system_prompt") or "").strip()
                        using_custom = bool(sp)

            if not sp:
                from media_importer.llm_scraper import LLMScraper
                ds = LLMScraper.TMDB_CONTEXT_PROMPT
                SEP = "【维度判断】\n当前需要判断的维度："
                if ds.endswith(SEP):
                    ds = ds[:-len(SEP)]
                sp = ds.strip()
                using_custom = False

            return {"system_prompt": sp, "using_custom": using_custom}
        except Exception as e:
            import sys, traceback
            print(f"[ERROR] _load_tmdb_prompts_for_ui failed: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            return {"system_prompt": "", "using_custom": False}

    def _config_save_prompts(self, body: dict):
        """保存提示词到 scraper_prompts.md"""
        try:
            if not body:
                json_response(self, 400, message="Empty body")
                return

            system_prompt = body.get("system_prompt", "").strip()

            config_path = _config.get("_config_path") if _config else None
            if config_path:
                prompts_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(config_path))), "config", "scraper_prompts.md")
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                prompts_file = os.path.join(base_dir, "config", "scraper_prompts.md")

            head_comment = """# ============================================================
# LLM 刮削提示词配置 - 用户自定义
# ============================================================
# 在此文件中修改提示词内容，程序会优先使用此处配置
# 提示词分为两半：上半部（此文件）由您编写，下半部（维度列表+JSON Schema）由程序自动追加
# 如需恢复出厂默认，点击 WebUI 中的 "重置为默认" 即可

"""

            from ruamel.yaml import YAML
            from ruamel.yaml.scalarstring import LiteralScalarString

            yaml = YAML()
            yaml.preserve_quotes = True
            yaml.width = 120

            doc = {}
            if system_prompt:
                doc["system_prompt"] = LiteralScalarString(system_prompt)

            with open(prompts_file, "w", encoding="utf-8") as f:
                f.write(head_comment)
                yaml.dump(doc, f)

            json_response(self, 200, message="提示词已保存，重启服务后生效")
        except Exception as e:
            json_response(self, 500, message="保存提示词失败: " + str(e))

    def _config_reset_prompts(self):
        """恢复出厂默认提示词（删除用户文件，回退到 example.md）"""
        try:
            config_path = _config.get("_config_path") if _config else None
            if config_path:
                prompts_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(config_path))), "config", "scraper_prompts.md")
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                prompts_file = os.path.join(base_dir, "config", "scraper_prompts.md")

            if os.path.isfile(prompts_file):
                os.remove(prompts_file)

            json_response(self, 200, message="已恢复出厂默认提示词，重启服务后生效")
        except Exception as e:
            json_response(self, 500, message="恢复默认提示词失败: " + str(e))

    def _config_save_tmdb_prompts(self, body: dict):
        """保存 TMDB 版提示词到 tmdb_prompts.md"""
        try:
            if not body:
                json_response(self, 400, message="Empty body")
                return

            system_prompt = body.get("system_prompt", "").strip()

            config_path = _config.get("_config_path") if _config else None
            if config_path:
                prompts_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(config_path))), "config", "tmdb_prompts.md")
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                prompts_file = os.path.join(base_dir, "config", "tmdb_prompts.md")

            head_comment = """# ============================================================
# LLM+TMDB 刮削提示词配置
# ============================================================
# 当 TMDb API 命中元数据后，使用此提示词让 AI 整理/校验 TMDb 数据
# 程序会自动追加维度列表和 JSON Schema，此文件只需编写上半部
# 如需恢复出厂默认，点击 WebUI 中的 "重置为默认" 即可

"""
            from ruamel.yaml import YAML
            from ruamel.yaml.scalarstring import LiteralScalarString

            yaml = YAML()
            yaml.preserve_quotes = True
            yaml.width = 120

            doc = {}
            if system_prompt:
                doc["system_prompt"] = LiteralScalarString(system_prompt)

            with open(prompts_file, "w", encoding="utf-8") as f:
                f.write(head_comment)
                yaml.dump(doc, f)

            json_response(self, 200, message="LLM+TMDB 提示词已保存，重启服务后生效")
        except Exception as e:
            json_response(self, 500, message="保存 LLM+TMDB 提示词失败: " + str(e))

    def _config_reset_tmdb_prompts(self):
        try:
            config_path = _config.get("_config_path") if _config else None
            if config_path:
                prompts_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(config_path))), "config", "tmdb_prompts.md")
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                prompts_file = os.path.join(base_dir, "config", "tmdb_prompts.md")

            if os.path.isfile(prompts_file):
                os.remove(prompts_file)

            json_response(self, 200, message="已恢复出厂默认 LLM+TMDB 提示词，重启服务后生效")
        except Exception as e:
            json_response(self, 500, message="恢复 LLM+TMDB 默认提示词失败: " + str(e))

    def _list_tasks(self, query):
        status = query.get("status", [None])[0]
        limit = int(query.get("limit", [20])[0])
        offset = int(query.get("offset", [0])[0])
        show_all = query.get("all", ["false"])[0].lower() == "true"
        page = query.get("page", [None])[0]
        format_mode = query.get("format", ["json"])[0].lower()

        if status:
            status = status.strip().upper()
        if status and status != "ALL" and status not in VALID_STATUSES:
            if _global_logger:
                _global_logger.warning(f"Invalid status filter: {status}, VALID_STATUSES={VALID_STATUSES}")
            json_response(self, 400, message=f"Invalid status: {status}")
            return

        if status and status == "ALL":
            status = None

        if page is not None:
            page_num = int(page)
            page_size = limit
        else:
            page_num = (offset // limit) + 1 if limit > 0 else 1
            page_size = limit

        from db import list_tasks as db_list
        rows, total, total_pages = db_list(
            _global_task_manager.conn,
            page=page_num,
            page_size=page_size,
            status=status,
        )
        counts = _global_task_manager.count_by_status()
        active_count = sum(counts.get(s, 0) for s in ("PENDING", "PROCESSING", "FAILED", "CONFIRMING"))

        json_data = {
            "tasks": rows,
            "total": total,
            "total_pages": total_pages,
            "page": page_num,
            "page_size": page_size,
            "active_count": active_count,
            "by_status": counts,
        }

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
            name = t.get("source_filename", "")
            name_short = (name[:25] + "...") if len(name) > 28 else name
            status = t.get("status", "")
            pct = t.get("percentage", 0)
            scraped = t.get("scrape_result", {})
            error_msg = format_error(t.get("error_message", ""), 20)
            
            title_cn = scraped.get("title_cn", "") or scraped.get("title_en", "") or "?"
            year = scraped.get("year", "")
            result = f"{title_cn}({year})" if year else title_cn
            result_short = (result[:16] + "..") if len(result) > 18 else result
            
            lines.append(f"{name_short:<28} {status_label(status):^8} {pct:>3}%   {result_short:<18} {error_msg:<20}")
    
    return "\n".join(lines)



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
    global _global_pipeline, _global_task_manager, _global_metrics, _global_logger, _global_notifier, _config

    _config = config
    data_dir = config.get("_data_dir",
        os.path.join(os.path.dirname(__file__), "..", "data"))

    try:
        os.makedirs(data_dir, exist_ok=True)
    except (OSError, PermissionError) as e:
        print(f"WARNING: 无法创建数据目录 {data_dir}: {e}", file=sys.stderr)
    _global_task_manager = TaskManager(data_dir, config)
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

    _global_logger.info("API 服务初始化完成")

    _cleanup_orphaned_state(config, _global_task_manager, _global_logger)

    def notify_error(error_type: str, error_message: str, extra_data: dict = None):
        if _global_notifier:
            _global_notifier.notify_program_error(error_type, error_message, extra_data)

    def on_new_files(new_files):
        global _config_dirty
        if _global_pipeline and not _global_pipeline.is_paused():
            try:
                _global_pipeline.run_all()
            except Exception as e:
                _global_logger.error(f"批量处理异常: {e}")
                notify_error("batch_error", str(e), {"new_files": list(new_files)})

        if _config_dirty and not _global_task_manager.has_running_tasks():
            _config_dirty = False
            try:
                config_path = _config.get("_config_path") if _config else None
                if config_path:
                    new_config = load_config(config_path)
                    _config.clear()
                    _config.update(new_config)
                    if _global_pipeline:
                        _global_pipeline.config = _config
                    _global_logger.info("任务完成后自动重载配置")
            except Exception as e:
                _global_logger.error(f"自动重载配置失败: {e}")

    global _global_watcher
    watcher_cfg = config.get("file_watcher", {})
    if watcher_cfg.get("enabled", False):
        _global_watcher = FileWatcher(config, on_new_files=on_new_files, logger=_global_logger)
        _global_watcher.start()
        _global_logger.info(f"文件监控已启用 (轮询间隔 {watcher_cfg.get('poll_interval', 60)}s)")
    else:
        _global_watcher = None
        _global_logger.info("文件监控未启用")

    source_dir = config.get("source_dir", "")
    if source_dir and os.path.isdir(source_dir):
        from file_scanner import scan_source_dir
        try:
            groups = scan_source_dir(source_dir, config)
            if groups:
                _global_logger.info(f"启动时发现 {len(groups)} 个待处理文件")
                def run_initial_batch():
                    global _config_dirty
                    _global_pipeline.run_all()
                    if _config_dirty and not _global_task_manager.has_running_tasks():
                        _config_dirty = False
                        try:
                            config_path = _config.get("_config_path") if _config else None
                            if config_path:
                                new_config = load_config(config_path)
                                _config.clear()
                                _config.update(new_config)
                                if _global_pipeline:
                                    _global_pipeline.config = _config
                                _global_logger.info("任务完成后自动重载配置")
                        except Exception as e:
                            _global_logger.error(f"自动重载配置失败: {e}")
                threading.Thread(target=run_initial_batch, daemon=True).start()
        except Exception as e:
            _global_logger.error(f"启动扫描失败: {e}")

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
    if _global_watcher and _global_watcher.enabled:
        print(f"  文件监控: 已启用 (轮询间隔 {_global_watcher.poll_interval}s)")
    print("")
    print("按 Ctrl+C 停止服务")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        if _global_watcher:
            _global_watcher.stop()
        print("\n服务已停止")
        httpd.shutdown()
