import os

from media_importer.features.configuration import load_config, mask_sensitive
from media_importer.api import globals
from media_importer.features.configuration import validate_config
from media_importer.notify.hermes_hook import HermesNotifier
from media_importer.monitor.file_watcher import FileWatcher
from media_importer.core.db import list_tasks as db_list
from .config_save import save_config
from .utils import json_response


class ConfigHandlersMixin:
    def _config(self):
        masked = mask_sensitive(globals._config) if globals._config else {}
        sp = masked.get("source_policy", {})
        if "cleanup_mode" not in sp:
            cleanup_after_done = sp.get("cleanup_source_after_done")
            if cleanup_after_done is False:
                sp["cleanup_mode"] = "read_only"
            elif cleanup_after_done is True:
                sp["cleanup_mode"] = "full_cleanup"
        if "delete_source_after_import" not in sp:
            sp["delete_source_after_import"] = sp.get("cleanup_source_after_done", True)
        prompts_data = self._load_prompts_for_ui()
        json_response(self, 200, data={"config": masked, "prompts": prompts_data})

    def _config_save(self, body: dict):
        save_config(self, body, globals_module=globals, respond=json_response)

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
            "metadata.providers": ["metadata"],
            "llm": ["llm"],
            "server": ["server"],
            "hermes": ["hermes"],
            "file_watcher": ["file_watcher"],
            "advanced": ["log_dir", "task_queue", "video_extensions", "subtitle_extensions"],
            "confidence": ["confidence"],
            "source_cleaner": ["source_cleaner"],
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

            if section == "metadata.providers":
                self._merge_provider_sensitive_fields(section_body)

            self._config_save(section_body)
        except Exception as e:
            json_response(self, 500, message=f"保存区块配置失败: {str(e)}")

    def _merge_provider_sensitive_fields(self, section_body: dict):
        new_providers = []
        if isinstance(section_body.get("metadata"), dict):
            new_providers = section_body["metadata"].get("providers", [])
        if not new_providers:
            return
        existing_providers = globals._config.get("metadata", {}).get("providers", []) if globals._config else []
        legacy_configs = {}
        metadata = globals._config.get("metadata", {}) if globals._config else {}
        for ptype in set(p.get("type", "") for p in new_providers):
            legacy = metadata.get(ptype, {})
            if isinstance(legacy, dict) and legacy.get("api_key"):
                legacy_configs[ptype] = legacy
        for new_p in new_providers:
            ptype = new_p.get("type", "")
            existing_p = None
            for ep in existing_providers:
                if ep.get("type") == ptype:
                    existing_p = ep
                    break
            if not new_p.get("api_key") or new_p.get("api_key") == "***":
                if existing_p and existing_p.get("api_key") and existing_p.get("api_key") != "***":
                    new_p["api_key"] = existing_p["api_key"]
                elif ptype in legacy_configs and legacy_configs[ptype].get("api_key"):
                    new_p["api_key"] = legacy_configs[ptype]["api_key"]

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
            cfg_to_check = body if body else (globals._config or {})
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
            from media_importer.monitor.permission_checker import check_path_permission, get_current_user
            result = check_path_permission(path, need_write=need_write)
            result["user"] = get_current_user()
            json_response(self, 200, data=result, message=result["message"])
        except Exception as e:
            json_response(self, 500, message=f"路径测试异常: {e}")

    def _watcher_status(self):
        if not globals._global_watcher:
            json_response(self, 200, data={"enabled": False, "status": "not_started"})
            return
        json_response(self, 200, data={
            "enabled": globals._global_watcher.is_running(),
            "poll_interval": globals._global_watcher.poll_interval,
            "status": "running" if globals._global_watcher.is_running() else "stopped"
        })

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
