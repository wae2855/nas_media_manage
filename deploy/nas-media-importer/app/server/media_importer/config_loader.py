#!/usr/bin/env python3
import os
import yaml
import sys
import shutil
from copy import deepcopy


def copy_config_template(target_path: str):
    script_dir = os.path.dirname(__file__)
    project_root = os.path.dirname(script_dir)
    template_path = os.path.join(project_root, "config.yaml.example")

    if not os.path.exists(template_path):
        print(f"错误: 配置模板文件不存在: {template_path}")
        sys.exit(1)

    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    shutil.copy2(template_path, target_path)


def validate_config(config: dict) -> list:
    errors = []

    if not config.get("llm", {}).get("api_key") or config["llm"]["api_key"] == "your-api-key-here":
        errors.append("缺少有效的 llm.api_key 配置")

    for dir_key in ["source_dir", "temp_dir", "log_dir"]:
        dir_path = config.get(dir_key, "")
        if not dir_path:
            errors.append(f"{dir_key} 未配置")
        elif not os.path.isdir(dir_path):
            try:
                os.makedirs(dir_path, exist_ok=True)
            except OSError:
                errors.append(f"{dir_key} 不存在且无法创建: {dir_path}")

    # 固定维度白名单校验
    dimensions = config.get("dimensions", [])
    EXPECTED_DIMENSION_NAMES = {'media_type', 'documentary', 'animation', 'restricted_level'}
    actual_names = {dim.get('name') for dim in dimensions if dim.get('name')}
    if actual_names != EXPECTED_DIMENSION_NAMES:
        errors.append(f"dimensions 名称必须为 {EXPECTED_DIMENSION_NAMES}，实际为 {actual_names}")

    for dim in dimensions:
        if not dim.get("name"):
            errors.append("dimension 缺少 name 字段")
        if not dim.get("values") or not isinstance(dim["values"], list):
            errors.append(f"dimension '{dim.get('name')}' 缺少有效的 values 列表")

    return errors


def mask_sensitive(config: dict) -> dict:
    masked = deepcopy(config)

    if masked.get("server", {}).get("api_key"):
        masked["server"]["api_key"] = "***"

    if masked.get("llm", {}).get("api_key"):
        api_key = masked["llm"]["api_key"]
        if api_key:
            prefix_end = 0
            for i, c in enumerate(api_key):
                if c == '-':
                    prefix_end = i + 1
                    break
            if prefix_end > 0:
                masked["llm"]["api_key"] = api_key[:prefix_end] + "***"
            else:
                masked["llm"]["api_key"] = "***"

    if masked.get("hermes", {}).get("webhook", {}).get("secret"):
        masked["hermes"]["webhook"]["secret"] = "***"

    return masked


def validate_dimension_values(dimensions: list, ai_response: dict) -> list:
    errors = []

    if "dimensions" not in ai_response:
        return errors

    for dim in dimensions:
        dim_name = dim["name"]
        if dim_name in ai_response["dimensions"]:
            value = ai_response["dimensions"][dim_name]
            valid_values = dim.get("values", [])
            if valid_values and not _value_in_list(value, valid_values):
                errors.append(
                    f"dimension '{dim_name}' 的值 '{value}' 不在允许范围内: {valid_values}"
                )

    return errors


def _value_in_list(value, valid_values):
    if value in valid_values:
        return True
    if isinstance(value, bool):
        str_val = 'true' if value else 'false'
        return str_val in valid_values or ('yes' if value else 'no') in valid_values
    if isinstance(value, str):
        if value.lower() in BOOL_TRUE_STRINGS:
            return True in valid_values or 'yes' in valid_values
        if value.lower() in BOOL_FALSE_STRINGS:
            return False in valid_values or 'no' in valid_values
    return False


def load_config(config_path: str = None) -> dict:
    trim_pkgvar = os.environ.get("TRIM_PKGVAR", "")

    if config_path is None:
        if trim_pkgvar:
            config_path = os.path.join(trim_pkgvar, "config", "config.yaml")
        else:
            script_dir = os.path.dirname(__file__)
            project_root = os.path.dirname(script_dir)
            config_path = os.path.join(project_root, "config", "config.yaml")

    if not os.path.exists(config_path):
        print(f"配置文件不存在，正在从模板复制: {config_path}")
        copy_config_template(config_path)
        print("配置文件已生成，请通过前台界面完善配置")

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"配置文件 YAML 格式错误: {e}")
        sys.exit(1001)

    config_dir = os.path.dirname(os.path.abspath(config_path))
    project_root = os.path.dirname(config_dir)

    for key in ["source_dir", "temp_dir", "log_dir"]:
        path_val = config.get(key, "")
        if path_val and not os.path.isabs(path_val):
            config[key] = os.path.join(project_root, path_val)

    task_queue = config.get("task_queue", {})
    persistence_path = task_queue.get("persistence_path", "")
    if not persistence_path:
        if trim_pkgvar:
            task_queue["persistence_path"] = os.path.join(trim_pkgvar, "data", "tasks.json")
        else:
            task_queue["persistence_path"] = os.path.join(project_root, "data", "tasks.json")
    elif not os.path.isabs(persistence_path):
        task_queue["persistence_path"] = os.path.join(project_root, "data", persistence_path)

    errors = validate_config(config)
    if errors:
        print("配置校验警告（服务仍可启动，请通过前台完善配置）:")
        for error in errors:
            print(f"  - {error}")

    config["_config_path"] = os.path.abspath(config_path)

    _normalize_bool_strings(config)

    return config


BOOL_TRUE_STRINGS = {'true', 'yes', 'on'}
BOOL_FALSE_STRINGS = {'false', 'no', 'off'}
BOOL_KEYS = {
    'enabled', 'verify_ssl', 'delete_after_process', 'recursive',
    'create_series_folder', 'organize_by_season', 'create_year_folder',
    'auto_delete_success',
}


def _normalize_bool_strings(obj):
    if isinstance(obj, dict):
        for key in list(obj.keys()):
            value = obj[key]
            if isinstance(value, str) and key in BOOL_KEYS:
                if value.lower() in BOOL_TRUE_STRINGS:
                    obj[key] = True
                elif value.lower() in BOOL_FALSE_STRINGS:
                    obj[key] = False
            elif isinstance(value, dict):
                _normalize_bool_strings(value)
            elif isinstance(value, list):
                _normalize_bool_strings_in_list(value)
    return obj


def _normalize_bool_strings_in_list(lst):
    for i in range(len(lst)):
        item = lst[i]
        if isinstance(item, dict):
            _normalize_bool_strings(item)
        elif isinstance(item, list):
            _normalize_bool_strings_in_list(item)
