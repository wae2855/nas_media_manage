#!/usr/bin/env python3
"""
配置检测模块
用于检测各项配置项的有效性，包括路径存在性、API连通性等
"""
import os
import time
import requests
import hashlib
import hmac
import json
from typing import Dict, Any, List, Tuple


def check_path(path: str, require_write: bool = False) -> Tuple[bool, str]:
    if not path:
        return False, "路径未配置"
    
    if not os.path.exists(path):
        return False, f"路径不存在: {path}"
    
    if not os.path.isdir(path):
        return False, f"路径不是目录: {path}"
    
    if require_write:
        test_file = os.path.join(path, f".test_write_{int(time.time())}")
        try:
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            return True, f"路径存在且可写: {path}"
        except Exception as e:
            return False, f"路径不可写: {path}, 错误: {str(e)}"
    
    return True, f"路径存在: {path}"


def test_llm_api(base_url: str, api_key: str, model: str, timeout: int = 10) -> Tuple[bool, str]:
    """
    测试LLM API连通性
    
    Args:
        base_url: API基础地址
        api_key: API密钥
        model: 模型名称
        timeout: 超时时间（秒）
    
    Returns:
        (是否通过, 详细信息)
    """
    if not api_key or api_key == "your-api-key-here":
        return False, "API密钥未配置或无效"
    
    if not base_url:
        return False, "API地址未配置"
    
    try:
        test_url = base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "test"}],
            "max_tokens": 5
        }
        
        response = requests.post(test_url, json=payload, headers=headers, timeout=timeout)
        
        if response.status_code == 200:
            return True, f"LLM API连通正常 (状态码: 200)"
        elif response.status_code == 401:
            return False, f"LLM API认证失败 (状态码: 401, 请检查API密钥)"
        elif response.status_code == 404:
            return False, f"LLM API端点不存在 (状态码: 404, 请检查base_url: {base_url})"
        else:
            return False, f"LLM API返回错误 (状态码: {response.status_code}, 响应: {response.text[:100]})"
    
    except requests.exceptions.Timeout:
        return False, f"LLM API连接超时 ({timeout}秒)"
    except requests.exceptions.ConnectionError:
        return False, f"LLM API连接失败 (无法连接到: {base_url})"
    except Exception as e:
        return False, f"LLM API测试异常: {str(e)}"


def test_hermes_webhook(base_url: str, route_name: str, secret: str, timeout: int = 10) -> Tuple[bool, str]:
    if not base_url:
        return True, "Hermes未启用或地址未配置（可选）"

    if not route_name:
        return False, "Webhook路由名称未配置"

    try:
        webhook_url = base_url.rstrip("/") + "/webhooks/" + route_name.lstrip("/")

        test_message = {
            "event_type": "test_notification",
            "event_type_display": "🔧 配置验证测试",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "video_file": "",
            "status": "TEST",
            "extra_info": "这是一条来自影音库AI智能整理的测试消息，验证Hermes Webhook连通性",
            "task": {},
            "test": True,
            "source": "config_validation"
        }

        headers = {
            "Content-Type": "application/json"
        }

        payload_bytes = json.dumps(test_message, ensure_ascii=False).encode("utf-8")

        if secret:
            signature = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
            headers["X-Webhook-Signature"] = signature

        response = requests.post(webhook_url, data=payload_bytes, headers=headers, timeout=timeout)

        if response.status_code == 200:
            try:
                result = response.json()
                if result.get("success") or result.get("code") == 200:
                    return True, f"Hermes Webhook测试成功: {webhook_url}"
                elif result.get("status") in ("delivered", "ok", "accepted"):
                    target = result.get("target", "")
                    route = result.get("route", route_name)
                    return True, f"Hermes通知已投递 (路由: {route}, 目标: {target})"
                else:
                    return False, f"Hermes返回失败: {response.text[:100]}"
            except Exception:
                return True, f"Hermes Webhook响应成功 (状态码: 200)"
        elif response.status_code == 401:
            return False, f"Hermes认证失败 (状态码: 401, 请检查secret)"
        elif response.status_code == 404:
            return False, f"Hermes路由不存在: {route_name} (URL: {webhook_url})"
        else:
            return False, f"Hermes返回错误 (状态码: {response.status_code}, 响应: {response.text[:100]})"

    except requests.exceptions.Timeout:
        return False, f"Hermes连接超时 ({timeout}秒)"
    except requests.exceptions.ConnectionError:
        return False, f"Hermes连接失败 (无法连接到: {base_url})"
    except Exception as e:
        return False, f"Hermes测试异常: {str(e)}"


def validate_config(config: Dict[str, Any], test_llm: bool = False, test_hermes: bool = False) -> Dict[str, Any]:
    """
    验证配置 - 基础有效性检查
    
    Args:
        config: 配置字典
        test_llm: 是否测试LLM API（默认不测试，由独立按钮触发）
        test_hermes: 是否测试Hermes Webhook（默认不测试，由独立按钮触发）
    
    Returns:
        验证结果字典
    """
    results = {
        "overall": "ok",
        "details": [],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
    }
    
    def add_check(item, status, message):
        results["details"].append({"item": item, "status": status, "message": message})
        if status == "error":
            results["overall"] = "degraded"
    
    source_dir = config.get("source_dir", "")
    if not source_dir:
        add_check("source_dir", "error", "源目录未配置")
    else:
        ok, msg = check_path(source_dir, require_write=False)
        add_check("source_dir", "ok" if ok else "error", msg)
    
    temp_dir = config.get("temp_dir", "")
    if not temp_dir:
        add_check("temp_dir", "error", "中转目录未配置")
    else:
        ok, msg = check_path(temp_dir, require_write=True)
        add_check("temp_dir", "ok" if ok else "error", msg)

    source_policy = config.get("source_policy", {})
    quarantine_dir = source_policy.get("quarantine_dir", "")
    recycle_dir = source_policy.get("recycle_dir", "") or quarantine_dir
    if not recycle_dir:
        add_check("recycle_dir", "error", "回收站目录未配置")
    else:
        ok, msg = check_path(recycle_dir, require_write=True)
        add_check("recycle_dir", "ok" if ok else "error", msg)

    norm_source = source_dir.rstrip("/") if source_dir else ""
    norm_temp = temp_dir.rstrip("/") if temp_dir else ""
    norm_recycle = recycle_dir.rstrip("/") if recycle_dir else ""

    if source_policy.get("cleanup_mode") is not None:
        add_check("source_policy.cleanup_mode", "warning", "cleanup_mode 已废弃，请使用 cleanup_source_after_done 替代")
    if source_policy.get("delete_source_after_import") is not None:
        add_check("source_policy.delete_source_after_import", "warning", "delete_source_after_import 已废弃，请使用 cleanup_source_after_done 替代")

    cleanup_after_done = source_policy.get("cleanup_source_after_done")
    if cleanup_after_done is not None and not isinstance(cleanup_after_done, bool):
        add_check("source_policy.cleanup_source_after_done", "error", "cleanup_source_after_done 必须为布尔值，当前: " + str(cleanup_after_done))
    elif cleanup_after_done is True:
        add_check("source_policy.cleanup_source_after_done", "ok", "入库后自动清理源文件: 已启用")
    elif cleanup_after_done is False:
        add_check("source_policy.cleanup_source_after_done", "ok", "入库后保留源文件: 只读模式")

    retention_days = source_policy.get("recycle_retention_days")
    if retention_days is not None:
        if not isinstance(retention_days, int) or retention_days < 0:
            add_check("source_policy.recycle_retention_days", "error", "recycle_retention_days 必须为非负整数，当前: " + str(retention_days))
        else:
            add_check("source_policy.recycle_retention_days", "ok", "回收站保留天数: " + str(retention_days))

    source_cleaner = config.get("source_cleaner", {})
    if source_cleaner:
        sc_enabled = source_cleaner.get("enabled")
        if sc_enabled is not None and not isinstance(sc_enabled, bool):
            add_check("source_cleaner.enabled", "error", "source_cleaner.enabled 必须为布尔值，当前: " + str(sc_enabled))
        elif sc_enabled is True:
            add_check("source_cleaner.enabled", "ok", "源目录智能清理: 已启用")

        sc_cleanup_mode = source_cleaner.get("cleanup_mode")
        valid_sc_modes = ("media_only", "media_and_related")
        if sc_cleanup_mode is not None:
            if sc_cleanup_mode not in valid_sc_modes:
                add_check("source_cleaner.cleanup_mode", "error", "source_cleaner.cleanup_mode 必须为 " + "/".join(valid_sc_modes) + " 之一，当前: " + str(sc_cleanup_mode))
            else:
                mode_label = "仅保留影视+字幕" if sc_cleanup_mode == "media_only" else "保留影视+字幕+关联文件"
                add_check("source_cleaner.cleanup_mode", "ok", "清理模式: " + mode_label)

        sc_merge = source_cleaner.get("merge_strategy")
        valid_merge = ("intersection", "union")
        if sc_merge is not None:
            if sc_merge not in valid_merge:
                add_check("source_cleaner.merge_strategy", "error", "source_cleaner.merge_strategy 必须为 " + "/".join(valid_merge) + " 之一，当前: " + str(sc_merge))
            else:
                merge_label = "保守(交集)" if sc_merge == "intersection" else "激进(并集)"
                add_check("source_cleaner.merge_strategy", "ok", "AI合并策略: " + merge_label)

        sc_ai = source_cleaner.get("ai_enabled")
        if sc_ai is not None and not isinstance(sc_ai, bool):
            add_check("source_cleaner.ai_enabled", "error", "source_cleaner.ai_enabled 必须为布尔值，当前: " + str(sc_ai))

        sc_junk_size = source_cleaner.get("junk_video_max_size_mb")
        if sc_junk_size is not None:
            if not isinstance(sc_junk_size, int) or sc_junk_size < 0:
                add_check("source_cleaner.junk_video_max_size_mb", "error", "junk_video_max_size_mb 必须为非负整数，当前: " + str(sc_junk_size))
            else:
                add_check("source_cleaner.junk_video_max_size_mb", "ok", "垃圾视频大小阈值: " + str(sc_junk_size) + " MB")

    if norm_source and norm_temp and norm_source == norm_temp:
        add_check("dir_conflict", "error", "源目录与中转目录不能相同，否则会导致数据丢失")
    if norm_source and norm_recycle and norm_source == norm_recycle:
        add_check("dir_conflict", "error", "源目录与回收站目录不能相同，否则会导致数据丢失")
    if norm_temp and norm_recycle and norm_temp == norm_recycle:
        add_check("dir_conflict", "error", "中转目录与回收站目录不能相同，否则会导致数据丢失")

    log_dir = config.get("log_dir", "")
    if not log_dir:
        add_check("log_dir", "warning", "日志目录未配置，将使用默认路径")
    else:
        ok, msg = check_path(log_dir, require_write=True)
        add_check("log_dir", "ok" if ok else "error", msg)
    
    llm_config = config.get("llm", {})
    metadata_config = config.get("metadata", {})
    scrape_mode = metadata_config.get("scrape_mode", "provider_first")
    valid_scrape_modes = ("provider_first", "ai_only")
    if scrape_mode not in valid_scrape_modes:
        add_check("metadata.scrape_mode", "error",
                   "scrape_mode 必须为 " + "/".join(valid_scrape_modes) + " 之一，当前: " + str(scrape_mode))
    else:
        mode_labels = {
            "provider_first": "Provider优先（AI仅补充缺失维度）",
            "ai_only": "纯AI刮削（不使用元数据源API）",
        }
        add_check("metadata.scrape_mode", "ok", "刮削模式: " + mode_labels.get(scrape_mode, scrape_mode))

        # Cross-validate scrape_mode with provider/LLM config
        # As of 2026-06: AI availability is determined by field completeness
        # (api_key + base_url + model), not by the deprecated `llm.enabled` flag.
        llm_api_key = llm_config.get("api_key", "")
        llm_base_url = llm_config.get("base_url", "")
        llm_model = llm_config.get("model", "")
        llm_configured = bool(llm_api_key and llm_base_url and llm_model)
        tmdb_enabled = False
        for p in metadata_config.get("providers", []):
            if p.get("enabled") and p.get("type") == "tmdb":
                tmdb_enabled = True
            elif p.get("type") == "tmdb" and metadata_config.get("tmdb", {}).get("enabled"):
                tmdb_enabled = True
        if not tmdb_enabled and metadata_config.get("tmdb", {}).get("enabled"):
            tmdb_enabled = True

        if scrape_mode == "provider_first" and not tmdb_enabled and not any(
            p.get("enabled") for p in metadata_config.get("providers", [])
        ):
            add_check("metadata.scrape_mode_provider", "warning",
                       "Provider优先模式但未启用任何元数据源，将降级到纯AI刮削")
        if scrape_mode == "ai_only" and not llm_configured:
            add_check("metadata.scrape_mode_llm", "error",
                       "纯AI模式需要完整配置AI刮削（需填写 API Key、接口地址、模型ID）")


    if not llm_config.get("api_key"):
        add_check("llm_api_key", "error", "LLM API Key 未配置")
    elif llm_config.get("api_key") == "***":
        add_check("llm_api_key", "warning", "LLM API Key 为掩码值，请重新输入真实密钥")
    else:
        add_check("llm_api_key", "ok", "LLM API Key 已配置")
    
    if not llm_config.get("base_url"):
        add_check("llm_base_url", "error", "LLM API 地址未配置")
    elif not llm_config.get("base_url", "").startswith(("http://", "https://")):
        add_check("llm_base_url", "error", "LLM API 地址格式错误，应以 http:// 或 https:// 开头")
    else:
        add_check("llm_base_url", "ok", "LLM API 地址格式正确")
    
    if not llm_config.get("model"):
        add_check("llm_model", "error", "LLM 模型名称未配置")
    else:
        add_check("llm_model", "ok", "LLM 模型: " + llm_config.get("model"))
    
    if test_llm:
        llm_ok, llm_msg = test_llm_api(
            llm_config.get("base_url", ""),
            llm_config.get("api_key", ""),
            llm_config.get("model", "")
        )
        add_check("llm_api", "ok" if llm_ok else "error", llm_msg)
    
    hermes_config = config.get("hermes", {})
    if hermes_config.get("enabled", False):
        webhook_config = hermes_config.get("webhook", {})
        if not webhook_config.get("base_url"):
            add_check("hermes_webhook", "error", "Hermes 已启用但 Webhook 地址未配置")
        elif not webhook_config.get("base_url", "").startswith(("http://", "https://")):
            add_check("hermes_webhook", "error", "Hermes Webhook 地址格式错误")
        else:
            add_check("hermes_webhook", "ok", "Hermes Webhook 地址格式正确")
        
        if not webhook_config.get("route_name"):
            add_check("hermes_route", "error", "Hermes 已启用但路由名称未配置")
        else:
            add_check("hermes_route", "ok", "Hermes 路由: " + webhook_config.get("route_name"))
    else:
        add_check("hermes", "ok", "Hermes 通知未启用（可选）")
    
    if test_hermes:
        webhook_config = hermes_config.get("webhook", {})
        hermes_ok, hermes_msg = test_hermes_webhook(
            webhook_config.get("base_url", ""),
            webhook_config.get("route_name", ""),
            webhook_config.get("secret", "")
        )
        add_check("hermes_webhook_test", "ok" if hermes_ok else "error", hermes_msg)
    
    path_rules = config.get("path_rules", [])
    if not path_rules:
        add_check("path_rules", "warning", "入库规则未配置，将使用默认路径")
    else:
        rule_errors = []
        for i, rule in enumerate(path_rules):
            template = rule.get("template", "")
            if not template:
                rule_errors.append("规则 " + str(i + 1) + " 缺少 template")
            elif "{" in template and "}" not in template:
                rule_errors.append("规则 " + str(i + 1) + " template 变量格式不完整")
            conditions = rule.get("conditions", {})
            if not conditions:
                rule_errors.append("规则 " + str(i + 1) + " 缺少 conditions，将作为默认规则")
        
        if rule_errors:
            for err in rule_errors:
                add_check("path_rules", "warning", err)
            add_check("path_rules_count", "ok", "共 " + str(len(path_rules)) + " 条规则")
        else:
            add_check("path_rules", "ok", "入库规则格式正确，共 " + str(len(path_rules)) + " 条")
    
    confidence = config.get("confidence", {})
    if confidence:
        valid_r_formulas = ["inverse", "log", "sqrt", "flat"]
        r_formula = confidence.get("R_formula", "")
        if r_formula and r_formula not in valid_r_formulas:
            add_check("confidence.R_formula", "error", "R_formula 必须为 " + "/".join(valid_r_formulas) + " 之一，当前: " + str(r_formula))
        elif r_formula:
            add_check("confidence.R_formula", "ok", "R_formula: " + r_formula)

        valid_aggregation = ["product", "geometric_mean", "min"]
        aggregation_method = confidence.get("aggregation_method", "")
        if aggregation_method and aggregation_method not in valid_aggregation:
            add_check("confidence.aggregation_method", "error", "aggregation_method 必须为 " + "/".join(valid_aggregation) + " 之一，当前: " + str(aggregation_method))
        elif aggregation_method:
            add_check("confidence.aggregation_method", "ok", "aggregation_method: " + aggregation_method)

        threshold_keys_01 = [
            "pass_threshold", "confirm_threshold", "review_threshold",
            "tmdb_match_threshold", "title_exact_with_year", "title_exact_no_year",
            "title_exact_year_mismatch", "title_fuzzy_year_coeff", "title_min_similarity",
            "R_min_value", "tmdb_dim_confidence", "file_dim_confidence", "dim_missing_confidence"
        ]
        for key in threshold_keys_01:
            val = confidence.get(key)
            if val is not None:
                if not isinstance(val, (int, float)) or val < 0 or val > 1:
                    add_check("confidence." + key, "error", key + " 必须为 0-1 之间的数值，当前: " + str(val))

        pass_t = confidence.get("pass_threshold")
        confirm_t = confidence.get("confirm_threshold")
        review_t = confidence.get("review_threshold")
        if pass_t is not None and confirm_t is not None and pass_t <= confirm_t:
            add_check("confidence.pass_vs_confirm", "error", "pass_threshold 必须大于 confirm_threshold（当前: " + str(pass_t) + " vs " + str(confirm_t) + "）")
        if confirm_t is not None and review_t is not None and confirm_t <= review_t:
            add_check("confidence.confirm_vs_review", "error", "confirm_threshold 必须大于 review_threshold（当前: " + str(confirm_t) + " vs " + str(review_t) + "）")

        r_max_cap = confidence.get("R_max_results_cap")
        if r_max_cap is not None:
            if not isinstance(r_max_cap, int) or r_max_cap < 1:
                add_check("confidence.R_max_results_cap", "error", "R_max_results_cap 必须为正整数，当前: " + str(r_max_cap))

        ai_cap_keys = [k for k in confidence if k.startswith("ai_cap_")]
        for key in ai_cap_keys:
            val = confidence.get(key)
            if val is not None:
                if not isinstance(val, (int, float)) or val < 0 or val > 1:
                    add_check("confidence." + key, "error", key + " 必须为 0-1 之间的数值，当前: " + str(val))

        dimensions = confidence.get("dimensions", {})
        if dimensions:
            for dim_name, dim_conf in dimensions.items():
                if not isinstance(dim_conf, dict):
                    add_check("confidence.dimensions." + dim_name, "warning", "维度 " + dim_name + " 配置格式不正确，应为字典")
                    continue
                weight = dim_conf.get("weight")
                if weight is not None:
                    if not isinstance(weight, (int, float)) or weight <= 0:
                        add_check("confidence.dimensions." + dim_name + ".weight", "error", "维度 " + dim_name + " 的 weight 必须为正数，当前: " + str(weight))
                veto = dim_conf.get("veto_threshold")
                if veto is not None:
                    if not isinstance(veto, (int, float)) or veto < 0 or veto > 1:
                        add_check("confidence.dimensions." + dim_name + ".veto_threshold", "error", "维度 " + dim_name + " 的 veto_threshold 必须为 0-1 之间的数值，当前: " + str(veto))
                source_conf = dim_conf.get("source_confidence")
                if source_conf is not None:
                    if not isinstance(source_conf, dict):
                        add_check("confidence.dimensions." + dim_name + ".source_confidence", "warning", "维度 " + dim_name + " 的 source_confidence 应为字典")
                    else:
                        for src_key, src_val in source_conf.items():
                            if not isinstance(src_val, (int, float)) or src_val < 0 or src_val > 1:
                                add_check("confidence.dimensions." + dim_name + ".source_confidence." + src_key, "error", "维度 " + dim_name + " source_confidence." + src_key + " 必须为 0-1 之间的数值，当前: " + str(src_val))
    else:
        add_check("confidence", "warning", "confidence 配置未设置，将使用默认置信度参数")
    
    try:
        disk_check_dir = config.get("temp_dir", "/tmp")
        stat = os.statvfs(disk_check_dir)
        free_gb = stat.f_bavail * stat.f_frsize / (1024**3)
        if free_gb > 1:
            add_check("disk_space", "ok", "磁盘空间充足 (" + str(round(free_gb, 1)) + " GB)")
        elif free_gb > 0.1:
            add_check("disk_space", "warning", "磁盘空间紧张 (" + str(round(free_gb, 1)) + " GB)")
        else:
            add_check("disk_space", "error", "磁盘空间不足 (" + str(round(free_gb, 1)) + " GB)")
    except Exception as e:
        add_check("disk_space", "error", "磁盘检查失败: " + str(e))
    
    return results