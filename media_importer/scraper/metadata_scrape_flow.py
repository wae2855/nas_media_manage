import logging
import time
from typing import Any, Dict, List, Optional, Set

from media_importer.core.db import get_enabled_dimensions
from media_importer.features.scraping.confidence_models import CleanResult

from .llm_scraper import LLMScrapeError


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

def _inject_trace_fields(result: dict, scrape_mode: str,
                         ai_invoked: bool, ai_invoke_reason: Optional[str]) -> None:
    """Inject scrape-mode tracking fields into the scrape_trace dict."""
    trace = result.get("scrape_trace", {})
    trace["scrape_mode"] = scrape_mode
    trace["ai_invoked"] = ai_invoked
    trace["ai_invoke_reason"] = ai_invoke_reason
    if "search_enhanced" not in trace:
        trace["search_enhanced"] = result.get("search_enhanced", False)
    result["scrape_trace"] = trace


# match_level / match_concerns / match_trace / confirm_reason / dim_sources
# 由 MatchEngine 和 ReviewDecisionService 决定；本模块不再写入旧解释字段。
def _apply_confidence_result(result: dict, confiance_result) -> None:
    """兼容入口：新任务流程禁止调用。"""
    return


# ---------------------------------------------------------------------------
# Minimal result builder
# ---------------------------------------------------------------------------

def _build_minimal_result(clean_result, enabled_dims_set=None,
                          provider_fallback_reasons=None, ai_clean_result=None,
                          scrape_mode="provider_first", ai_invoke_reason=None):
    """Build a minimal result dict when no provider match and no AI available.

    match_level 由 MatchEngine 决定。
    """
    title = clean_result.clean_title or ""
    result = {
        "title": title,
        "title_cn": title,
        "title_en": "",
        "year": clean_result.year,
        "season": clean_result.season,
        "episode": clean_result.episode,
        "media_type": "tv" if clean_result.season else "movie",
        "provider_type": "ai",
        "provider_id": "",
        "scrape_trace": {},
    }
    if provider_fallback_reasons:
        result["scrape_trace"]["provider_fallback_reasons"] = provider_fallback_reasons
    _inject_trace_fields(result, scrape_mode, ai_invoked=False, ai_invoke_reason=ai_invoke_reason)
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


def _do_ai_clean(scraper, video_filename, log, t_start):
    """Run AI title cleaning, returning (ai_clean_result, elapsed_str) or (None, ...)."""
    try:
        log.info(f"[metadata_scraper] ai_clean start ({time.time()-t_start:.1f}s)")
        result = scraper._cleaner.ai_clean(video_filename, scraper.llm_scraper)
        log.info(
            f"[metadata_scraper] ai_clean done: title={result.clean_title}, "
            f"year={result.year} ({time.time()-t_start:.1f}s)"
        )
        return result
    except Exception as e:
        log.warning(f"[metadata_scraper] ai_clean failed: {e}")
        return None


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
                                match_result, ai_clean_result, enabled_dims_set,
                                log, t_start):
    """Build result from Provider data only (no AI call)."""
    result = {
        "title": details.title or search_item.title,
        "original_title": details.original_title or search_item.original_title,
        "year": details.year or clean_result.year,
        "season": clean_result.season,
        "episode": clean_result.episode,
        "media_type": media_type,
        "overview": details.overview or "",
        "genres": [g.name for g in details.genres if g.name],
        "vote_average": details.vote_average,
        "poster_url": getattr(details, "poster_url", "") or "",
    }
    if provider_dimensions:
        for dim_name, dim_data in provider_dimensions.items():
            if dim_name not in result:
                result[dim_name] = dim_data.get("value")
    log.info(f"[metadata_scraper] done (provider_only): total={time.time()-t_start:.1f}s")
    return result


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

def scrape_metadata(scraper, video_filename: str, subtitle_filenames: Optional[List[str]] = None,
                    conn=None, force_mode: Optional[str] = None) -> Dict[str, Any]:
    """Provider-first 单模式刮削入口。"""
    log = logging.getLogger(__name__)
    if subtitle_filenames is None:
        subtitle_filenames = []

    if force_mode is not None and force_mode in VALID_SCRAPE_MODES:
        scrape_mode = force_mode
    else:
        scrape_mode = getattr(scraper.view.metadata, "scrape_mode", "provider_first")
        if scrape_mode not in VALID_SCRAPE_MODES:
            scrape_mode = "provider_first"

    return _scrape_provider_first(scraper, video_filename, subtitle_filenames, conn)


# ---------------------------------------------------------------------------
# Mode: provider_first
# ---------------------------------------------------------------------------

def _scrape_provider_first(scraper, video_filename: str, subtitle_filenames: List[str],
                           conn) -> Dict[str, Any]:
    """Provider-first mode: use Provider as authority, AI only supplements missing dims."""
    log = logging.getLogger(__name__)
    ai_available = scraper.llm_scraper.enabled
    enabled_dims_set = _get_enabled_dims(conn)
    t_start = time.time()

    clean_result = scraper._cleaner.clean(video_filename)
    ai_clean_result = None
    log.info(
        "[metadata_scraper] regex_clean: "
        f"title={clean_result.clean_title}, year={clean_result.year}, "
        f"season={clean_result.season}, year_suspect={clean_result.year_suspect}"
    )

    # TitleMatcher 内部离散等级 L1-L7 决定是否触发 AI clean 重搜：
# - L1/L2/L3/L5：标题匹配良好，不触发 AI clean。
# - L4/L6/L7：标题明显不匹配（年份不同 / 模糊无年份 / 完全不匹配），
#   触发 AI 辅助清洗后重新搜索。
# 决策只参考 match_result.level。
    _TRIGGER_AI_CLEAN_LEVELS = {"L4", "L6", "L7"}
    last_provider_statuses = []

    # --- Step 1: AI clean if year_suspect ---
    if clean_result.year_suspect and ai_available:
        ai_clean_result = _do_ai_clean(scraper, video_filename, log, t_start)
    elif clean_result.year_suspect:
        log.info("[metadata_scraper] year_suspect=True but AI not enabled, skip ai_clean")

    search_title = ai_clean_result.clean_title if ai_clean_result else clean_result.clean_title
    search_year = ai_clean_result.year if ai_clean_result else clean_result.year

    # --- Step 2: Provider search ---
    if clean_result.cjk_title and scraper.providers:
        # CJK search first, then fallback to English
        provider_search_result, last_provider_statuses = scraper._search_all_providers(
            clean_result.cjk_title, clean_result.year, clean_result.season
        )
        if provider_search_result:
            _, _, _, cjk_match, _ = provider_search_result
            # 标题匹配明显不匹配（年份不同 / 模糊无年份 / 完全不匹配）→ 回退到英文再搜。
            if cjk_match.level in _TRIGGER_AI_CLEAN_LEVELS:
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
    else:
        provider_search_result, last_provider_statuses = scraper._search_all_providers(
            search_title, search_year, clean_result.season,
        )

    # --- Step 3: If low match, try AI clean + re-search ---
    if provider_search_result:
        _, _, _, match_result, _ = provider_search_result
        if match_result.level in _TRIGGER_AI_CLEAN_LEVELS and ai_available and not ai_clean_result:
            ai_clean_result = _do_ai_clean(scraper, video_filename, log, t_start)
            if ai_clean_result:
                search_year_2 = ai_clean_result.year if ai_clean_result.year is not None else clean_result.year
                provider_search_result_2, statuses_2 = scraper._search_all_providers(
                    ai_clean_result.clean_title, search_year_2, clean_result.season,
                )
                if provider_search_result_2:
                    _, _, _, match_result_2, _ = provider_search_result_2
                    if match_result_2.T > match_result.T:
                        provider_search_result = provider_search_result_2
                        last_provider_statuses = statuses_2
    elif not provider_search_result and ai_available and not ai_clean_result:
        # No provider result at all, try AI clean
        ai_clean_result = _do_ai_clean(scraper, video_filename, log, t_start)
        if ai_clean_result:
            search_year = ai_clean_result.year if ai_clean_result.year is not None else clean_result.year
            provider_search_result, last_provider_statuses = scraper._search_all_providers(
                ai_clean_result.clean_title, search_year, clean_result.season,
            )

    # --- Step 4: Process provider result ---
    if provider_search_result:
        provider, search_item, media_type, match_result, search_info = provider_search_result

        # Get details
        try:
            details = provider.get_details(search_item.item_id, media_type)
        except Exception as e:
            log.warning(f"[metadata_scraper] provider_details failed: {e}")
            # Provider 详情失败 → 构建最小结果，不调用纯 AI 兜底
            return _build_minimal_result(
                clean_result, enabled_dims_set,
                provider_fallback_reasons=[{
                    "provider_type": provider.provider_type,
                    "display_name": provider.display_name,
                    "status": "details_error",
                    "reason": f"{provider.display_name} 详情获取失败: {str(e)[:100]}",
                    "best_T": match_result.T,
                }],
                ai_clean_result=ai_clean_result,
                scrape_mode="provider_first",
                ai_invoke_reason="Provider详情失败",
            )

        search_info["original_filename"] = video_filename

        # Map provider dimensions
        provider_dimensions = {
            "media_type": {
                "value": media_type,
                "source": provider.provider_type,
            }
        }
        if conn:
            provider_dimensions.update(scraper._map_provider_dimensions(provider, details, conn))

        # --- Dimension completeness check (core logic) ---
        if enabled_dims_set is not None:
            completeness = _check_dimension_completeness(provider_dimensions, enabled_dims_set)
        else:
            # No dimension info available, treat as incomplete to be safe
            completeness = {"complete": False, "missing_dims": set(), "provider_covered": set()}

        if completeness["complete"] and not ai_available:
            # Provider data covers everything, no AI needed
            result = _build_provider_only_result(
                scraper, details, search_item, media_type,
                clean_result, provider_dimensions, search_info,
                match_result, ai_clean_result, enabled_dims_set,
                log, t_start,
            )
            result["provider_type"] = provider.provider_type
            result["provider_id"] = search_item.item_id
            result["poster_url"] = getattr(details, "poster_url", "") or ""
            _inject_trace_fields(result, "provider_first", ai_invoked=False, ai_invoke_reason=None)
            # 写入显式维度来源：provider 映射的维度键集合
            result.setdefault("scrape_trace", {})["provider_dimensions"] = {
                k: v.get("source", provider.provider_type) if isinstance(v, dict) else provider.provider_type
                for k, v in provider_dimensions.items()
            }
            return result

        if completeness["complete"]:
            # Provider data covers everything, AI available but not needed
            result = _build_provider_only_result(
                scraper, details, search_item, media_type,
                clean_result, provider_dimensions, search_info,
                match_result, ai_clean_result, enabled_dims_set,
                log, t_start,
            )
            result["provider_type"] = provider.provider_type
            result["provider_id"] = search_item.item_id
            result["poster_url"] = getattr(details, "poster_url", "") or ""
            _inject_trace_fields(result, "provider_first", ai_invoked=False, ai_invoke_reason=None)
            result.setdefault("scrape_trace", {})["provider_dimensions"] = {
                k: v.get("source", provider.provider_type) if isinstance(v, dict) else provider.provider_type
                for k, v in provider_dimensions.items()
            }
            return result

        # Dimensions incomplete — AI supplements missing dims only
        provider_context = scraper._extract_context(details, clean_result, provider)
        if ai_available:
            try:
                log.info(
                    f"[metadata_scraper] scrape_with_context (supplement dims) "
                    f"missing={completeness['missing_dims']} ({time.time()-t_start:.1f}s)"
                )
                result = scraper.llm_scraper.scrape_with_context(
                    video_filename, subtitle_filenames, provider_context,
                    provider_dimensions=provider_dimensions,
                    provider_name=provider.display_name, conn=conn,
                )
                # 记录 AI 辅助补全的维度键集合
                ai_dims = result.get("dimensions", {})
                if isinstance(ai_dims, dict):
                    provider_covered = completeness.get("provider_covered", set())
                    ai_assist_keys = {k for k in ai_dims if k not in provider_covered}
                    result.setdefault("scrape_trace", {})["ai_assist_dimensions"] = {
                        k: "ai_assist" for k in ai_assist_keys
                    }
                # 如果启用了联网搜索，记录 ai_search 维度
                if result.get("search_enhanced"):
                    result.setdefault("scrape_trace", {})["ai_search_dimensions"] = {
                        k: "ai_search" for k in completeness.get("missing_dims", set())
                        if k in ai_dims
                    }
            except LLMScrapeError:
                log.warning("[metadata_scraper] scrape_with_context failed, fallback to scrape")
                try:
                    result = scraper.llm_scraper.scrape(video_filename, subtitle_filenames, conn=conn)
                except LLMScrapeError as llm_err:
                    log.warning(f"[metadata_scraper] scrape fallback also failed: {llm_err}")
                    result = {}

            result["provider_type"] = provider.provider_type
            result["provider_id"] = search_item.item_id
            result["poster_url"] = getattr(details, "poster_url", "") or ""
            # 写入 provider 维度来源
            result.setdefault("scrape_trace", {})["provider_dimensions"] = {
                k: v.get("source", provider.provider_type) if isinstance(v, dict) else provider.provider_type
                for k, v in provider_dimensions.items()
            }
            _inject_trace_fields(result, "provider_first", ai_invoked=True,
                                 ai_invoke_reason="维度不完整")
            log.info(f"[metadata_scraper] done: total={time.time()-t_start:.1f}s")
            return result
        else:
            # No AI, use provider data as-is
            result = _build_provider_only_result(
                scraper, details, search_item, media_type,
                clean_result, provider_dimensions, search_info,
                match_result, ai_clean_result, enabled_dims_set,
                log, t_start,
            )
            result["provider_type"] = provider.provider_type
            result["provider_id"] = search_item.item_id
            result["poster_url"] = getattr(details, "poster_url", "") or ""
            result.setdefault("scrape_trace", {})["provider_dimensions"] = {
                k: v.get("source", provider.provider_type) if isinstance(v, dict) else provider.provider_type
                for k, v in provider_dimensions.items()
            }
            _inject_trace_fields(result, "provider_first", ai_invoked=False,
                                 ai_invoke_reason=None)
            return result

    # --- No provider result: build minimal result, do NOT fallback to pure AI ---
    result = _build_minimal_result(
        clean_result, enabled_dims_set,
        provider_fallback_reasons=last_provider_statuses if last_provider_statuses else None,
        ai_clean_result=ai_clean_result,
        scrape_mode="provider_first",
        ai_invoke_reason="Provider无结果",
    )
    _inject_trace_fields(result, "provider_first", ai_invoked=False,
                         ai_invoke_reason="Provider无结果")
    return result


# ---------------------------------------------------------------------------
# Series scraping
# ---------------------------------------------------------------------------

def scrape_series_metadata(scraper, series_name: str) -> Dict[str, Any]:
    log = logging.getLogger(__name__)
    scrape_mode = getattr(scraper.view.metadata, "scrape_mode", "provider_first")
    if scrape_mode not in VALID_SCRAPE_MODES:
        scrape_mode = "provider_first"

    ai_available = bool(scraper.llm_scraper.enabled)

    # provider_first: try provider first
    for provider in scraper.providers:
        try:
            search_result = provider.search(series_name, media_type="tv")
            if search_result.items:
                search_item = search_result.items[0]
                details = provider.get_details(search_item.item_id, "tv")
                clean_result = CleanResult(clean_title=series_name)
                provider_context = scraper._extract_context(details, clean_result, provider)

                if ai_available:
                    try:
                        result = scraper.llm_scraper.scrape_series_with_context(
                            series_name, provider_context, provider_name=provider.display_name
                        )
                        _inject_trace_fields(result, "provider_first", ai_invoked=True,
                                             ai_invoke_reason="维度不完整")
                        return result
                    except LLMScrapeError:
                        pass
                else:
                    log.info("[metadata_scraper] AI not enabled, return provider details for series")
                    result = {
                        "title": details.get("name", series_name) if isinstance(details, dict) else getattr(details, "title", series_name),
                        "media_type": "tv",
                        "provider_type": provider.provider_type,
                        "provider_id": search_item.item_id,
                        "scrape_trace": {"scrape_mode": "provider_first", "ai_invoked": False, "ai_invoke_reason": None},
                    }
                    return result
        except Exception:
            pass

    # No provider result for series → return minimal result, do NOT call pure AI
    return {
        "title": series_name,
        "media_type": "tv",
        "provider_type": "",
        "provider_id": "",
        "scrape_trace": {"scrape_mode": scrape_mode, "ai_invoked": False, "ai_invoke_reason": None},
    }
