"""Provider 候选搜索与手动选择服务。"""

import copy
from typing import Any, Dict, List, Optional

MANUAL_SEARCH_LANGUAGES = {"zh-CN", "en-US", "ja-JP", "ko-KR"}
MANUAL_SEARCH_MEDIA_TYPES = {"movie", "tv"}


def _provider_config(
    config: dict,
    provider_type: str,
    language: Optional[str] = None,
) -> dict:
    providers = ((config or {}).get("metadata", {}) or {}).get("providers", []) or []
    for raw in providers:
        if raw.get("type") != provider_type or raw.get("enabled") is not True:
            continue
        selected = copy.deepcopy(raw)
        if language in MANUAL_SEARCH_LANGUAGES:
            selected["language"] = language
        return selected
    return {}


def _config_with_language(config: dict, language: Optional[str]) -> dict:
    if language not in MANUAL_SEARCH_LANGUAGES:
        return config
    adjusted = copy.deepcopy(config or {})
    for provider in ((adjusted.get("metadata", {}) or {}).get("providers", []) or []):
        if provider.get("enabled") is True:
            provider["language"] = language
    return adjusted


def search_provider_candidates(
    config: dict,
    query: str,
    year: Optional[str] = None,
    media_type: Optional[str] = None,
    language: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """搜索 Provider 候选列表，去重后返回统一结构。

    Args:
        config: 全局配置字典。
        query: 搜索关键词（必填）。
        year: 年份过滤（可选）。
        media_type: 媒体类型过滤（可选）。

    Returns:
        候选列表，每项包含 id/title/original_title/year/media_type/
        overview/provider_type/poster_url/vote_average。
    """
    from media_importer.features.providers import create_providers

    safe_limit = min(20, max(1, int(limit or 20)))
    normalized_media_type = media_type if media_type in MANUAL_SEARCH_MEDIA_TYPES else None
    providers = create_providers(_config_with_language(config, language))
    candidates: List[Dict[str, Any]] = []
    seen: set = set()

    for provider in providers:
        try:
            result = provider.search(query, year=year, media_type=normalized_media_type)
            if not result or not result.items:
                continue
            for item in result.items:
                dedup_key = f"{item.item_id}@{provider.provider_type}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                overview = getattr(item, "overview", "") or (
                    getattr(item, "raw_data", {}) or {}
                ).get("overview", "")
                if isinstance(overview, str) and len(overview) > 200:
                    overview = overview[:200] + "..."
                candidates.append({
                    "id": item.item_id,
                    "title": item.title,
                    "original_title": getattr(item, "original_title", "") or item.title,
                    "year": item.year,
                    "media_type": item.media_type,
                    "overview": overview,
                    "provider_type": provider.provider_type,
                    "poster_url": getattr(item, "poster_url", ""),
                    "vote_average": getattr(item, "vote_average", 0),
                })
                if len(candidates) >= safe_limit:
                    return candidates
        except Exception:
            continue

    return candidates


def load_provider_candidate(
    config: dict,
    conn,
    *,
    provider_type: str,
    item_id: str,
    media_type: str,
    language: Optional[str] = None,
) -> Dict[str, Any]:
    """按 Provider ID 获取完整资料和维度；不接触任务或文件。"""

    if not item_id:
        raise ValueError("缺少 Provider 条目 ID")
    if media_type not in MANUAL_SEARCH_MEDIA_TYPES:
        raise ValueError("作品类型必须是电影或剧集")
    if language and language not in MANUAL_SEARCH_LANGUAGES:
        raise ValueError("不支持的结果语言")

    from media_importer.features.providers import get_provider_class
    from media_importer.features.scraping.dimension_manager import (
        get_dimensions_for_provider,
    )
    from media_importer.infrastructure.db import get_enabled_dimensions

    provider_class = get_provider_class(provider_type)
    provider_config = _provider_config(config, provider_type, language)
    if not provider_class or not provider_config:
        raise ValueError(f"Provider '{provider_type}' 未启用或配置不存在")

    provider = provider_class(provider_config)
    details = provider.get_details(str(item_id), media_type)
    dim_configs = get_dimensions_for_provider(conn, provider_type)
    mappings = provider.map_dimensions(dim_configs, details)
    enabled_names = {item["name"] for item in get_enabled_dimensions(conn)}
    dimensions = {
        mapping.name: mapping.value
        for mapping in mappings
        if mapping.name in enabled_names and mapping.value not in (None, "", [])
    }
    dimensions["media_type"] = media_type
    dim_sources = {
        name: f"provider:{provider_type}"
        for name in dimensions
    }
    mapping_evidence = {
        mapping.name: mapping.evidence
        for mapping in mappings
        if mapping.name in enabled_names and mapping.evidence
    }
    return {
        "provider_type": provider_type,
        "provider_id": str(item_id),
        "language": language or provider_config.get("language", ""),
        "dimensions": dimensions,
        "dim_sources": dim_sources,
        "scrape_result": {
            "title_cn": details.title,
            "title_en": details.original_title,
            "year": details.year,
            "media_type": details.media_type,
            "overview": details.overview,
            "genres": [genre.name for genre in details.genres if genre.name],
            "poster_url": details.poster_url,
            "vote_average": details.vote_average,
            "origin_country": details.origin_country,
            "original_language": details.original_language,
            "adult": details.adult,
            "tagline": details.tagline,
            "provider_type": provider_type,
            "provider_id": str(item_id),
            "provider_dimensions": dimensions,
            "dimensions": dimensions,
            "match_level": "NEEDS_CONFIRM",
            "match_concerns": [],
            "manual_selected": True,
            "scrape_trace": {
                "dimension_mapping_evidence": mapping_evidence,
            },
        },
    }


__all__ = [
    "MANUAL_SEARCH_LANGUAGES",
    "MANUAL_SEARCH_MEDIA_TYPES",
    "load_provider_candidate",
    "search_provider_candidates",
]
