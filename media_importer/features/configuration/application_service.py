from typing import Callable

from media_importer.core.config_loader import mask_sensitive


SECTION_FIELD_MAP = {
    "basic": ["source_dir", "temp_dir", "source_policy"],
    "path_rules": ["path_rules", "fallback_dir"],
    "import_options": ["manual_review", "duplicate_handling", "filename_templates"],
    "metadata.providers": ["metadata"],
    "ai_assist": ["ai_assist"],
    "ai_search": ["ai_search"],
    "ai_apikey": ["__synthetic__"],
    "ai_prompts": ["__synthetic__"],
    "ai_scene_strategy": ["ai_scene_strategy"],
    "server": ["server"],
    "hermes": ["hermes"],
    "file_watcher": ["file_watcher"],
    "advanced": ["log_dir", "task_queue", "video_extensions", "subtitle_extensions"],
    "source_cleaner": ["source_cleaner"],
}


_PROMPT_FIELDS = (
    "prompt_title_clean",
    "prompt_match_assist",
    "prompt_dimension_mapping",
    "prompt_source_clean",
    "prompt_match_assist_instruction",
    "prompt_dimension_mapping_instruction",
    "prompt_source_clean_instruction",
    "prompt_dimension_supplement_instruction",
)


def build_config_ui_payload(config: dict) -> dict:
    masked = mask_sensitive(config) if config else {}
    source_policy = masked.get("source_policy", {})
    if "cleanup_mode" not in source_policy:
        cleanup_after_done = source_policy.get("cleanup_source_after_done")
        if cleanup_after_done is False:
            source_policy["cleanup_mode"] = "read_only"
        elif cleanup_after_done is True:
            source_policy["cleanup_mode"] = "full_cleanup"
    if "delete_source_after_import" not in source_policy:
        source_policy["delete_source_after_import"] = source_policy.get(
            "cleanup_source_after_done", True
        )
    return {"config": masked}


def build_section_config_update(section: str, data: dict, current_config: dict) -> dict:
    if not section or not data:
        raise ValueError("缺少 section 或 data 参数")
    if section not in SECTION_FIELD_MAP:
        raise KeyError(f"未知的配置区块: {section}")

    if section == "ai_apikey":
        return _build_ai_apikey_section(data, current_config)
    if section == "ai_prompts":
        return _build_ai_prompts_section(data, current_config)
    if section == "ai_scene_strategy":
        return _build_ai_scene_strategy_section(data)

    section_body = {key: data[key] for key in SECTION_FIELD_MAP[section] if key in data}
    if not section_body:
        raise ValueError("区块数据为空")

    if section == "metadata.providers":
        _merge_provider_sensitive_fields(section_body, current_config)
    return section_body


def _build_ai_apikey_section(data: dict, current_config: dict) -> dict:
    """合并 ai_assist / ai_search 两个子节到顶层 ai_assist / ai_search。

    输入：data = {ai_assist: {...}, ai_search: {...}}（每个子节可含 base_url/api_key/model 等）
    输出：{ai_assist: {...}, ai_search: {...}}

    脱敏规则：
    - 值为 "***" 跳过（前端掩码，避免覆盖真实配置）
    - api_key 字段为空字符串跳过（前端输入框留空，避免覆盖真实密钥）
    """
    out = {}
    current = current_config or {}
    for sub in ("ai_assist", "ai_search"):
        sub_data = data.get(sub, {})
        if not isinstance(sub_data, dict):
            continue
        merged = dict(current.get(sub, {}) or {})
        for key, value in sub_data.items():
            if isinstance(value, str) and "***" in value:
                continue
            if key == "api_key" and value == "":
                continue
            merged[key] = value
        if merged:
            out[sub] = merged
    if not out:
        raise ValueError("ai_apikey 区块数据为空")
    return out


def _build_ai_prompts_section(data: dict, current_config: dict) -> dict:
    """仅写入 prompt_* 字段，保留每个子节其他字段不变。

    输入：data = {ai_assist: {prompt_title_clean: ..., ...}, ai_search: {prompt_dimension_supplement: ...}}
    """
    out = {}
    current = current_config or {}
    for sub in ("ai_assist", "ai_search"):
        sub_data = data.get(sub, {})
        if not isinstance(sub_data, dict):
            continue
        prompt_only = {k: v for k, v in sub_data.items() if k in _PROMPT_FIELDS or k == "prompt_dimension_supplement"}
        if not prompt_only:
            continue
        merged = dict(current.get(sub, {}) or {})
        merged.update(prompt_only)
        out[sub] = merged
    if not out:
        raise ValueError("ai_prompts 区块数据为空")
    return out


def _build_ai_scene_strategy_section(data: dict) -> dict:
    """校验 5 个场景 key 完整。"""
    required = (
        "dimension_supplement", "dimension_mapping",
        "title_clean", "match_assist", "source_clean",
    )
    missing = [s for s in required if s not in data]
    if missing:
        raise ValueError(f"ai_scene_strategy 缺少场景: {missing}")
    return {"ai_scene_strategy": data}


def build_config_permission_payload(
    body: dict,
    current_config: dict,
    check_permissions: Callable[[dict], dict],
) -> dict:
    config_to_check = body if body else (current_config or {})
    return check_permissions(config_to_check)


def build_path_test_payload(
    body: dict,
    check_path_permission: Callable[..., dict],
    get_current_user: Callable[[], str],
) -> dict:
    path = (body or {}).get("path", "").strip()
    need_write = bool((body or {}).get("need_write", True))
    if not path:
        raise ValueError("path 参数必填")
    result = check_path_permission(path, need_write=need_write)
    result["user"] = get_current_user()
    return result


def build_watcher_status_payload(watcher) -> dict:
    if not watcher:
        return {"enabled": False, "status": "not_started"}
    is_running = watcher.is_running()
    return {
        "enabled": is_running,
        "poll_interval": watcher.poll_interval,
        "status": "running" if is_running else "stopped",
    }


def _merge_provider_sensitive_fields(section_body: dict, current_config: dict):
    metadata = section_body.get("metadata")
    if not isinstance(metadata, dict):
        return
    new_providers = metadata.get("providers", [])
    if not new_providers:
        return

    current_config = current_config or {}
    existing_providers = current_config.get("metadata", {}).get("providers", [])

    for new_provider in new_providers:
        provider_type = new_provider.get("type", "")
        existing_provider = next(
            (
                provider
                for provider in existing_providers
                if provider.get("type") == provider_type
            ),
            None,
        )
        api_key = new_provider.get("api_key")
        if api_key and api_key != "***":
            continue
        if existing_provider and existing_provider.get("api_key") not in ("", "***", None):
            new_provider["api_key"] = existing_provider["api_key"]
