import logging
import time
from typing import Any, Dict, List, Optional, Set

from media_importer.core.db import get_enabled_dimensions

from .confidence_engine import CleanResult
from .llm_scraper import LLMScrapeError


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SCRAPE_MODES = {"provider_first", "ai_only"}


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


def _apply_confidence_result(result: dict, confidence_result) -> None:
    result["confidence"] = confidence_result.final_confidence
    result["scrape_trace"] = confidence_result.scrape_trace
    result["confidence_gate_blocked"] = confidence_result.gate_blocked
    result["confidence_search"] = confidence_result.search_conf
    result["confidence_data_gate"] = confidence_result.data_gate
    result["confidence_detail"] = confidence_result.confidence_detail


# ---------------------------------------------------------------------------
# Minimal result builder
# ---------------------------------------------------------------------------

def _build_minimal_result(clean_result, confidence_engine, enabled_dims_set=None,
                          provider_fallback_reasons=None, ai_clean_result=None,
                          scrape_mode="provider_first", ai_invoke_reason=None):
    """Build a minimal result dict when no provider match and no AI available."""
    result = {
        "title": clean_result.clean_title,
        "year": clean_result.year,
        "season": clean_result.season,
        "episode": None,
        "media_type": "movie",
        "confidence": 0,
        "provider_type": "",
        "provider_id": "",
        "scrape_trace": {},
        "confidence_gate_blocked": False,
        "confidence_search": 0,
        "confidence_data_gate": 0,
    }
    confidence_result = confidence_engine.calculate_ai_only(
        scrape_result=result,
        clean_result=clean_result,
        llm_raw_confidence=None,
        enabled_dims=enabled_dims_set,
        ai_clean_result=ai_clean_result,
        provider_fallback_reasons=provider_fallback_reasons,
    )
    _apply_confidence_result(result, confidence_result)
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
    confidence_result = scraper.confidence_engine.calculate(
        scrape_result=result,
        provider_search_info=search_info,
        clean_result=clean_result,
        ai_clean_result=ai_clean_result,
        match_result=match_result,
        llm_raw_confidence=None,
        enabled_dims=enabled_dims_set,
    )
    _apply_confidence_result(result, confidence_result)
    log.info(f"[metadata_scraper] done (provider_only): total={time.time()-t_start:.1f}s")
    return result


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

def scrape_metadata(scraper, video_filename: str, subtitle_filenames: List[str] = None,
                    conn=None, force_mode: Optional[str] = None) -> Dict[str, Any]:
    """Dispatch to the appropriate scrape mode handler."""
    log = logging.getLogger(__name__)
    if subtitle_filenames is None:
        subtitle_filenames = []

    if force_mode is not None and force_mode in VALID_SCRAPE_MODES:
        scrape_mode = force_mode
    else:
        scrape_mode = getattr(scraper.view.metadata, "scrape_mode", "provider_first")
        if scrape_mode not in VALID_SCRAPE_MODES:
            scrape_mode = "provider_first"

    ai_available = bool(scraper.llm_scraper.enabled)

    if force_mode is not None and scrape_mode == "ai_only" and not ai_available:
        log.warning(f"[metadata_scraper] force_mode={scrape_mode} but AI not configured")
        return {
            "error": "AI 刮削未配置，请在 AI 配置页中启用并填写 API Key、接口地址和模型ID",
            "title": "",
            "year": None,
            "media_type": "movie",
            "confidence": 0,
            "provider_type": "",
            "provider_id": "",
            "scrape_trace": {
                "scrape_mode": scrape_mode,
                "ai_invoked": False,
                "ai_invoke_reason": "AI未配置",
                "search_enhanced": False,
            },
        }

    if scrape_mode == "ai_only" and not ai_available:
        log.warning(
            f"[metadata_scraper] scrape_mode={scrape_mode} but AI not configured, "
            f"falling back to provider_first"
        )
        result = _scrape_provider_first(scraper, video_filename, subtitle_filenames, conn)
        _inject_trace_fields(result, scrape_mode, ai_invoked=False,
                             ai_invoke_reason="AI未配置-已降级为provider_first")
        return result

    if scrape_mode == "ai_only":
        return _scrape_ai_only(scraper, video_filename, subtitle_filenames, conn)
    else:
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

    match_threshold = scraper.confidence_engine._config.get("provider_match_threshold", 0.85)
    ai_research_threshold = scraper.confidence_engine._config.get("confirm_threshold", 0.5)
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
            if cjk_match.T < match_threshold:
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
            min_threshold=ai_research_threshold if ai_clean_result else None
        )

    # --- Step 3: If low match, try AI clean + re-search ---
    if provider_search_result:
        _, _, _, match_result, _ = provider_search_result
        if match_result.T < match_threshold and ai_available and not ai_clean_result:
            ai_clean_result = _do_ai_clean(scraper, video_filename, log, t_start)
            if ai_clean_result:
                search_year_2 = ai_clean_result.year if ai_clean_result.year is not None else clean_result.year
                provider_search_result_2, statuses_2 = scraper._search_all_providers(
                    ai_clean_result.clean_title, search_year_2, clean_result.season,
                    min_threshold=ai_research_threshold
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
                min_threshold=ai_research_threshold
            )

    # --- Step 4: Process provider result ---
    if provider_search_result:
        provider, search_item, media_type, match_result, search_info = provider_search_result

        # Get details
        try:
            details = provider.get_details(search_item.item_id, media_type)
        except Exception as e:
            log.warning(f"[metadata_scraper] provider_details failed: {e}")
            # Fallback to AI
            if ai_available:
                return _do_ai_fallback(
                    scraper, video_filename, subtitle_filenames, conn,
                    clean_result, ai_clean_result, enabled_dims_set,
                    "provider_first",
                    provider_fallback_reasons=[{
                        "provider_type": provider.provider_type,
                        "display_name": provider.display_name,
                        "status": "details_error",
                        "reason": f"{provider.display_name} 详情获取失败: {str(e)[:100]}",
                        "best_T": match_result.T,
                    }],
                    ai_invoke_reason="Provider详情失败",
                    log=log, t_start=t_start,
                )
            else:
                return _build_minimal_result(
                    clean_result, scraper.confidence_engine, enabled_dims_set,
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
                "confidence": 1.0,
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
            except LLMScrapeError:
                log.warning("[metadata_scraper] scrape_with_context failed, fallback to scrape")
                try:
                    result = scraper.llm_scraper.scrape(video_filename, subtitle_filenames, conn=conn)
                except LLMScrapeError as llm_err:
                    log.warning(f"[metadata_scraper] scrape fallback also failed: {llm_err}")
                    result = {}

            llm_raw_confidence = result.get("confidence", None)
            confidence_result = scraper.confidence_engine.calculate(
                scrape_result=result,
                provider_search_info=search_info,
                clean_result=clean_result,
                ai_clean_result=ai_clean_result,
                match_result=match_result,
                llm_raw_confidence=llm_raw_confidence,
                enabled_dims=enabled_dims_set,
            )
            _apply_confidence_result(result, confidence_result)
            result["provider_type"] = provider.provider_type
            result["provider_id"] = search_item.item_id
            result["poster_url"] = getattr(details, "poster_url", "") or ""
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
            _inject_trace_fields(result, "provider_first", ai_invoked=False,
                                 ai_invoke_reason=None)
            return result

    # --- No provider result: fallback to pure AI ---
    if ai_available:
        log.info(f"[metadata_scraper] no provider, ai_only fallback ({time.time()-t_start:.1f}s)")
        try:
            result = scraper.llm_scraper.scrape(video_filename, subtitle_filenames, conn=conn)
        except LLMScrapeError as e:
            log.warning(f"[metadata_scraper] ai_only fallback failed: {e}")
            result = _build_minimal_result(
                clean_result, scraper.confidence_engine, enabled_dims_set,
                provider_fallback_reasons=last_provider_statuses if last_provider_statuses else None,
                ai_clean_result=ai_clean_result,
                scrape_mode="provider_first",
                ai_invoke_reason="Provider无结果",
            )
            return result

        llm_raw_confidence = result.get("confidence", None)
        confidence_result = scraper.confidence_engine.calculate_ai_only(
            scrape_result=result,
            clean_result=clean_result,
            llm_raw_confidence=llm_raw_confidence,
            enabled_dims=enabled_dims_set,
            ai_clean_result=ai_clean_result,
            provider_fallback_reasons=last_provider_statuses if last_provider_statuses else None,
        )
        _apply_confidence_result(result, confidence_result)
        result["provider_type"] = ""
        result["provider_id"] = ""
        _inject_trace_fields(result, "provider_first", ai_invoked=True,
                             ai_invoke_reason="Provider无结果")
        log.info(f"[metadata_scraper] done (ai_fallback): total={time.time()-t_start:.1f}s")
        return result
    else:
        log.info(f"[metadata_scraper] no provider and AI not enabled ({time.time()-t_start:.1f}s)")
        return _build_minimal_result(
            clean_result, scraper.confidence_engine, enabled_dims_set,
            provider_fallback_reasons=last_provider_statuses if last_provider_statuses else None,
            ai_clean_result=ai_clean_result,
            scrape_mode="provider_first",
            ai_invoke_reason=None,
        )


def _do_ai_fallback(scraper, video_filename, subtitle_filenames, conn,
                    clean_result, ai_clean_result, enabled_dims_set,
                    scrape_mode, provider_fallback_reasons, ai_invoke_reason,
                    log, t_start):
    """Pure AI fallback used by provider_first when provider details fail."""
    try:
        result = scraper.llm_scraper.scrape(video_filename, subtitle_filenames, conn=conn)
    except LLMScrapeError as llm_err:
        log.warning(f"[metadata_scraper] ai_only fallback also failed: {llm_err}")
        return _build_minimal_result(
            clean_result, scraper.confidence_engine, enabled_dims_set,
            provider_fallback_reasons=provider_fallback_reasons,
            ai_clean_result=ai_clean_result,
            scrape_mode=scrape_mode,
            ai_invoke_reason=ai_invoke_reason,
        )

    llm_raw_confidence = result.get("confidence", None)
    confidence_result = scraper.confidence_engine.calculate_ai_only(
        scrape_result=result,
        clean_result=clean_result,
        llm_raw_confidence=llm_raw_confidence,
        enabled_dims=enabled_dims_set,
        ai_clean_result=ai_clean_result,
        provider_fallback_reasons=provider_fallback_reasons,
    )
    _apply_confidence_result(result, confidence_result)
    result["provider_type"] = ""
    result["provider_id"] = ""
    _inject_trace_fields(result, scrape_mode, ai_invoked=True,
                         ai_invoke_reason=ai_invoke_reason)
    return result


# ---------------------------------------------------------------------------
# Mode: ai_only
# ---------------------------------------------------------------------------

def _scrape_ai_only(scraper, video_filename: str, subtitle_filenames: List[str],
                    conn) -> Dict[str, Any]:
    """AI-only mode: skip Provider entirely, use LLM for everything."""
    log = logging.getLogger(__name__)
    enabled_dims_set = _get_enabled_dims(conn)
    t_start = time.time()

    clean_result = scraper._cleaner.clean(video_filename)
    ai_clean_result = None
    log.info(
        "[metadata_scraper] (ai_only) regex_clean: "
        f"title={clean_result.clean_title}, year={clean_result.year}, "
        f"season={clean_result.season}, year_suspect={clean_result.year_suspect}"
    )

    # AI clean if year_suspect
    if clean_result.year_suspect and scraper.llm_scraper.enabled:
        ai_clean_result = _do_ai_clean(scraper, video_filename, log, t_start)

    # Note: AI availability is guaranteed at this point because the dispatcher
    # `scrape_metadata()` falls back to provider_first when AI is not configured.
    log.info(f"[metadata_scraper] (ai_only) scrape start ({time.time()-t_start:.1f}s)")
    try:
        result = scraper.llm_scraper.scrape(video_filename, subtitle_filenames, conn=conn)
    except LLMScrapeError as e:
        log.warning(f"[metadata_scraper] (ai_only) scrape failed: {e}")
        return _build_minimal_result(
            clean_result, scraper.confidence_engine, enabled_dims_set,
            ai_clean_result=ai_clean_result,
            scrape_mode="ai_only",
            ai_invoke_reason=None,
        )

    llm_raw_confidence = result.get("confidence", None)
    confidence_result = scraper.confidence_engine.calculate_ai_only(
        scrape_result=result,
        clean_result=clean_result,
        llm_raw_confidence=llm_raw_confidence,
        enabled_dims=enabled_dims_set,
        ai_clean_result=ai_clean_result,
    )
    _apply_confidence_result(result, confidence_result)
    result["provider_type"] = ""
    result["provider_id"] = ""
    _inject_trace_fields(result, "ai_only", ai_invoked=True,
                         ai_invoke_reason="标题清洗" if ai_clean_result else "纯AI刮削")
    log.info(f"[metadata_scraper] (ai_only) done: total={time.time()-t_start:.1f}s")
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

    if scrape_mode == "ai_only" and not ai_available:
        log.warning(
            f"[metadata_scraper] series scrape_mode={scrape_mode} but AI not configured, "
            f"falling back to provider_first"
        )
        scrape_mode = "provider_first"

    # ai_only: skip provider entirely (only reached when AI is available)
    if scrape_mode == "ai_only":
        try:
            result = scraper.llm_scraper.scrape_series(series_name)
            _inject_trace_fields(result, "ai_only", ai_invoked=True,
                                 ai_invoke_reason="纯AI刮削")
            return result
        except LLMScrapeError as e:
            log.warning(f"[metadata_scraper] series ai_only failed: {e}")
        return {
            "title": series_name,
            "media_type": "tv",
            "provider_type": "",
            "provider_id": "",
            "confidence": 0,
            "scrape_trace": {"scrape_mode": "ai_only", "ai_invoked": False, "ai_invoke_reason": None},
        }

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
                        "confidence": 0.5,
                        "scrape_trace": {"scrape_mode": "provider_first", "ai_invoked": False, "ai_invoke_reason": None},
                    }
                    return result
        except Exception:
            pass

    # No provider result
    if ai_available:
        try:
            result = scraper.llm_scraper.scrape_series(series_name)
            _inject_trace_fields(result, scrape_mode, ai_invoked=True,
                                 ai_invoke_reason="Provider无结果")
            return result
        except LLMScrapeError as e:
            log.warning(f"[metadata_scraper] series ai_only failed: {e}")
    else:
        log.info("[metadata_scraper] no provider for series and AI not enabled")

    return {
        "title": series_name,
        "media_type": "tv",
        "provider_type": "",
        "provider_id": "",
        "confidence": 0,
        "scrape_trace": {"scrape_mode": scrape_mode, "ai_invoked": False, "ai_invoke_reason": None},
    }
