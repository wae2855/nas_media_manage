BOOL_TRUE_STRINGS = {'true', 'yes', 'on'}
BOOL_FALSE_STRINGS = {'false', 'no', 'off'}
BOOL_KEYS = {
    'enabled', 'verify_ssl', 'delete_after_process', 'recursive',
    'create_series_folder', 'organize_by_season', 'create_year_folder',
    'auto_delete_success', 'scan_source', 'cleanup_source_after_done',
    'ai_enabled', 'cleanup_empty_dirs', 'confirm_before_cleanup',
}


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


def _migrate_mcp_to_web_search(config: dict) -> None:
    llm = config.get("llm", {})

    llm.pop("provider", None)

    if "mcp" not in llm:
        return

    mcp = llm.pop("mcp")

    if mcp.get("enabled"):
        scenarios = mcp.get("scenarios", {})
        llm["web_search"] = {
            "enabled": True,
            "enabled_for_scrape": scenarios.get("scrape", True),
            "enabled_for_series_scrape": scenarios.get("series_scrape", True),
        }

    llm.pop("provider", None)


def _normalize_bool_strings_in_list(lst):
    for i in range(len(lst)):
        item = lst[i]
        if isinstance(item, dict):
            _normalize_bool_strings(item)
        elif isinstance(item, list):
            _normalize_bool_strings_in_list(item)
