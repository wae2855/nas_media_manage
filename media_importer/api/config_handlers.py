import os

from media_importer.features.configuration import (
    build_config_permission_payload,
    build_config_ui_payload,
    build_path_test_payload,
    build_section_config_update,
    build_watcher_status_payload,
    load_config,
)
from media_importer.api import globals
from media_importer.features.configuration import validate_config
from media_importer.notify.hermes_hook import HermesNotifier
from media_importer.monitor.file_watcher import FileWatcher
from media_importer.core.db import list_tasks as db_list
from .config_save import save_config
from .utils import json_response


class ConfigHandlersMixin:
    def _config(self):
        prompts_data = self._load_prompts_for_ui()
        payload = build_config_ui_payload(globals._config, prompts_data)
        json_response(self, 200, data=payload)

    def _config_save(self, body: dict):
        save_config(self, body, globals_module=globals, respond=json_response)

    def _config_save_section(self, body: dict):
        section = body.get("section", "")
        data = body.get("data", {})

        try:
            section_body = build_section_config_update(section, data, globals._config)
            self._config_save(section_body)
        except (KeyError, ValueError) as e:
            json_response(self, 400, message=str(e))
        except Exception as e:
            json_response(self, 500, message=f"保存区块配置失败: {str(e)}")

    def _config_validate(self):
        try:
            results = validate_config(globals._config, test_llm=False, test_hermes=False)
            json_response(self, 200, data=results, message="配置验证完成: " + results['overall'])
        except Exception as e:
            json_response(self, 500, message="配置验证失败: " + str(e))

    def _config_reload(self):

        try:
            config_path = globals._config.get("_config_path") if globals._config else None
            new_config = load_config(config_path) if config_path else load_config()

            if globals._global_task_manager and globals._global_task_manager.has_running_tasks():
                json_response(self, 400, message="当前有任务正在执行，请等待任务完成后再重载配置")
                return

            globals._config.clear()
            globals._config.update(new_config)

            if globals._global_pipeline:
                globals._global_pipeline.config = globals._config
                from media_importer.features.scraping import LLMScraper
                globals._global_pipeline.scraper = LLMScraper(globals._config)
                globals._global_pipeline.copier = type(globals._global_pipeline.copier)(globals._config.get('temp_dir', ''))

            hermes_cfg = globals._config.get("hermes", {})
            if hermes_cfg.get("enabled", False):
                globals._global_notifier = HermesNotifier(globals._config)
            else:
                globals._global_notifier = None

            if globals._global_pipeline:
                globals._global_pipeline.notifier = globals._global_notifier

            self._reload_watcher()

            json_response(self, 200, message="配置已重载并生效")
        except Exception as e:
            json_response(self, 500, message="配置重载失败: " + str(e))

    def _reload_watcher(self):

        if globals._global_watcher:
            globals._global_watcher.stop()
            globals._global_watcher = None

        watcher_cfg = globals._config.get("file_watcher", {})
        if watcher_cfg.get("enabled", False):
            def on_new_files(new_files):
                if globals._global_pipeline and not globals._global_pipeline.is_paused():
                    try:
                        globals._global_pipeline.run_all()
                    except Exception as e:
                        globals._global_logger.error("批量处理异常: " + str(e))

            globals._global_watcher = FileWatcher(globals._config, on_new_files=on_new_files, logger=globals._global_logger)
            globals._global_watcher.start()
            globals._global_logger.info("文件监控已应用新配置并重启: "
                                f"enabled={watcher_cfg.get('enabled')}, "
                                f"poll_interval={watcher_cfg.get('poll_interval')}s")
        else:
            globals._global_logger.info("文件监控已停用（配置 enabled=false）")

    def _config_check_permission(self, body: dict):
        try:
            from media_importer.monitor.permission_checker import check_config_permissions
            result = build_config_permission_payload(
                body,
                globals._config,
                check_config_permissions,
            )
            json_response(self, 200, data=result, message="权限检测完成")
        except Exception as e:
            json_response(self, 500, message=f"权限检测异常: {e}")

    def _path_test(self, body: dict):
        try:
            from media_importer.monitor.permission_checker import check_path_permission, get_current_user
            result = build_path_test_payload(body, check_path_permission, get_current_user)
            json_response(self, 200, data=result, message=result["message"])
        except ValueError as e:
            json_response(self, 400, message=str(e))
        except Exception as e:
            json_response(self, 500, message=f"路径测试异常: {e}")

    def _watcher_status(self):
        json_response(self, 200, data=build_watcher_status_payload(globals._global_watcher))

    def _watcher_control(self, query):
        action = query.get("action", [None])[0]
        if not globals._global_watcher:
            json_response(self, 400, message="Watcher not initialized")
            return

        if action == "pause":
            globals._global_watcher.stop()
            json_response(self, 200, message="轮询已暂停")
        elif action == "resume":
            globals._global_watcher.start()
            json_response(self, 200, message="轮询已恢复")
        elif action == "status":
            self._watcher_status()
        else:
            json_response(self, 400, message="Invalid action: use pause/resume/status")

    def _list_tasks(self, query):
        from media_importer.core.db import VALID_STATUSES
        status = query.get("status", [None])[0]
        limit = int(query.get("limit", [20])[0])
        offset = int(query.get("offset", [0])[0])
        show_all = query.get("all", ["false"])[0].lower() == "true"
        page = query.get("page", [None])[0]
        format_mode = query.get("format", ["json"])[0].lower()

        if status:
            status = status.strip().upper()
        if status and status != "ALL" and status not in VALID_STATUSES:
            if globals._global_logger:
                globals._global_logger.warning(f"Invalid status filter: {status}, VALID_STATUSES={VALID_STATUSES}")
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

        rows, total, total_pages = db_list(
            globals._global_task_manager.conn,
            page=page_num,
            page_size=page_size,
            status=status,
        )
        counts = globals._global_task_manager.count_by_status()
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
            from .utils import format_tasks_to_text
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

    def _get_real_config_value(self, *path) -> str:
        if globals._config:
            value = globals._config
            for key in path:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    value = ""
                    break
            if isinstance(value, str) and not self._is_masked_value(value) and value:
                return value
        if len(path) >= 3 and path[0] == "metadata":
            provider_type = path[1]
            provider_field = path[2] if len(path) == 3 else None
            if provider_field:
                providers = globals._config.get("metadata", {}).get("providers", []) if globals._config else []
                for p in providers:
                    if p.get("type") == provider_type:
                        val = p.get(provider_field, "")
                        if val and isinstance(val, str) and not self._is_masked_value(val):
                            return val
                        break
        config_path = globals._config.get("_config_path") if globals._config else None
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
                    if len(path) >= 3 and path[0] == "metadata":
                        provider_type = path[1]
                        provider_field = path[2] if len(path) == 3 else None
                        if provider_field:
                            providers = file_config.get("metadata", {}).get("providers", []) if isinstance(file_config, dict) else []
                            for p in providers:
                                if isinstance(p, dict) and p.get("type") == provider_type:
                                    val = p.get(provider_field, "")
                                    if val and isinstance(val, str):
                                        return val
                                    break
                    return ""
            return value if isinstance(value, str) else str(value) if value else ""
        except Exception:
            return ""

    def _filter_sensitive_fields(self, body: dict, original_config: dict) -> dict:
        import copy
        filtered = copy.deepcopy(body)

        sensitive_fields = [
            ("server", "api_key"),
            ("llm", "api_key"),
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
        current = obj
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    def _delete_nested_path(self, obj: dict, path: tuple):
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
