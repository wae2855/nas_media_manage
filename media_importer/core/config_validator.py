#!/usr/bin/env python3
"""
配置检测模块
用于检测各项配置项的有效性，包括路径存在性、API连通性等
"""

import os
import time
from typing import Any, Dict, Tuple

import requests

from media_importer.infrastructure.filesystem import check_write_permission


def check_path(path: str, require_write: bool = False) -> Tuple[bool, str]:
    if not path:
        return False, "路径未配置"

    if not os.path.exists(path):
        return False, f"路径不存在: {path}"

    if not os.path.isdir(path):
        return False, f"路径不是目录: {path}"

    if require_write:
        ok, message = check_write_permission(path)
        if ok:
            return True, f"路径存在且可写: {path}"
        return False, f"路径不可写: {path}, 错误: {message}"

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
        # 兼容 base_url 已含 /chat/completions 的填法
        trimmed = base_url.rstrip("/")
        test_url = trimmed if trimmed.endswith("/chat/completions") else trimmed + "/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": model, "messages": [{"role": "user", "content": "test"}], "max_tokens": 5}

        response = requests.post(test_url, json=payload, headers=headers, timeout=timeout)

        if response.status_code == 200:
            return True, "LLM API连通正常 (状态码: 200)"
        elif response.status_code == 401:
            return False, "LLM API认证失败 (状态码: 401, 请检查API密钥)"
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


def validate_config(config: Dict[str, Any], test_llm: bool = False) -> Dict[str, Any]:
    """
    验证配置 - 基础有效性检查

    Args:
        config: 配置字典
        test_llm: 是否测试LLM API（默认不测试，由独立按钮触发）

    Returns:
        验证结果字典
    """
    results = {"overall": "ok", "details": [], "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}

    def add_check(item, status, message):
        results["details"].append({"item": item, "status": status, "message": message})
        if status == "error":
            results["overall"] = "degraded"

    source_dir = config.get("source_dir", "")
    source_policy_pre = config.get("source_policy", {}) or {}
    source_cleaner_pre = config.get("source_cleaner", {}) or {}
    source_mode_pre = source_policy_pre.get("mode")
    if source_mode_pre not in {"preserve_all", "preserve_media", "recycle_source_unit"}:
        if source_policy_pre.get("cleanup_source_after_done") is True:
            source_mode_pre = "recycle_source_unit"
        elif source_cleaner_pre.get("enabled") is True:
            source_mode_pre = "preserve_media"
        else:
            source_mode_pre = "preserve_all"
    source_requires_write = source_mode_pre == "recycle_source_unit" or (
        source_mode_pre == "preserve_media" and source_cleaner_pre.get("enabled") is True
    )
    if not source_dir:
        add_check("source_dir", "error", "源目录未配置")
    else:
        ok, msg = check_path(source_dir, require_write=source_requires_write)
        add_check("source_dir", "ok" if ok else "error", msg)

    source_policy = config.get("source_policy", {})
    quarantine_dir = source_policy.get("quarantine_dir", "")
    recycle_dir = source_policy.get("recycle_dir", "") or quarantine_dir
    if not recycle_dir:
        add_check("recycle_dir", "error", "回收站目录未配置")
    else:
        ok, msg = check_path(recycle_dir, require_write=True)
        add_check("recycle_dir", "ok" if ok else "error", msg)

    if source_policy.get("cleanup_mode") is not None:
        add_check("source_policy.cleanup_mode", "warning", "cleanup_mode 不再使用，请迁移到 cleanup_source_after_done")
    if source_policy.get("delete_source_after_import") is not None:
        add_check(
            "source_policy.delete_source_after_import",
            "warning",
            "delete_source_after_import 不再使用，请迁移到 cleanup_source_after_done",
        )

    cleanup_after_done = source_policy.get("cleanup_source_after_done")
    if cleanup_after_done is not None and not isinstance(cleanup_after_done, bool):
        add_check(
            "source_policy.cleanup_source_after_done",
            "error",
            "cleanup_source_after_done 必须为布尔值，当前: " + str(cleanup_after_done),
        )
    elif cleanup_after_done is True:
        add_check("source_policy.cleanup_source_after_done", "ok", "入库后自动清理源文件: 已启用")
    elif cleanup_after_done is False:
        add_check("source_policy.cleanup_source_after_done", "ok", "入库后保留源文件: 只读模式")

    retention_days = source_policy.get("recycle_retention_days")
    if retention_days is not None:
        if not isinstance(retention_days, int) or retention_days < 0:
            add_check(
                "source_policy.recycle_retention_days",
                "error",
                "recycle_retention_days 必须为非负整数，当前: " + str(retention_days),
            )
        else:
            add_check("source_policy.recycle_retention_days", "ok", "回收站保留天数: " + str(retention_days))

    task_queue = config.get("task_queue", {})
    max_concurrent = (
        task_queue.get("max_concurrent", 1)
        if isinstance(task_queue, dict)
        else None
    )
    if (
        isinstance(max_concurrent, bool)
        or not isinstance(max_concurrent, int)
        or not 1 <= max_concurrent <= 2
    ):
        add_check(
            "task_queue.max_concurrent",
            "error",
            "最大并发任务数必须是 1 或 2，当前: " + str(max_concurrent),
        )
    else:
        add_check(
            "task_queue.max_concurrent",
            "ok",
            "最大并发任务数: " + str(max_concurrent),
        )

    source_cleaner = config.get("source_cleaner", {})
    if source_cleaner:
        sc_enabled = source_cleaner.get("enabled")
        if sc_enabled is not None and not isinstance(sc_enabled, bool):
            add_check(
                "source_cleaner.enabled", "error", "source_cleaner.enabled 必须为布尔值，当前: " + str(sc_enabled)
            )
        elif sc_enabled is True:
            add_check("source_cleaner.enabled", "ok", "源目录智能清理: 已启用")

        sc_cleanup_mode = source_cleaner.get("cleanup_mode")
        valid_sc_modes = ("media_only", "media_and_related")
        if sc_cleanup_mode is not None:
            if sc_cleanup_mode not in valid_sc_modes:
                add_check(
                    "source_cleaner.cleanup_mode",
                    "error",
                    "source_cleaner.cleanup_mode 必须为 "
                    + "/".join(valid_sc_modes)
                    + " 之一，当前: "
                    + str(sc_cleanup_mode),
                )
            else:
                mode_label = "仅保留影视+字幕" if sc_cleanup_mode == "media_only" else "保留影视+字幕+关联文件"
                add_check("source_cleaner.cleanup_mode", "ok", "清理模式: " + mode_label)

        sc_merge = source_cleaner.get("merge_strategy")
        valid_merge = ("intersection", "union")
        if sc_merge is not None:
            if sc_merge not in valid_merge:
                add_check(
                    "source_cleaner.merge_strategy",
                    "error",
                    "source_cleaner.merge_strategy 必须为 " + "/".join(valid_merge) + " 之一，当前: " + str(sc_merge),
                )
            else:
                merge_label = "保守(交集)" if sc_merge == "intersection" else "激进(并集)"
                add_check("source_cleaner.merge_strategy", "ok", "AI合并策略: " + merge_label)

        sc_ai = source_cleaner.get("ai_enabled")
        if sc_ai is not None and not isinstance(sc_ai, bool):
            add_check(
                "source_cleaner.ai_enabled", "error", "source_cleaner.ai_enabled 必须为布尔值，当前: " + str(sc_ai)
            )

        sc_junk_size = source_cleaner.get("junk_video_max_size_mb")
        if sc_junk_size is not None:
            if not isinstance(sc_junk_size, int) or sc_junk_size < 0:
                add_check(
                    "source_cleaner.junk_video_max_size_mb",
                    "error",
                    "junk_video_max_size_mb 必须为非负整数，当前: " + str(sc_junk_size),
                )
            else:
                add_check(
                    "source_cleaner.junk_video_max_size_mb", "ok", "垃圾视频大小阈值: " + str(sc_junk_size) + " MB"
                )

    candidate_filter = config.get("media_candidate_filter", {}) or {}
    if candidate_filter:
        candidate_enabled = candidate_filter.get("enabled")
        if candidate_enabled is not None and not isinstance(candidate_enabled, bool):
            add_check(
                "media_candidate_filter.enabled",
                "error",
                "媒体候选过滤开关必须为布尔值",
            )
        for key, label in (
            ("small_video_max_mb", "小视频上限"),
            ("main_video_min_mb", "主视频下限"),
        ):
            value = candidate_filter.get(key)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                    add_check(
                        f"media_candidate_filter.{key}",
                        "error",
                        f"{label}必须为非负数字",
                    )
                else:
                    add_check(
                        f"media_candidate_filter.{key}",
                        "ok",
                        f"{label}: {value} MB",
                    )
        ratio = candidate_filter.get("max_size_ratio")
        if ratio is not None:
            if (
                isinstance(ratio, bool)
                or not isinstance(ratio, (int, float))
                or not 0 <= ratio <= 1
            ):
                add_check(
                    "media_candidate_filter.max_size_ratio",
                    "error",
                    "附带视频体积比例必须在 0 到 1 之间",
                )
            else:
                add_check(
                    "media_candidate_filter.max_size_ratio",
                    "ok",
                    f"附带视频体积比例上限: {ratio:g}",
                )
        patterns = candidate_filter.get("extra_name_patterns")
        if patterns is not None:
            if not isinstance(patterns, list) or not all(
                isinstance(pattern, str) for pattern in patterns
            ):
                add_check(
                    "media_candidate_filter.extra_name_patterns",
                    "error",
                    "自定义推广文件名模式必须是字符串列表",
                )
            else:
                add_check(
                    "media_candidate_filter.extra_name_patterns",
                    "ok",
                    f"自定义推广模式: {len(patterns)} 条",
                )

    watcher = config.get("file_watcher", {}) or {}
    poll_interval = watcher.get("poll_interval", 300)
    if isinstance(poll_interval, bool) or not isinstance(poll_interval, int):
        add_check("file_watcher.poll_interval", "error", "自动运行轮询周期必须为整数秒")
    elif not 10 <= poll_interval <= 3600:
        add_check("file_watcher.poll_interval", "error", "自动运行轮询周期必须在 10 到 3600 秒之间")
    else:
        add_check("file_watcher.poll_interval", "ok", f"自动运行每 {poll_interval} 秒检查一次")

    from media_importer.features.configuration.storage_topology import (
        topology_error_messages,
    )

    for message in topology_error_messages(config):
        add_check("dir_conflict", "error", message)

    log_dir = config.get("log_dir", "")
    if not log_dir:
        add_check("log_dir", "warning", "日志目录未配置，将使用默认路径")
    else:
        ok, msg = check_path(log_dir, require_write=True)
        add_check("log_dir", "ok" if ok else "error", msg)

    metadata_config = config.get("metadata", {})
    scrape_mode = metadata_config.get("scrape_mode", "provider_first")
    valid_scrape_modes = ("provider_first",)
    if scrape_mode not in valid_scrape_modes:
        add_check(
            "metadata.scrape_mode",
            "error",
            "scrape_mode 必须为 " + "/".join(valid_scrape_modes) + " 之一，当前: " + str(scrape_mode),
        )
    else:
        mode_labels = {
            "provider_first": "Provider优先（AI仅补充缺失维度）",
        }
        add_check("metadata.scrape_mode", "ok", "刮削模式: " + mode_labels.get(scrape_mode, scrape_mode))

        tmdb_enabled = any(p.get("enabled") for p in metadata_config.get("providers", []) if p.get("type") == "tmdb")

        if (
            scrape_mode == "provider_first"
            and not tmdb_enabled
            and not any(p.get("enabled") for p in metadata_config.get("providers", []))
        ):
            add_check("metadata.scrape_mode_provider", "warning", "Provider优先模式但未启用任何元数据源")

    # LLM 配置检查（ADR-0010：LLM 仅服务源目录清理器，llm 块为唯一配置源）
    llm_cfg = config.get("llm", {})
    if not llm_cfg.get("api_key"):
        add_check("llm.api_key", "warning", "LLM API Key 未配置（源目录清理器 AI 功能不可用）")
    elif llm_cfg.get("api_key") == "***":
        add_check("llm.api_key", "warning", "LLM API Key 为掩码值，请重新输入真实密钥")
    else:
        add_check("llm.api_key", "ok", "LLM API Key 已配置")

    if not llm_cfg.get("base_url"):
        add_check("llm.base_url", "warning", "LLM API 地址未配置")
    elif not llm_cfg.get("base_url", "").startswith(("http://", "https://")):
        add_check("llm.base_url", "error", "LLM API 地址格式错误，应以 http:// 或 https:// 开头")
    else:
        add_check("llm.base_url", "ok", "LLM API 地址格式正确")

    if not llm_cfg.get("model"):
        add_check("llm.model", "warning", "LLM 模型名称未配置")
    else:
        add_check("llm.model", "ok", "LLM 模型: " + llm_cfg.get("model"))

    if test_llm:
        if llm_cfg.get("api_key") and llm_cfg.get("base_url") and llm_cfg.get("model"):
            llm_ok, llm_msg = test_llm_api(
                llm_cfg.get("base_url", ""), llm_cfg.get("api_key", ""), llm_cfg.get("model", "")
            )
            add_check("llm_api", "ok" if llm_ok else "error", llm_msg)

    library_root = str(config.get("library_root", "") or "").strip()
    migration_error = config.get("_library_migration_error", "")
    if migration_error:
        add_check("library_root", "error", f"旧入库规则迁移失败: {migration_error}")
    elif not library_root:
        try:
            from media_importer.features.configuration.library_paths import canonicalize_library_config
            inferred = canonicalize_library_config(config).get("library_root", "")
        except ValueError as exc:
            add_check("library_root", "error", f"旧入库规则无法安全迁移: {exc}")
        else:
            add_check(
                "library_root", "warning",
                "旧入库规则将在保存时归入片库根目录" if inferred else "片库根目录尚未配置",
            )
    elif not os.path.isabs(library_root):
        add_check("library_root", "error", "片库根目录必须是绝对路径")
    else:
        ok, msg = check_path(library_root, require_write=True)
        add_check("library_root", "ok" if ok else "error", msg)

    source_policy = config.get("source_policy", {}) or {}
    source_mode = source_policy.get("mode")
    if source_mode not in {"preserve_all", "preserve_media", "recycle_source_unit"}:
        if "mode" in source_policy:
            add_check("source_policy.mode", "error", "源文件处理模式无效")
        else:
            add_check("source_policy.mode", "warning", "旧版源文件策略将在保存时迁移")
    disposal_mode = source_policy.get("disposal_mode", "local_recycle")
    if disposal_mode not in {"local_recycle", "permanent_delete"}:
        add_check("source_policy.disposal_mode", "error", "来源处置方式无效")
    elif source_mode == "preserve_all" and disposal_mode == "permanent_delete":
        add_check(
            "source_policy.disposal_mode",
            "error",
            "完整保留模式不能同时选择永久删除来源",
        )
    elif disposal_mode == "permanent_delete":
        add_check(
            "source_policy.disposal_mode",
            "warning",
            "来源内容将永久删除，无法从应用回收区恢复",
        )
    source_cleaner = config.get("source_cleaner", {}) or {}
    if source_cleaner.get("enabled") is True and source_mode not in {None, "preserve_media"}:
        add_check("source_cleaner.enabled", "error", "智能清理仅能用于保留媒体模式")
    if source_cleaner.get("ai_enabled") is True and source_mode != "preserve_media":
        add_check("source_cleaner.ai_enabled", "error", "LLM 辅助清理仅能用于保留媒体模式")

    path_rules = config.get("path_rules", [])
    if not path_rules:
        add_check("path_rules", "warning", "入库规则未配置，将使用默认路径")
    else:
        rule_errors = []
        for i, rule in enumerate(path_rules):
            template = rule.get("template", "")
            if not template:
                rule_errors.append("规则 " + str(i + 1) + " 缺少 template")
            elif library_root and os.path.isabs(template):
                rule_errors.append("规则 " + str(i + 1) + " 必须使用片库根目录下的相对子目录")
            elif library_root and (os.path.normpath(template) == ".." or os.path.normpath(template).startswith(".." + os.sep)):
                rule_errors.append("规则 " + str(i + 1) + " 超出片库根目录")
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
        roots = config.get("library_roots") or []
        disk_check_dir = next(
            (
                str(root.get("path") or "")
                for root in roots
                if isinstance(root, dict) and root.get("enabled", True) is not False
            ),
            config.get("source_dir", "/tmp"),
        )
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
