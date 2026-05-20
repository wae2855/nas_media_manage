#!/usr/bin/env python3
"""
配置检测模块
用于检测各项配置项的有效性，包括路径存在性、API连通性等
"""
import os
import time
import requests
from typing import Dict, Any, List, Tuple


def check_path(path: str, require_write: bool = False) -> Tuple[bool, str]:
    """
    检查路径是否存在，可选检查写入权限
    
    Args:
        path: 要检查的路径
        require_write: 是否需要写入权限
    
    Returns:
        (是否通过, 详细信息)
    """
    if not path:
        return False, "路径未配置"
    
    if not os.path.exists(path):
        try:
            os.makedirs(path, exist_ok=True)
            return True, f"路径不存在，已自动创建: {path}"
        except Exception as e:
            return False, f"路径不存在且无法创建: {path}, 错误: {str(e)}"
    
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
        # 使用OpenAI兼容的API测试
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
    """
    测试Hermes Webhook连通性
    
    Args:
        base_url: Hermes服务地址
        route_name: Webhook路由名称
        secret: 签名密钥
        timeout: 超时时间（秒）
    
    Returns:
        (是否通过, 详细信息)
    """
    if not base_url:
        return True, "Hermes未启用或地址未配置（可选）"
    
    try:
        # 尝试访问Hermes的健康检查端点（如果有的话）
        health_url = base_url.rstrip("/") + "/health"
        response = requests.get(health_url, timeout=timeout)
        
        if response.status_code in [200, 404]:
            # 404是可以接受的，因为可能没有health端点
            return True, f"Hermes服务地址可访问: {base_url}"
        else:
            return False, f"Hermes服务返回错误状态码: {response.status_code}"
    
    except requests.exceptions.Timeout:
        return False, f"Hermes连接超时 ({timeout}秒)"
    except requests.exceptions.ConnectionError:
        return False, f"Hermes连接失败 (无法连接到: {base_url})"
    except Exception as e:
        return False, f"Hermes测试异常: {str(e)}"


def validate_config(config: Dict[str, Any], test_llm: bool = True, test_hermes: bool = True) -> Dict[str, Any]:
    """
    全面验证配置
    
    Args:
        config: 配置字典
        test_llm: 是否测试LLM API
        test_hermes: 是否测试Hermes Webhook
    
    Returns:
        验证结果字典
    """
    results = {
        "overall": "ok",
        "checks": {},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
    }
    
    # 检查源目录
    source_dir = config.get("source_dir", "")
    ok, msg = check_path(source_dir, require_write=False)
    results["checks"]["source_dir"] = {
        "status": "ok" if ok else "error",
        "message": msg
    }
    if not ok:
        results["overall"] = "degraded"
    
    # 检查临时目录
    temp_dir = config.get("temp_dir", "")
    ok, msg = check_path(temp_dir, require_write=True)
    results["checks"]["temp_dir"] = {
        "status": "ok" if ok else "error",
        "message": msg
    }
    if not ok:
        results["overall"] = "degraded"
    
    # 检查日志目录
    log_dir = config.get("log_dir", "")
    ok, msg = check_path(log_dir, require_write=True)
    results["checks"]["log_dir"] = {
        "status": "ok" if ok else "error",
        "message": msg
    }
    if not ok:
        results["overall"] = "degraded"
    
    # 检查任务持久化目录
    task_queue = config.get("task_queue", {})
    persistence_path = task_queue.get("persistence_path", "")
    if persistence_path:
        persistence_dir = os.path.dirname(persistence_path)
        if persistence_dir:
            ok, msg = check_path(persistence_dir, require_write=True)
            results["checks"]["task_persistence_dir"] = {
                "status": "ok" if ok else "error",
                "message": msg
            }
            if not ok:
                results["overall"] = "degraded"
    
    # 测试LLM API
    llm_config = config.get("llm", {})
    if test_llm:
        ok, msg = test_llm_api(
            base_url=llm_config.get("base_url", ""),
            api_key=llm_config.get("api_key", ""),
            model=llm_config.get("model", ""),
            timeout=llm_config.get("timeout", 10)
        )
        results["checks"]["llm_api"] = {
            "status": "ok" if ok else "error",
            "message": msg
        }
        if not ok:
            results["overall"] = "degraded"
    else:
        results["checks"]["llm_api"] = {
            "status": "skipped",
            "message": "跳过LLM API测试"
        }
    
    # 测试Hermes
    hermes_config = config.get("hermes", {})
    if hermes_config.get("enabled", False) and test_hermes:
        ok, msg = test_hermes_webhook(
            base_url=hermes_config.get("webhook", {}).get("base_url", ""),
            route_name=hermes_config.get("webhook", {}).get("route_name", ""),
            secret=hermes_config.get("webhook", {}).get("secret", "")
        )
        results["checks"]["hermes_webhook"] = {
            "status": "ok" if ok else "error",
            "message": msg
        }
        if not ok:
            results["overall"] = "degraded"
    else:
        results["checks"]["hermes_webhook"] = {
            "status": "skipped",
            "message": "Hermes未启用或跳过测试"
        }
    
    # 检查磁盘空间
    temp_dir_for_check = config.get("temp_dir", "/tmp")
    try:
        if os.path.exists(temp_dir_for_check):
            stat = os.statvfs(temp_dir_for_check)
            free_gb = stat.f_bavail * stat.f_frsize / (1024**3)
            if free_gb > 1:
                results["checks"]["disk_space"] = {
                    "status": "ok",
                    "message": f"磁盘空间充足 ({free_gb:.1f} GB 可用)"
                }
            elif free_gb > 0.5:
                results["checks"]["disk_space"] = {
                    "status": "warning",
                    "message": f"磁盘空间偏低 ({free_gb:.1f} GB 可用)"
                }
                if results["overall"] == "ok":
                    results["overall"] = "degraded"
            else:
                results["checks"]["disk_space"] = {
                    "status": "error",
                    "message": f"磁盘空间严重不足 ({free_gb:.1f} GB 可用)"
                }
                results["overall"] = "degraded"
    except Exception as e:
        results["checks"]["disk_space"] = {
            "status": "error",
            "message": f"检查磁盘空间失败: {str(e)}"
        }
        results["overall"] = "degraded"
    
    return results
