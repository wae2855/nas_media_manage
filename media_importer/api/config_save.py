import logging
import os
import tempfile
import traceback

from media_importer.api import globals

from .utils import json_response


def save_config(handler, body: dict, globals_module=None, respond=None):
    state = globals_module or globals
    write_response = respond or json_response

    if not body:
        write_response(handler, 400, message="Empty config")
        return

    try:
        from media_importer.features.configuration import (
            config_revision,
            inspect_storage_readiness,
            validate_config,
        )
        from media_importer.features.configuration.library_paths import (
            LibraryPathError,
            canonicalize_library_config,
        )

        requested_revision = body.get("_revision")
        if requested_revision and requested_revision != config_revision(state._config or {}):
            write_response(handler, 409, message="配置已被其他页面更新，请刷新后重试")
            return
        body = {key: value for key, value in body.items() if key != "_revision"}

        config_path = state._config.get("_config_path") if state._config else None
        if not config_path:
            write_response(handler, 500, message="Config path not found")
            return

        from ruamel.yaml import YAML
        from ruamel.yaml.comments import CommentedMap
        from ruamel.yaml.scalarstring import DoubleQuotedScalarString, SingleQuotedScalarString

        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.width = 120

        with open(config_path, "r", encoding="utf-8") as f:
            config_doc = yaml.load(f)

        config_to_save = handler._filter_sensitive_fields(body, config_doc)

        yaml_reserved_words = {"true", "false", "yes", "no", "on", "off", "null", "~"}
        yaml_special_chars = set("{}:#&*!|>'\"'")

        def _needs_quote(value):
            if not isinstance(value, str):
                return False
            if value.lower() in yaml_reserved_words:
                return True
            if any(c in value for c in yaml_special_chars):
                return True
            if " " in value:
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

        try:
            canonical = canonicalize_library_config(dict(config_doc))
        except LibraryPathError as exc:
            write_response(handler, 400, message=f"配置未保存：{exc}")
            return
        for key in ("library_root", "path_rules", "fallback_dir"):
            if key in canonical:
                update_nested(config_doc, {key: canonical[key]})

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

        validation = validate_config(dict(config_doc), test_llm=False)
        if validation.get("overall") != "ok":
            errors = [
                detail.get("message", "配置无效")
                for detail in validation.get("details", [])
                if detail.get("status") == "error"
            ]
            write_response(handler, 400, message="配置未保存：" + "；".join(errors[:4]))
            return
        if (config_doc.get("file_watcher") or {}).get("enabled") is True:
            readiness = inspect_storage_readiness(dict(config_doc))
            if not readiness["automatic_allowed"]:
                write_response(
                    handler,
                    400,
                    message="自动运行未启用：请先让所有存储检查项达到绿色",
                )
                return

        config_dir = os.path.dirname(config_path) or "."
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=config_dir,
                prefix=".config-",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = temp_file.name
                yaml.dump(config_doc, temp_file)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_path, config_path)
            temp_path = ""
            try:
                dir_fd = os.open(config_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

        has_running_tasks = state._global_task_manager and state._global_task_manager.has_running_tasks()

        safe_sections = {"source_cleaner", "advanced"}
        body_sections = set(body.keys())
        is_safe_update = body_sections.issubset(safe_sections)

        if has_running_tasks and not is_safe_update:
            state._config_dirty = True
            write_response(
                handler,
                200,
                message="配置已保存到文件。当前有任务正在执行，任务完成后自动同步内存配置，或点击「重载配置」立即生效（可能影响正在执行的任务）",
            )
        else:
            if isinstance(state._config, dict):
                handler._update_config_safely(state._config, body)
            if "file_watcher" in body:
                try:
                    handler._reload_watcher()
                    write_response(handler, 200, message="轮询监控配置已保存并立即生效")
                    return
                except Exception as e:
                    (state._global_logger or logging.getLogger(__name__)).error(f"文件监控配置更新后重启失败: {e}")

            write_response(handler, 200, message="配置已保存并生效")
    except Exception as e:
        error_msg = f"保存配置失败: {e}\n{traceback.format_exc()}"
        write_response(handler, 500, message=error_msg)
