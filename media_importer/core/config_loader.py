#!/usr/bin/env python3
import os
import shutil
import sys
from copy import deepcopy
from typing import Optional

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

BOOL_TRUE_STRINGS = {'true', 'yes', 'on'}
BOOL_FALSE_STRINGS = {'false', 'no', 'off'}


def copy_config_template(target_path: str):
    script_dir = os.path.dirname(__file__)
    project_root = os.path.dirname(script_dir)
    template_path = os.path.join(project_root, "config.yaml.example")

    if not os.path.exists(template_path):
        print(f"错误: 配置模板文件不存在: {template_path}")
        sys.exit(1)

    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    shutil.copy2(template_path, target_path)


# ADR-0010 退役的配置块：视图层剥离（mask_sensitive），不参与校验与前端展示
RETIRED_CONFIG_SECTIONS = ("ai_assist", "ai_search", "ai_scene_strategy", "confidence")


def validate_config(config: dict) -> list:
    errors = []

    # LLM 配置完整性（ADR-0010：LLM 仅服务源目录清理器）
    llm_cfg = config.get("llm", {})
    if llm_cfg.get("api_key") and llm_cfg["api_key"] != "your-api-key-here":
        if not llm_cfg.get("base_url"):
            errors.append("llm 已配置 API Key，但缺少模型地址（base_url）")
        if not llm_cfg.get("model"):
            errors.append("llm 已配置 API Key，但缺少模型ID（model）")

    for dir_key in ["source_dir", "temp_dir", "log_dir"]:
        dir_path = config.get(dir_key, "")
        if not dir_path:
            errors.append(f"{dir_key} 未配置")
        elif not os.path.isdir(dir_path):
            errors.append(f"{dir_key} 不存在: {dir_path}")

    recycle_dir = config.get("source_policy", {}).get("recycle_dir", "")
    if not recycle_dir:
        errors.append("source_policy.recycle_dir 未配置")
    elif not os.path.isdir(recycle_dir):
        errors.append(f"source_policy.recycle_dir 不存在: {recycle_dir}")

    return errors


def mask_sensitive(config: dict) -> dict:
    masked = deepcopy(config)

    if masked.get("server", {}).get("api_key"):
        masked["server"]["api_key"] = "***"

    llm_cfg = masked.get("llm")
    if isinstance(llm_cfg, dict):
        for key in list(llm_cfg.keys()):
            # 脱敏 llm 块内全部密钥字段（兼容历史 fast_api_key 等字段名）
            if "api_key" in key and isinstance(llm_cfg[key], str) and llm_cfg[key]:
                api_key = llm_cfg[key]
                prefix_end = 0
                for i, c in enumerate(api_key):
                    if c == '-':
                        prefix_end = i + 1
                        break
                llm_cfg[key] = (api_key[:prefix_end] + "***") if prefix_end > 0 else "***"

    for provider in masked.get("metadata", {}).get("providers", []):
        if provider.get("api_key"):
            provider["api_key"] = "***"

    # ADR-0010 退役配置块不出现在前端载荷（底层 config 不动，仅视图剥离）
    for retired in RETIRED_CONFIG_SECTIONS:
        masked.pop(retired, None)

    return masked


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


def load_config(config_path: Optional[str] = None) -> dict:
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
            config = YAML(typ="safe").load(f)
    except YAMLError as e:
        print(f"配置文件 YAML 格式错误: {e}")
        sys.exit(1001)

    config_dir = os.path.dirname(os.path.abspath(config_path))
    project_root = os.path.dirname(config_dir)

    for key in ["source_dir", "temp_dir", "log_dir"]:
        path_val = config.get(key, "")
        if path_val and not os.path.isabs(path_val):
            config[key] = os.path.join(project_root, path_val)

    if "source_policy" not in config:
        config["source_policy"] = {}
    source_policy = config["source_policy"]
    source_policy.setdefault("cleanup_source_after_done", False)
    source_policy.setdefault(
        "mode",
        "recycle_source_unit" if source_policy.get("cleanup_source_after_done") is True
        else "preserve_media" if (config.get("source_cleaner") or {}).get("enabled") is True
        else "preserve_all",
    )
    source_policy.setdefault("recycle_retention_days", 30)
    source_policy.setdefault("scan_recursive", True)
    source_policy.setdefault("scan_max_depth", 5)
    source_policy.setdefault("unit_settle_seconds", 120)
    source_policy.setdefault(
        "unit_incomplete_patterns",
        ["*.part", "*.partial", "*.aria2", "*.!qB", "*.crdownload"],
    )

    recycle_dir = source_policy.get("recycle_dir", "")
    if recycle_dir and not os.path.isabs(recycle_dir):
        source_policy["recycle_dir"] = os.path.join(project_root, recycle_dir)

    if "source_cleaner" not in config:
        config["source_cleaner"] = {}
    source_cleaner = config["source_cleaner"]
    source_cleaner.setdefault("enabled", False)
    source_cleaner.setdefault("cleanup_mode", "media_only")
    source_cleaner.setdefault("ai_enabled", False)
    source_cleaner.setdefault("merge_strategy", "intersection")
    source_cleaner.setdefault("junk_video_max_size_mb", 50)
    source_cleaner.setdefault("delete_extensions", [".url", ".log", ".txt"])
    source_cleaner.setdefault("protect_extensions", [".nfo", ".jpg", ".png"])
    source_cleaner.setdefault("blacklist_patterns", ["RARBG*", "*/Sample/*", "*/sample/*"])
    source_cleaner.setdefault("cleanup_empty_dirs", True)

    env_data_dir = os.environ.get("NAS_MEDIA_IMPORTER_DATA_DIR")
    if env_data_dir:
        data_dir = env_data_dir
    elif trim_pkgvar:
        data_dir = os.path.join(trim_pkgvar, "data")
    else:
        data_dir = os.path.join(project_root, "data")
    config["_data_dir"] = data_dir

    if "metadata" not in config:
        config["metadata"] = {}
    if "providers" not in config["metadata"]:
        config["metadata"]["providers"] = [
            {"type": "tmdb", "enabled": True, "language": "zh-CN", "fallback_language": "en-US"}
        ]

    if "manual_review" not in config:
        config["manual_review"] = {"enabled": False}

    config.setdefault("fallback_dir", "")

    # 旧版绝对路径规则只在能证明同属一个片库根目录时自动归一化。
    try:
        from media_importer.features.configuration.library_paths import canonicalize_library_config
        config = canonicalize_library_config(config)
    except ValueError as exc:
        config["_library_migration_error"] = str(exc)

    errors = validate_config(config)
    if errors:
        print("配置校验警告（服务仍可启动，请通过前台完善配置）:")
        for error in errors:
            print(f"  - {error}")

    config["_config_path"] = os.path.abspath(config_path)

    return config
