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

    if trim_pkgvar:
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

    config.setdefault("fallback_dir", "")

    errors = validate_config(config)
    if errors:
        print("配置校验警告（服务仍可启动，请通过前台完善配置）:")
        for error in errors:
            print(f"  - {error}")

    config["_config_path"] = os.path.abspath(config_path)

    _normalize_bool_strings(config)

    return config


def _migrate_confidence_v1_to_v2(confidence):
    changed = False
    v1_keys = [
        "aggregation_method", "tmdb_dim_confidence", "file_dim_confidence",
        "dim_missing_confidence",
    ]
    for key in v1_keys:
        if key in confidence:
            del confidence[key]
            changed = True

    default_sp = confidence.get("source_priority", ["tmdb", "ai", "file"])
    dims = confidence.get("dimensions", {})
    for dim_name, dim_cfg in list(dims.items()):
        if not isinstance(dim_cfg, dict):
            continue
        v1_dim_keys = ["weight", "veto_threshold", "source_confidence",
                        "tmdb_confidence", "ai_confidence", "file_confidence",
                        "missing_confidence"]
        has_v1 = False
        for k in v1_dim_keys:
            if k in dim_cfg:
                has_v1 = True
                del dim_cfg[k]
        if has_v1 or "trusted_sources" in dim_cfg:
            changed = True

        if "sources" not in dim_cfg:
            legacy_trusted = dim_cfg.pop("trusted_sources", None)
            if legacy_trusted is not None:
                dim_cfg["sources"] = [
                    {"source": s, "trusted": s in legacy_trusted}
                    for s in default_sp
                ]
            else:
                dim_cfg["sources"] = [
                    {"source": s, "trusted": True}
                    for s in default_sp
                ]
        else:
            if "trusted_sources" in dim_cfg:
                del dim_cfg["trusted_sources"]

    if changed:
        print("已自动迁移置信度配置 v1 → v2（移除聚合方法/维度权重，新增按维度来源信任配置）")


BOOL_TRUE_STRINGS = {'true', 'yes', 'on'}
BOOL_FALSE_STRINGS = {'false', 'no', 'off'}
BOOL_KEYS = {
    'enabled', 'verify_ssl', 'delete_after_process', 'recursive',
    'create_series_folder', 'organize_by_season', 'create_year_folder',
    'auto_delete_success', 'scan_source', 'cleanup_source_after_done',
    'ai_enabled', 'cleanup_empty_dirs', 'confirm_before_cleanup',
}


def _migrate_source_policy(source_policy: dict, config: dict):
    cleanup_mode = source_policy.get("cleanup_mode", "")
    delete_after = source_policy.get("delete_source_after_import", None)

    if "cleanup_source_after_done" not in source_policy:
        if cleanup_mode == "read_only":
            source_policy["cleanup_source_after_done"] = False
        elif cleanup_mode == "full_cleanup":
            source_policy["cleanup_source_after_done"] = delete_after if delete_after is not None else True
        elif cleanup_mode == "smart_cleanup":
            source_policy["cleanup_source_after_done"] = delete_after if delete_after is not None else True
            if "source_cleaner" not in config:
                config["source_cleaner"] = {}
            config["source_cleaner"]["enabled"] = True
        else:
            source_policy["cleanup_source_after_done"] = delete_after if delete_after is not None else True

    smart_cleanup = source_policy.pop("smart_cleanup", None)
    if smart_cleanup and "source_cleaner" not in config:
        config["source_cleaner"] = {}
    if smart_cleanup:
        cleaner = config.get("source_cleaner", {})
        cleaner.setdefault("ai_enabled", smart_cleanup.get("ai_enabled", True))
        cleaner.setdefault("protect_extensions", smart_cleanup.get("protect_extensions", []))
        cleaner.setdefault("blacklist_patterns", smart_cleanup.get("blacklist_patterns", []))
        cleaner.setdefault("cleanup_empty_dirs", smart_cleanup.get("cleanup_empty_dirs", True))
        cleaner.setdefault("confirm_before_cleanup", smart_cleanup.get("confirm_before_cleanup", True))

    if "source_cleaner" in config:
        cleaner = config["source_cleaner"]
        old_mode = cleaner.get("cleanup_mode", "")
        if old_mode == "keep_media_only":
            cleaner["cleanup_mode"] = "media_only"
        elif old_mode == "keep_media_related":
            cleaner["cleanup_mode"] = "media_and_related"


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
