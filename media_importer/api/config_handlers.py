import os

from media_importer.api import globals
from media_importer.features.configuration import (
    apply_runtime_config,
    build_config_permission_payload,
    build_config_ui_payload,
    build_path_test_payload,
    build_section_config_update,
    build_watcher_status_payload,
    inspect_startup_readiness,
    load_config,
    restart_watcher,
    validate_config,
)
from media_importer.features.tasks import list_tasks_for_api

from .config_save import save_config
from .utils import json_response


class ConfigHandlersMixin:
    def _config(self, *, body: dict, params: dict, query: dict):
        payload = build_config_ui_payload(globals._config or {})  # type: ignore[arg-type]
        json_response(self, 200, data=payload)

    def _config_save(self, *, body: dict, params: dict, query: dict):
        save_config(self, body, globals_module=globals, respond=json_response)

    def _config_save_section(self, *, body: dict, params: dict, query: dict):
        section = body.get("section", "")
        data = body.get("data", {})

        try:
            section_body = build_section_config_update(section, data, globals._config or {})  # type: ignore[arg-type]
            if body.get("revision"):
                section_body["_revision"] = body["revision"]
            self._config_save(body=section_body, params={}, query={})
        except (KeyError, ValueError) as e:
            json_response(self, 400, message=str(e))
        except Exception as e:
            json_response(self, 500, message=f"保存区块配置失败: {str(e)}")

    def _config_validate(self, *, body: dict, params: dict, query: dict):
        try:
            results = validate_config(globals._config or {}, test_llm=False)  # type: ignore[arg-type]
            json_response(self, 200, data=results, message="配置验证完成: " + results['overall'])
        except Exception as e:
            json_response(self, 500, message="配置验证失败: " + str(e))

    def _config_startup_readiness(self, *, body: dict, params: dict, query: dict):
        try:
            result = inspect_startup_readiness(globals._config or {})  # type: ignore[arg-type]
            json_response(self, 200, data=result, message="开场检查完成")
        except Exception as e:
            json_response(self, 500, message="开场检查失败: " + str(e))

    def _config_fnos_folders(self, *, body: dict, params: dict, query: dict):
        from media_importer.features.configuration.fnos_directory_access import (
            build_fnos_directory_capability,
        )

        result = build_fnos_directory_capability()
        json_response(self, 200, data=result, message=result["message"])

    def _config_reload(self, *, body: dict, params: dict, query: dict):

        try:
            config_path = globals._config.get("_config_path") if globals._config else None
            new_config = load_config(config_path) if config_path else load_config()

            if globals._global_task_manager and globals._global_task_manager.has_running_tasks():
                json_response(self, 400, message="当前有任务正在执行，请等待任务完成后再重载配置")
                return

            globals._config.clear()
            globals._config.update(new_config)

            components = apply_runtime_config(
                globals._config,  # type: ignore[arg-type]
                globals._global_pipeline,
                current_watcher=globals._global_watcher,
                logger=globals._global_logger,
            )
            globals._global_notifier = components.notifier
            globals._global_watcher = components.watcher

            json_response(self, 200, message="配置已重载并生效")
        except Exception as e:
            json_response(self, 500, message="配置重载失败: " + str(e))

    def _reload_watcher(self, *, body: dict, params: dict, query: dict):
        globals._global_watcher = restart_watcher(
            globals._config,  # type: ignore[arg-type]
            current_watcher=globals._global_watcher,
            pipeline=globals._global_pipeline,
            logger=globals._global_logger,
        )

    def _config_check_permission(self, *, body: dict, params: dict, query: dict):
        try:
            from media_importer.monitor.permission_checker import check_config_permissions
            result = build_config_permission_payload(
                body,
                globals._config or {},  # type: ignore[arg-type]
                check_config_permissions,
            )
            json_response(self, 200, data=result, message="权限检测完成")
        except Exception as e:
            json_response(self, 500, message=f"权限检测异常: {e}")

    def _path_test(self, *, body: dict, params: dict, query: dict):
        try:
            from media_importer.monitor.permission_checker import check_path_permission, get_current_user
            result = build_path_test_payload(body, check_path_permission, get_current_user)
            json_response(self, 200, data=result, message=result["message"])
        except ValueError as e:
            json_response(self, 400, message=str(e))
        except Exception as e:
            json_response(self, 500, message=f"路径测试异常: {e}")

    def _watcher_status(self, *, body: dict, params: dict, query: dict):
        json_response(self, 200, data=build_watcher_status_payload(globals._global_watcher))

    def _watcher_control(self, *, body: dict, params: dict, query: dict):
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
            self._watcher_status(body=body, params=params, query=query)
        else:
            json_response(self, 400, message="Invalid action: use pause/resume/status")

    def _list_tasks(self, *, body: dict, params: dict, query: dict):
        result = list_tasks_for_api(
            query,
            globals._global_task_manager,
            logger=globals._global_logger,
        )
        if result.code != 200:
            json_response(self, result.code, message=result.message)
            return

        if result.format_mode == "text":
            from .utils import format_tasks_to_text
            text_output = format_tasks_to_text(result.data)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(text_output.encode("utf-8"))))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(text_output.encode("utf-8"))
            self.wfile.flush()
        else:
            json_response(self, 200, data=result.data)

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
            ("ai_assist", "api_key"),
            ("ai_search", "api_key"),
        ]

        for field_path in sensitive_fields:
            current_value = self._get_nested_value(filtered, field_path)
            if current_value and self._is_masked_value(str(current_value)):
                self._delete_nested_path(filtered, field_path)

        if "hooks" in filtered:
            del filtered["hooks"]

        return filtered

    def _get_nested_value(self, obj: dict, path: tuple):
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
