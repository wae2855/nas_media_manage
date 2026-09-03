import logging
import time
from typing import Any, Dict, List, Optional, Set

from media_importer.features.providers.base import SearchItem
from media_importer.infrastructure.db import get_enabled_dimensions

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SCRAPE_MODES = {"provider_first"}


# ---------------------------------------------------------------------------
# Dimension completeness check
# ---------------------------------------------------------------------------

def _check_dimension_completeness(provider_dimensions: dict, enabled_dims: set) -> dict:
    """Check whether Provider-mapped dimensions cover all enabled dimensions.

    A dimension is considered "covered" only when its value is not None.
    Provider mappings that return ``value=None`` are treated as missing
    because the Provider could not determine the value.

    Returns:
        dict with keys:
            complete (bool)        – True if all enabled dims have non-None values
            missing_dims (set)     – dim names where value is None or absent
            provider_covered (set) – dim names where Provider gave a non-None value
    """
    provider_covered: Set[str] = set()
    missing_dims: Set[str] = set()

    for dim_name in enabled_dims:
        dim_info = provider_dimensions.get(dim_name)
        if dim_info and dim_info.get("value") is not None:
            provider_covered.add(dim_name)
        else:
            missing_dims.add(dim_name)

    return {
        "complete": len(missing_dims) == 0,
        "missing_dims": missing_dims,
        "provider_covered": provider_covered,
    }


# ---------------------------------------------------------------------------
# Trace helpers
# ---------------------------------------------------------------------------


def _build_minimal_result(clean_result, enabled_dims_set=None,
                          provider_fallback_reasons=None,
                          scrape_mode="provider_first", ai_invoke_reason=None):
    """Build a minimal result dict when no provider match.

    match_level 由 MatchEngine 决定。
    """
    title = clean_result.clean_title or ""
    media_type = "tv" if clean_result.season else "movie"
    result = {
        "title": title,
        "title_cn": title,
        "title_en": "",
        "year": clean_result.year,
        "season": clean_result.season,
        "episode": clean_result.episode,
        "media_type": media_type,
        "provider_type": "",
        "provider_id": "",
        "dimensions": {"media_type": media_type},
        "clean_result": {
            "clean_title": clean_result.clean_title,
            "year": clean_result.year,
            "season": getattr(clean_result, "season", None),
            "episode": getattr(clean_result, "episode", None),
            "removed_items": getattr(clean_result, "removed_items", []) or [],
            "method": getattr(clean_result, "method", "structured"),
            "title_candidates": getattr(clean_result, "title_candidates", []) or [],
            "release_identity": getattr(clean_result, "release_identity", {}) or {},
        },
        "scrape_trace": {},
    }
    if provider_fallback_reasons:
        result["scrape_trace"]["provider_fallback_reasons"] = provider_fallback_reasons
    return result


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _get_enabled_dims(conn) -> Optional[Set[str]]:
    """Safely retrieve enabled dimension names from DB."""
    if not conn:
        return None
    try:
        return {d["name"] for d in get_enabled_dimensions(conn)}
    except Exception:
        return None


# CJK 匹配等级差（年份不符/模糊/无结果）→ 回退英文标题再搜一轮
_TRIGGER_ENG_FALLBACK_LEVELS = {"L4", "L6", "L7"}


def _apply_dimension_defaults(provider_dimensions: dict, conn) -> None:
    """ADR-0010 B 方案：值为 None 的维度应用 DB 配置的 default_value（就地修改）。

    未配置默认值的维度保持 None → completeness 判定不完整 → 任务进 NEEDS_CONFIRM
    人工确认（A 方案兜底）。应用默认值时标记 source=default 供前端展示。
    """
    if not conn:
        return
    try:
        from media_importer.infrastructure.db import get_all_dimensions
        dim_rows = get_all_dimensions(conn)
    except Exception:
        return
    defaults = {
        d["name"]: (d.get("default_value") or "").strip()
        for d in dim_rows
        if isinstance(d, dict)
    }
    for dim_name, dim_info in provider_dimensions.items():
        if not isinstance(dim_info, dict):
            continue
        if dim_info.get("value") is None:
            default_value = defaults.get(dim_name, "")
            if default_value:
                dim_info["value"] = default_value
                dim_info["source"] = "default"
                dim_info["source_reliability"] = 0.5



def _do_provider_search(scraper, title, year, season, log, t_start,
                        min_threshold=None):
    """Run provider search, returning (search_result, statuses)."""
    try:
        result, statuses = scraper._search_all_providers(
            title, year, season, min_threshold=min_threshold
        )
        log.info(
            f"[metadata_scraper] provider_search done: "
            f"found={result is not None} ({time.time()-t_start:.1f}s)"
        )
        return result, statuses
    except Exception as e:
        log.warning(f"[metadata_scraper] provider_search failed: {e}")
        return None, []


def _build_provider_only_result(scraper, details, search_item, media_type,
                                clean_result, provider_dimensions, search_info,
                                match_result, enabled_dims_set,
                                log, t_start):
    """Build result from Provider data only (no AI call).

    title_cn / title_en 必须写入，与 api/scrape_preview_job 保持一致，
    否则下游列存字段为空、命名模板退化为只剩年份。
    """
    result = {
        "title": details.title or search_item.title,
        "title_cn": details.title or search_item.title,
        "title_en": details.original_title or search_item.original_title,
        "original_title": details.original_title or search_item.original_title,
        "year": details.year or clean_result.year,
        "clean_result": {
            "clean_title": clean_result.clean_title,
            "year": clean_result.year,
            "season": getattr(clean_result, "season", None),
            "episode": getattr(clean_result, "episode", None),
            "removed_items": getattr(clean_result, "removed_items", []) or [],
            "method": getattr(clean_result, "method", "structured"),
            "title_candidates": getattr(clean_result, "title_candidates", []) or [],
            "release_identity": getattr(clean_result, "release_identity", {}) or {},
        },
        "season": clean_result.season,
        "episode": clean_result.episode,
        "media_type": media_type,
        "overview": details.overview or "",
        "genres": [g.name for g in details.genres if g.name],
        "vote_average": details.vote_average,
        "poster_url": getattr(details, "poster_url", "") or "",
    }
    if provider_dimensions:
        result["dimensions"] = {}
        for dim_name, dim_data in provider_dimensions.items():
            if dim_name not in result:
                result[dim_name] = dim_data.get("value")
            result["dimensions"][dim_name] = dim_data.get("value")
        mapping_evidence = {
            dim_name: dim_data.get("mapping_evidence")
            for dim_name, dim_data in provider_dimensions.items()
            if isinstance(dim_data, dict) and dim_data.get("mapping_evidence")
        }
        if mapping_evidence:
            result.setdefault("scrape_trace", {})[
                "dimension_mapping_evidence"
            ] = mapping_evidence
    log.info(f"[metadata_scraper] done (provider_only): total={time.time()-t_start:.1f}s")
    return result


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

def scrape_metadata(scraper, video_filename: str, subtitle_filenames: Optional[List[str]] = None,
                    conn=None, force_mode: Optional[str] = None, *, video_path: str = "",
                    match_result=None) -> Dict[str, Any]:
    """Provider-first 单模式刮削入口。"""
    if subtitle_filenames is None:
        subtitle_filenames = []

    if force_mode is not None and force_mode in VALID_SCRAPE_MODES:
        scrape_mode = force_mode
    else:
        scrape_mode = getattr(scraper.view.metadata, "scrape_mode", "provider_first")
        if scrape_mode not in VALID_SCRAPE_MODES:
            scrape_mode = "provider_first"

    return _scrape_provider_first(
        scraper,
        video_filename,
        subtitle_filenames,
        conn,
        video_path=video_path,
        match_result=match_result,
    )


# ---------------------------------------------------------------------------
# Mode: provider_first
# ---------------------------------------------------------------------------

def _scrape_provider_first(scraper, video_filename: str, subtitle_filenames: List[str],
                           conn, *, video_path: str = "", match_result=None) -> Dict[str, Any]:
    """Provider-first mode: TMDB 为权威数据源（ADR-0010：AI 刮削已移除）。

    流程：正则清洗 → CJK/英文两轮 Provider 搜索 → 命中则映射维度+完整性检查
    → 维度不完整时应用默认值（B）或留空进人工确认（A）；未命中返回最小结果。
    """
    log = logging.getLogger(__name__)
    enabled_dims_set = _get_enabled_dims(conn)
    t_start = time.time()

    clean_result = scraper._cleaner.clean(video_filename)
    identity_evidence = getattr(match_result, "identity_evidence", {}) or {}
    path_structure = identity_evidence.get("path_structure", {})
    path_season = path_structure.get("season")
    if clean_result.season is None and path_season is not None:
        clean_result.season = path_season
    log.info(
        "[metadata_scraper] regex_clean: "
        f"title={clean_result.clean_title}, year={clean_result.year}, "
        f"season={clean_result.season}, year_suspect={clean_result.year_suspect}"
    )

    last_provider_statuses = []
    provided_match_result = match_result

    # --- Step 1: use the unified match decision when the pipeline supplied it ---
    provider_search_result = None
    selected = getattr(match_result, "selected_candidate", None)
    if selected and selected.provider_id and selected.provider_type:
        provider = next(
            (
                item for item in scraper.providers
                if item.provider_type == selected.provider_type
            ),
            None,
        )
        if provider is not None:
            search_item = SearchItem(
                provider_type=selected.provider_type,
                item_id=str(selected.provider_id),
                title=selected.title,
                original_title=selected.title,
                year=selected.year,
                media_type=selected.media_type or (
                    "tv" if clean_result.season is not None else "movie"
                ),
                poster_url=None,
                vote_average=selected.score,
                raw_data={},
            )
            provider_search_result = (
                provider,
                search_item,
                search_item.media_type,
                None,
                {
                    "query": clean_result.clean_title,
                    "selected_title": selected.title,
                    "selected_year": selected.year,
                    "provider_type": selected.provider_type,
                    "selection_source": selected.why_selected,
                    "original_filename": video_filename,
                },
            )

    # Direct callers without a match decision keep the existing file-only path.
    if provider_search_result is None and clean_result.cjk_title and scraper.providers:
        provider_search_result, last_provider_statuses = scraper._search_all_providers(
            clean_result.cjk_title, clean_result.year, clean_result.season
        )
        if provider_search_result:
            _, _, _, cjk_match, _ = provider_search_result
            if cjk_match.level in _TRIGGER_ENG_FALLBACK_LEVELS:
                eng_result, eng_statuses = scraper._search_all_providers(
                    clean_result.clean_title, clean_result.year, clean_result.season
                )
                last_provider_statuses = eng_statuses
                if eng_result:
                    _, _, _, eng_match, _ = eng_result
                    if eng_match.T > cjk_match.T:
                        provider_search_result = eng_result
        else:
            provider_search_result, last_provider_statuses = scraper._search_all_providers(
                clean_result.clean_title, clean_result.year, clean_result.season
            )
    elif provider_search_result is None:
        provider_search_result, last_provider_statuses = scraper._search_all_providers(
            clean_result.clean_title, clean_result.year, clean_result.season,
        )

    # --- Step 2: Process provider result ---
    if provider_search_result:
        provider, search_item, media_type, match_result, search_info = provider_search_result

        try:
            details = provider.get_details(search_item.item_id, media_type)
        except Exception as e:
            log.warning(f"[metadata_scraper] provider_details failed: {e}")
            return _build_minimal_result(
                clean_result, enabled_dims_set,
                provider_fallback_reasons=[{
                    "provider_type": provider.provider_type,
                    "display_name": provider.display_name,
                    "status": "details_error",
                    "reason": f"{provider.display_name} 详情获取失败: {str(e)[:100]}",
                    "best_T": getattr(match_result, "T", 0.0),
                }],
                scrape_mode="provider_first",
            )

        search_info["original_filename"] = video_filename

        provider_dimensions = {
            "media_type": {
                "value": media_type,
                "source": provider.provider_type,
            }
        }
        if conn:
            provider_dimensions.update(scraper._map_provider_dimensions(provider, details, conn))

        # ADR-0010 B 方案：映射为空的维度应用可配置默认值（无默认值则留空进人工确认）
        _apply_dimension_defaults(provider_dimensions, conn)

        result = _build_provider_only_result(
            scraper, details, search_item, media_type,
            clean_result, provider_dimensions, search_info,
            match_result, enabled_dims_set,
            log, t_start,
        )
        result["provider_type"] = provider.provider_type
        result["provider_id"] = search_item.item_id
        result["poster_url"] = getattr(details, "poster_url", "") or ""
        result.setdefault("scrape_trace", {})["provider_dimensions"] = {
            k: v.get("source", provider.provider_type) if isinstance(v, dict) else provider.provider_type
            for k, v in provider_dimensions.items()
        }
        if provided_match_result is not None:
            result.setdefault("scrape_trace", {})["identity_evidence"] = (
                provided_match_result.to_dict().get("identity_evidence", {})
            )
        return result

    # --- No provider result: build minimal result ---
    result = _build_minimal_result(
        clean_result, enabled_dims_set,
        provider_fallback_reasons=last_provider_statuses if last_provider_statuses else None,
        scrape_mode="provider_first",
    )
    return result


# ---------------------------------------------------------------------------
# Series scraping
# ---------------------------------------------------------------------------

def scrape_series_metadata(scraper, series_name: str) -> Dict[str, Any]:
    scrape_mode = getattr(scraper.view.metadata, "scrape_mode", "provider_first")
    if scrape_mode not in VALID_SCRAPE_MODES:
        scrape_mode = "provider_first"

    # provider_first: try provider first（ADR-0010：AI 整剧刮削已移除）
    for provider in scraper.providers:
        try:
            search_result = provider.search(series_name, media_type="tv")
            if search_result.items:
                search_item = search_result.items[0]
                details = provider.get_details(search_item.item_id, "tv")
                return {
                    "title": details.get("name", series_name) if isinstance(details, dict) else getattr(details, "title", series_name),
                    "media_type": "tv",
                    "provider_type": provider.provider_type,
                    "provider_id": search_item.item_id,
                    "scrape_trace": {"scrape_mode": "provider_first"},
                }
        except Exception:
            pass

    # No provider result for series → return minimal result, do NOT call pure AI
    return {
        "title": series_name,
        "media_type": "tv",
        "provider_type": "",
        "provider_id": "",
        "scrape_trace": {"scrape_mode": scrape_mode},
    }
