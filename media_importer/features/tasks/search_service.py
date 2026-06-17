"""Provider 候选搜索服务 — 从 task_handlers 抽取，遵循 handler 不承载业务策略规范。"""

from typing import Any, Dict, List, Optional


def search_provider_candidates(
    config: dict,
    query: str,
    year: Optional[str] = None,
    media_type: Optional[str] = None,
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

    providers = create_providers(config)
    candidates: List[Dict[str, Any]] = []
    seen: set = set()

    for provider in providers:
        try:
            result = provider.search(query, year=year, media_type=media_type or None)
            if not result or not result.items:
                continue
            for item in result.items[:5]:
                dedup_key = f"{item.item_id}@{provider.provider_type}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                overview = getattr(item, "overview", "")
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
        except Exception:
            continue

    return candidates
