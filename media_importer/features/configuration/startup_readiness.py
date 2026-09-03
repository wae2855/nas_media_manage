"""正式运行前的统一只读配置检查。"""

from __future__ import annotations

from collections.abc import Callable

from .application_service import config_revision
from .library_paths import LibraryPathError, canonicalize_library_config
from .storage_readiness import automatic_blocking_reasons, inspect_storage_readiness

Probe = Callable[[dict], tuple[bool, str]]


def _check(check_id: str, label: str, status: str, message: str,
           fix_target: str = "") -> dict:
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "message": message,
        "fix_target": fix_target,
    }


def _default_provider_probe(provider: dict) -> tuple[bool, str]:
    if provider.get("type") != "tmdb":
        return True, "元数据源配置已识别"
    api_key = provider.get("api_key", "")
    if not api_key or api_key == "***":
        return False, "TMDB API Key 未配置"
    try:
        from media_importer.features.scraping import TMDbClient
        ok = TMDbClient(api_key).test_connection()
        return ok, "TMDB 可连接" if ok else "TMDB 连接失败"
    except Exception as exc:  # 网络/服务异常必须转为检查结果，不能击穿接口
        return False, f"TMDB 检查失败: {exc}"


def _default_llm_probe(llm: dict) -> tuple[bool, str]:
    from media_importer.core.config_validator import test_llm_api

    return test_llm_api(
        llm.get("base_url", ""), llm.get("api_key", ""), llm.get("model", "")
    )


def _referenced_library_targets(config: dict) -> list[tuple[str, str]]:
    references = []
    for index, rule in enumerate(config.get("path_rules", []) or []):
        if not isinstance(rule, dict):
            continue
        label = str(rule.get("name", "") or f"第 {index + 1} 条规则").strip()
        references.append((label, str(rule.get("library_root_id", "") or "").strip()))
    if str(config.get("fallback_dir", "") or "").strip():
        references.append((
            "兜底入库目录",
            str(config.get("fallback_library_root_id", "") or "").strip(),
        ))
    return references


def inspect_startup_readiness(config: dict, *, provider_probe: Probe | None = None,
                              llm_probe: Probe | None = None,
                              watcher_running: bool | None = None,
                              conn=None) -> dict:
    config = config or {}
    checks = []
    storage = inspect_storage_readiness(config)
    storage_ok = storage.get("state") == "READY"
    storage_message = "存在不可用目录、权限或空间问题"
    if storage_ok:
        storage_message = (
            f"目录均可使用；另有 {len(storage.get('warnings', []))} 项运行提示"
            if storage.get("warnings")
            else "目录存在、权限和磁盘空间均正常"
        )
    checks.append(_check(
        "storage", "目录与磁盘", "PASS" if storage_ok else "BLOCKED",
        storage_message, "storage",
    ))

    try:
        canonical = canonicalize_library_config(config, require_rule_assignments=True)
        if not canonical.get("library_root"):
            raise LibraryPathError("片库根目录未配置")
    except LibraryPathError as exc:
        checks.append(_check(
            "library", "规则与目标片库", "BLOCKED", str(exc), "rules"
        ))
    else:
        target_locations = {
            str(item.get("id", ""))[7:]: item
            for item in storage.get("locations", [])
            if str(item.get("id", "")).startswith("target:")
        }
        unavailable = []
        for label, root_id in _referenced_library_targets(canonical):
            location = target_locations.get(root_id)
            capabilities = location.get("capabilities", {}) if location else {}
            if (
                not location
                or location.get("level") == "error"
                or not capabilities.get("read")
                or not capabilities.get("write")
            ):
                reason = str(location.get("message", "") if location else "片库目录未进入存储检查")
                unavailable.append(f"{label}的目标片库不可用：{reason}")
        if unavailable:
            checks.append(_check(
                "library", "规则与目标片库", "BLOCKED", unavailable[0], "storage"
            ))
        else:
            checks.append(_check(
                "library", "规则与目标片库", "PASS",
                "全部规则均已绑定有效片库，相关目录可读取并新增入库",
            ))

    providers = [
        provider for provider in config.get("metadata", {}).get("providers", [])
        if isinstance(provider, dict) and provider.get("enabled") is True
    ]
    tmdb = next((provider for provider in providers if provider.get("type") == "tmdb"), None)
    if tmdb is None:
        checks.append(_check("tmdb", "TMDB 元数据", "BLOCKED", "未启用 TMDB", "scraping"))
    else:
        ok, message = (provider_probe or _default_provider_probe)(tmdb)
        checks.append(_check(
            "tmdb", "TMDB 元数据", "PASS" if ok else "BLOCKED", message, "scraping"
        ))

    if conn is not None:
        try:
            import json

            from media_importer.features.scraping.dimension_mapping_engine import (
                MappingValidationError,
                validate_mapping,
            )
            from media_importer.infrastructure.db import get_enabled_dimensions

            mapping_errors = []
            provider_types = {item.get("type") for item in providers}
            for dimension in get_enabled_dimensions(conn):
                if dimension.get("source_type") != "provider":
                    continue
                if dimension.get("name") == "media_type":
                    # Provider 搜索结果自带作品类型，不需要业务值映射表。
                    continue
                raw_mappings = dimension.get("provider_mappings") or {}
                if isinstance(raw_mappings, str):
                    raw_mappings = json.loads(raw_mappings or "{}")
                values = {
                    str(item.get("value"))
                    for item in (dimension.get("value_list") or [])
                    if isinstance(item, dict) and item.get("value") is not None
                }
                usable = False
                for provider_type, mapping in (raw_mappings or {}).items():
                    if provider_type not in provider_types:
                        continue
                    try:
                        validate_mapping(mapping, values)
                        usable = True
                    except MappingValidationError as exc:
                        mapping_errors.append(
                            f"{dimension.get('label', dimension.get('name'))}: {exc}"
                        )
                if not usable:
                    mapping_errors.append(
                        f"{dimension.get('label', dimension.get('name'))}没有可用的 Provider 映射"
                    )
            checks.append(_check(
                "dimension_mappings", "维度映射",
                "BLOCKED" if mapping_errors else "PASS",
                mapping_errors[0] if mapping_errors else "已启用维度的 Provider 映射均有效",
                "advanced",
            ))
        except (TypeError, ValueError) as exc:
            checks.append(_check(
                "dimension_mappings", "维度映射", "BLOCKED",
                f"维度映射无法读取: {exc}", "advanced",
            ))

    legacy_restricted_rules = []
    for index, rule in enumerate(config.get("path_rules", []) or []):
        conditions = rule.get("conditions", {}) if isinstance(rule, dict) else {}
        raw_value = str(conditions.get("restricted_level", "") or "")
        if "17+" in raw_value.split("|"):
            legacy_restricted_rules.append(
                str(rule.get("name", "") or f"第 {index + 1} 条规则")
            )
    if legacy_restricted_rules:
        checks.append(_check(
            "viewing_rating_rules", "旧限制级规则", "WARN",
            f"{len(legacy_restricted_rules)} 条规则仍使用‘17+’；它现在只表示限制观看，不等于成人内容，请按实际片库用途复核",
            "rules",
        ))

    policy = config.get("source_policy", {}) or {}
    cleaner = config.get("source_cleaner", {}) or {}
    llm_required = (
        policy.get("mode") == "preserve_media"
        and cleaner.get("enabled") is True
        and cleaner.get("ai_enabled") is True
    )
    if not llm_required:
        checks.append(_check("llm", "LLM 辅助清理", "SKIPPED", "当前源处理模式不需要 LLM"))
    else:
        llm = config.get("llm", {}) or {}
        missing = [name for name in ("base_url", "api_key", "model") if not llm.get(name)]
        if missing:
            checks.append(_check(
                "llm", "LLM 辅助清理", "BLOCKED", "LLM 配置不完整", "source.llm"
            ))
        else:
            ok, message = (llm_probe or _default_llm_probe)(llm)
            checks.append(_check(
                "llm", "LLM 辅助清理", "PASS" if ok else "BLOCKED", message, "source.llm"
            ))

    watcher = config.get("file_watcher", {}) or {}
    automation_reasons = automatic_blocking_reasons(storage)
    if watcher.get("enabled") and not storage.get("automatic_allowed", False):
        checks.append(_check(
            "automation", "自动运行", "BLOCKED",
            automation_reasons[0] if automation_reasons else "存储未就绪，自动运行不能启动",
            "storage",
        ))
    elif watcher.get("enabled") and watcher_running is False:
        checks.append(_check(
            "automation", "自动运行", "BLOCKED",
            "设置已保存，但 fnOS 后台监控没有运行", "automation",
        ))
    elif watcher.get("enabled") and watcher_running is True:
        checks.append(_check("automation", "自动运行", "PASS", "fnOS 后台监控正在运行"))
    elif watcher.get("enabled"):
        checks.append(_check("automation", "自动运行", "PASS", "自动扫描配置允许启动"))
    else:
        checks.append(_check(
            "automation", "自动运行", "WARN", "自动扫描未开启，可先手动运行", "automation"
        ))

    state = "BLOCKED" if any(item["status"] == "BLOCKED" for item in checks) else "PASS"
    return {
        "state": state,
        "revision": config_revision(config),
        "checks": checks,
        "storage": storage,
    }
