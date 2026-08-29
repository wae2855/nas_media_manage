"""正式运行前的统一只读开场检查。"""

from __future__ import annotations

from collections.abc import Callable

from .application_service import config_revision
from .library_paths import LibraryPathError, canonicalize_library_config
from .storage_readiness import inspect_storage_readiness

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


def inspect_startup_readiness(config: dict, *, provider_probe: Probe | None = None,
                              llm_probe: Probe | None = None) -> dict:
    config = config or {}
    checks = []
    storage = inspect_storage_readiness(config)
    storage_ok = storage.get("state") == "READY"
    checks.append(_check(
        "storage", "目录与磁盘", "PASS" if storage_ok else "BLOCKED",
        "目录存在、权限和磁盘空间均正常" if storage_ok else "存在不可用目录、权限或空间问题",
        "storage",
    ))

    try:
        canonical = canonicalize_library_config(config)
        if not canonical.get("library_root"):
            raise LibraryPathError("片库根目录未配置")
    except LibraryPathError as exc:
        checks.append(_check(
            "library", "片库边界", "BLOCKED", str(exc), "rules"
        ))
    else:
        checks.append(_check(
            "library", "片库边界", "PASS", "全部规则均位于片库根目录内"
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
    if watcher.get("enabled") and not storage_ok:
        checks.append(_check(
            "automation", "自动运行", "BLOCKED", "存储未就绪，自动运行不能启动", "automation"
        ))
    elif watcher.get("enabled"):
        checks.append(_check("automation", "自动运行", "PASS", "自动扫描已配置"))
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
