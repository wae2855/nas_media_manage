import hashlib
import json
from typing import Callable

from media_importer.core.config_loader import mask_sensitive

from .fnos_directory_access import build_fnos_directory_capability
from .storage_readiness import inspect_storage_readiness

SECTION_FIELD_MAP = {
    "basic": ["source_dir", "temp_dir", "source_policy"],
    "path_rules": [
        "library_roots", "default_library_root_id", "library_root",
        "path_rules", "fallback_library_root_id", "fallback_dir",
    ],
    "import_options": ["manual_review", "duplicate_handling", "filename_templates"],
    "metadata.providers": ["metadata"],
    "llm": ["llm"],
    "server": ["server"],
    "file_watcher": ["file_watcher"],
    "advanced": ["log_dir", "task_queue", "video_extensions", "subtitle_extensions"],
    "source_cleaner": ["source_cleaner"],
}


def config_revision(config: dict) -> str:
    public_config = {
        key: value for key, value in (config or {}).items()
        if not str(key).startswith("_")
    }
    encoded = json.dumps(
        public_config,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]



def build_config_ui_payload(config: dict) -> dict:
    masked = mask_sensitive(config) if config else {}
    source_policy = masked.get("source_policy", {})
    if "mode" not in source_policy:
        source_policy["mode"] = (
            "recycle_source_unit"
            if source_policy.get("cleanup_source_after_done") is True
            else "preserve_all"
        )
    source_policy["cleanup_mode"] = (
        "full_cleanup" if source_policy["mode"] == "recycle_source_unit" else "read_only"
    )
    if "delete_source_after_import" not in source_policy:
        source_policy["delete_source_after_import"] = source_policy.get(
            "cleanup_source_after_done", False
        ) is True
    directory_authorization = build_fnos_directory_capability()
    return {
        "config": masked,
        "revision": config_revision(config or {}),
        "directory_authorization": directory_authorization,
        "readiness": inspect_storage_readiness(
            config or {}, authorization_capability=directory_authorization,
        ),
    }


def build_section_config_update(section: str, data: dict, current_config: dict) -> dict:
    if not section or not data:
        raise ValueError("缺少 section 或 data 参数")
    if section not in SECTION_FIELD_MAP:
        raise KeyError(f"未知的配置区块: {section}")


    section_body = {key: data[key] for key in SECTION_FIELD_MAP[section] if key in data}
    if not section_body:
        raise ValueError("区块数据为空")

    if section == "metadata.providers":
        _merge_provider_sensitive_fields(section_body, current_config)
    if section == "import_options" and "duplicate_handling" in section_body:
        section_body["duplicate_handling"] = {
            **(section_body.get("duplicate_handling") or {}),
            "enabled": True,
            "strategy": "confirm",
        }
    return section_body








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
