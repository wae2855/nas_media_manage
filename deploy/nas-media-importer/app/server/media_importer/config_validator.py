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
            "extra_info": "这是一条来自NAS影视入库系统的测试消息，验证Hermes Webhook连通性",
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
    if not quarantine_dir:
        add_check("quarantine_dir", "error", "隔离区目录未配置")
    else:
        ok, msg = check_path(quarantine_dir, require_write=True)
        add_check("quarantine_dir", "ok" if ok else "error", msg)

    norm_source = source_dir.rstrip("/") if source_dir else ""
    norm_temp = temp_dir.rstrip("/") if temp_dir else ""
    norm_quarantine = quarantine_dir.rstrip("/") if quarantine_dir else ""

    if norm_source and norm_temp and norm_source == norm_temp:
        add_check("dir_conflict", "error", "源目录与中转目录不能相同，否则会导致数据丢失")
    if norm_source and norm_quarantine and norm_source == norm_quarantine:
        add_check("dir_conflict", "error", "源目录与隔离区目录不能相同，否则会导致数据丢失")
    if norm_temp and norm_quarantine and norm_temp == norm_quarantine:
        add_check("dir_conflict", "error", "中转目录与隔离区目录不能相同，否则会导致数据丢失")

    log_dir = config.get("log_dir", "")
    if not log_dir:
        add_check("log_dir", "warning", "日志目录未配置，将使用默认路径")
    else:
        ok, msg = check_path(log_dir, require_write=True)
        add_check("log_dir", "ok" if ok else "error", msg)
    
    llm_config = config.get("llm", {})
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