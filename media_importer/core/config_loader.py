#!/usr/bin/env python3
import os
import yaml
import sys
import shutil
from copy import deepcopy

from .config_migrations import (
    _migrate_confidence_v1_to_v2,
    _migrate_confidence_v2_to_v3,
    _migrate_source_policy,
    _migrate_mcp_to_web_search,
    _normalize_bool_strings,
    BOOL_TRUE_STRINGS,
    BOOL_FALSE_STRINGS,
)


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
            errors.append(f"{dir_key} 不存在: {dir_path}")

    quarantine_dir = config.get("source_policy", {}).get("quarantine_dir", "")
    recycle_dir = config.get("source_policy", {}).get("recycle_dir", "")
    if not recycle_dir and quarantine_dir:
        recycle_dir = quarantine_dir
        config["source_policy"]["recycle_dir"] = quarantine_dir
    if not recycle_dir:
        errors.append("source_policy.recycle_dir 未配置")
    elif not os.path.isdir(recycle_dir):
        errors.append(f"source_policy.recycle_dir 不存在: {recycle_dir}")

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

    for provider in masked.get("metadata", {}).get("providers", []):
        if provider.get("api_key"):
            provider["api_key"] = "***"

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
    if "persistence_path" in task_queue:
        del task_queue["persistence_path"]

    if "source_file_handling" in config:
        del config["source_file_handling"]

    if "source_dedup" in config:
        old = config.pop("source_dedup")
        if "source_policy" not in config:
            config["source_policy"] = {}
        config["source_policy"].setdefault("recycle_dir", old.get("recycle_dir", "") or old.get("quarantine_dir", ""))

    if "source_dir_scan" in config:
        scan = config.pop("source_dir_scan")
        if "source_policy" not in config:
            config["source_policy"] = {}
        config["source_policy"].setdefault("scan_recursive", scan.get("recursive", True))
        config["source_policy"].setdefault("scan_max_depth", scan.get("max_depth", 5))

    if "source_policy" not in config:
        config["source_policy"] = {}
    source_policy = config["source_policy"]

    _migrate_source_policy(source_policy, config)

    source_policy.setdefault("cleanup_source_after_done", True)
    source_policy.setdefault("recycle_retention_days", 30)

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
    source_cleaner.setdefault("schedule", "0 3 * * *")

    env_data_dir = os.environ.get("NAS_MEDIA_IMPORTER_DATA_DIR")
    if env_data_dir:
        data_dir = env_data_dir
    elif trim_pkgvar:
        data_dir = os.path.join(trim_pkgvar, "data")
    else:
        data_dir = os.path.join(project_root, "data")
    config["_data_dir"] = data_dir

    source_policy.setdefault("scan_recursive", True)
    source_policy.setdefault("scan_max_depth", 5)

    quarantine_dir = source_policy.get("quarantine_dir", "")
    recycle_dir = source_policy.get("recycle_dir", "") or quarantine_dir
    if recycle_dir and not os.path.isabs(recycle_dir):
        source_policy["recycle_dir"] = os.path.join(project_root, recycle_dir)
    if quarantine_dir and "recycle_dir" not in source_policy:
        source_policy["recycle_dir"] = quarantine_dir

    if "metadata" not in config:
        config["metadata"] = {}
    if "providers" not in config["metadata"]:
        config["metadata"]["providers"] = [
            {"type": "tmdb", "enabled": True, "language": "zh-CN", "fallback_language": "en-US"}
        ]

    if "manual_review" not in config:
        config["manual_review"] = {"enabled": False}

    if "confidence" not in config:
        config["confidence"] = {}
    confidence = config["confidence"]
    confidence.setdefault("provider_match_threshold", 0.7)
    confidence.setdefault("title_exact_with_year", 1.0)
    confidence.setdefault("title_exact_with_season", 0.9)
    confidence.setdefault("title_exact_no_year", 0.7)
    confidence.setdefault("title_exact_year_mismatch", 0.4)
    confidence.setdefault("title_fuzzy_year_coeff", 0.7)
    confidence.setdefault("title_min_similarity", 0.3)
    confidence.setdefault("ai_cap_high_similarity", 0.7)
    confidence.setdefault("ai_cap_low_similarity", 0.3)
    confidence.setdefault("ai_cap_no_title", 0.3)
    confidence.setdefault("ai_cap_no_match", 0.2)
    confidence.setdefault("ai_cap_low_coeff", 0.5)
    confidence.setdefault("pass_threshold", 0.8)
    confidence.setdefault("confirm_threshold", 0.5)
    confidence.setdefault("review_threshold", 0.3)
    confidence.setdefault("R_formula", "log")
    confidence.setdefault("R_max_results_cap", 10)
    confidence.setdefault("R_min_value", 0.1)
    confidence.setdefault("R_T_floor", 0.5)
    confidence.setdefault("R_T_curve", 1.5)
    confidence.setdefault("source_priority", ["tmdb", "ai", "file"])
    confidence.setdefault("dimensions", {})

    _migrate_confidence_v1_to_v2(confidence)
    _migrate_confidence_v2_to_v3(config)

    config.setdefault("fallback_dir", "")

    errors = validate_config(config)
    if errors:
        print("配置校验警告（服务仍可启动，请通过前台完善配置）:")
        for error in errors:
            print(f"  - {error}")

    config["_config_path"] = os.path.abspath(config_path)

    _migrate_mcp_to_web_search(config)
    _normalize_bool_strings(config)

    return config
