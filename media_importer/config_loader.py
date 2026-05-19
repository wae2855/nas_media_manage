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

    dimensions = config.get("dimensions", [])
    for dim in dimensions:
        if not dim.get("name"):
            errors.append("dimension 缺少 name 字段")
        if not dim.get("values") or not isinstance(dim["values"], list):
            errors.append(f"dimension '{dim.get('name')}' 缺少有效的 values 列表")

    return errors


def mask_sensitive(config: dict) -> dict:
    masked = deepcopy(config)

    if masked.get("llm", {}).get("api_key"):
        api_key = masked["llm"]["api_key"]
        if len(api_key) > 8:
            masked["llm"]["api_key"] = api_key[:4] + "***" + api_key[-4:]
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
            if valid_values and value not in valid_values:
                errors.append(
                    f"dimension '{dim_name}' 的值 '{value}' 不在允许范围内: {valid_values}"
                )

    return errors


def load_config(config_path: str = None) -> dict:
    if config_path is None:
        script_dir = os.path.dirname(__file__)
        project_root = os.path.dirname(script_dir)
        config_path = os.path.join(project_root, "config", "config.yaml")

    if not os.path.exists(config_path):
        print(f"配置文件不存在，正在从模板复制: {config_path}")
        copy_config_template(config_path)
        print("配置文件已生成，请编辑后重新启动程序")
        sys.exit(1)

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
    if persistence_path and not os.path.isabs(persistence_path):
        task_queue["persistence_path"] = os.path.join(project_root, "data", persistence_path)

    errors = validate_config(config)
    if errors:
        print("配置校验失败:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1002)

    return config
