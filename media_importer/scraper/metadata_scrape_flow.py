import logging
import time
from typing import Any, Dict, List

from media_importer.core.db import get_enabled_dimensions

from .confidence_engine import CleanResult
from .llm_scraper import LLMScrapeError


def scrape_metadata(scraper, video_filename: str, subtitle_filenames: List[str] = None,
                    conn=None) -> Dict[str, Any]:
    if subtitle_filenames is None:
        subtitle_filenames = []

    log = logging.getLogger(__name__)

    enabled_dims_set = None
    if conn:
        try:
            enabled_dims_set = {d["name"] for d in get_enabled_dimensions(conn)}
        except Exception:
            pass

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

    if clean_result.year_suspect:
        try:
            log.info(f"[metadata_scraper] year_suspect=True, ai_clean first ({time.time()-t_start:.1f}s)")
            ai_clean_result = scraper._cleaner.ai_clean(video_filename, scraper.llm_scraper)
            log.info(
                f"[metadata_scraper] ai_clean done: title={ai_clean_result.clean_title}, "
                f"year={ai_clean_result.year} ({time.time()-t_start:.1f}s)"
            )
            provider_search_result, last_provider_statuses = scraper._search_all_providers(
                ai_clean_result.clean_title, ai_clean_result.year, clean_result.season,
                min_threshold=ai_research_threshold
            )
            log.info(
                "[metadata_scraper] provider_search (post-ai-clean) done: "
                f"found={provider_search_result is not None} ({time.time()-t_start:.1f}s)"
            )
        except Exception as e:
            log.warning(f"[metadata_scraper] ai_clean + provider_search failed: {e}")
            provider_search_result = None
            last_provider_statuses = []
    else:
        if clean_result.cjk_title and scraper.providers:
            log.info(f"[metadata_scraper] provider_search_cjk start: query={clean_result.cjk_title}")
            provider_search_result, last_provider_statuses = scraper._search_all_providers(
                clean_result.cjk_title, clean_result.year, clean_result.season
            )
            log.info(
                "[metadata_scraper] provider_search_cjk done: "
                f"found={provider_search_result is not None} ({time.time()-t_start:.1f}s)"
            )

            if provider_search_result:
                _, _, _, cjk_match, _ = provider_search_result
                if cjk_match.T < match_threshold:
                    log.info(f"[metadata_scraper] cjk T={cjk_match.T:.3f} < threshold, eng search start")
                    eng_search_result, eng_provider_statuses = scraper._search_all_providers(
                        clean_result.clean_title, clean_result.year, clean_result.season
                    )
                    last_provider_statuses = eng_provider_statuses
                    if eng_search_result:
                        _, _, _, eng_match, _ = eng_search_result
                        if eng_match.T > cjk_match.T:
                            provider_search_result = eng_search_result
                            log.info(
                                "[metadata_scraper] eng search better: "
                                f"T={eng_match.T:.3f} > cjk T={cjk_match.T:.3f}"
                            )
            else:
                log.info(f"[metadata_scraper] cjk no result, eng search start: query={clean_result.clean_title}")
                provider_search_result, last_provider_statuses = scraper._search_all_providers(
                    clean_result.clean_title, clean_result.year, clean_result.season
                )
                log.info(
                    "[metadata_scraper] eng search done: "
                    f"found={provider_search_result is not None} ({time.time()-t_start:.1f}s)"
                )
        else:
            log.info(f"[metadata_scraper] provider_search_1 start: query={clean_result.clean_title}")
            provider_search_result, last_provider_statuses = scraper._search_all_providers(
                clean_result.clean_title, clean_result.year, clean_result.season
            )
            log.info(
                "[metadata_scraper] provider_search_1 done: "
                f"found={provider_search_result is not None} ({time.time()-t_start:.1f}s)"
            )

        if provider_search_result:
            _, _, _, match_result, _ = provider_search_result
            log.info(f"[metadata_scraper] match T={match_result.T:.3f}, threshold={match_threshold}")
            if match_result.T < match_threshold:
                try:
                    log.info(f"[metadata_scraper] ai_clean start ({time.time()-t_start:.1f}s)")
                    ai_clean_result = scraper._cleaner.ai_clean(video_filename, scraper.llm_scraper)
                    log.info(
                        f"[metadata_scraper] ai_clean done: title={ai_clean_result.clean_title}, "
                        f"year={ai_clean_result.year} ({time.time()-t_start:.1f}s)"
                    )
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
                            log.info(f"[metadata_scraper] provider_search_2 better: T={match_result_2.T:.3f}")
                except Exception as e:
                    log.warning(f"[metadata_scraper] ai_clean + provider_search_2 failed: {e}")
        else:
            try:
                log.info(f"[metadata_scraper] no provider result, ai_clean start ({time.time()-t_start:.1f}s)")
                ai_clean_result = scraper._cleaner.ai_clean(video_filename, scraper.llm_scraper)
                log.info(
                    f"[metadata_scraper] ai_clean done: title={ai_clean_result.clean_title}, "
                    f"year={ai_clean_result.year} ({time.time()-t_start:.1f}s)"
                )
                search_year = ai_clean_result.year if ai_clean_result.year is not None else clean_result.year
                provider_search_result, last_provider_statuses = scraper._search_all_providers(
                    ai_clean_result.clean_title, search_year, clean_result.season,
                    min_threshold=ai_research_threshold
                )
                log.info(
                    "[metadata_scraper] provider_search_2 done: "
                    f"found={provider_search_result is not None} ({time.time()-t_start:.1f}s)"
                )
            except Exception as e:
                log.warning(f"[metadata_scraper] ai_clean + provider_search failed: {e}")

    if provider_search_result:
        provider, search_item, media_type, match_result, search_info = provider_search_result
        try:
            log.info(
                "[metadata_scraper] get_details start: "
                f"id={search_item.item_id}, provider={provider.provider_type} ({time.time()-t_start:.1f}s)"
            )
            details = provider.get_details(search_item.item_id, media_type)
            log.info(f"[metadata_scraper] get_details done ({time.time()-t_start:.1f}s)")
        except Exception as e:
            log.warning(f"[metadata_scraper] provider_details failed, fallback to ai_only: {e}")
            details_fallback_reasons = [{
                "provider_type": provider.provider_type,
                "display_name": provider.display_name,
                "status": "details_error",
                "reason": f"{provider.display_name} 详情获取失败: {str(e)[:100]}",
                "best_T": match_result.T,
            }]
            result = scraper.llm_scraper.scrape(video_filename, subtitle_filenames, conn=conn)
            llm_raw_confidence = result.get("confidence", None)
            confidence_result = scraper.confidence_engine.calculate_ai_only(
                scrape_result=result,
                clean_result=clean_result,
                llm_raw_confidence=llm_raw_confidence,
                enabled_dims=enabled_dims_set,
                ai_clean_result=ai_clean_result,
                provider_fallback_reasons=details_fallback_reasons,
            )
            result["confidence"] = confidence_result.final_confidence
            result["scrape_trace"] = confidence_result.scrape_trace
            result["provider_type"] = ""
            result["provider_id"] = ""
            return result

        search_info["original_filename"] = video_filename

        provider_dimensions = {
            "media_type": {
                "value": media_type,
                "confidence": 1.0,
                "source": provider.provider_type,
            }
        }
        if conn:
            provider_dimensions.update(scraper._map_provider_dimensions(provider, details, conn))
        provider_context = scraper._extract_context(details, clean_result, provider)

        try:
            log.info(f"[metadata_scraper] scrape_with_context start ({time.time()-t_start:.1f}s)")
            result = scraper.llm_scraper.scrape_with_context(
                video_filename, subtitle_filenames, provider_context,
                provider_dimensions=provider_dimensions, provider_name=provider.display_name, conn=conn
            )
            log.info(f"[metadata_scraper] scrape_with_context done ({time.time()-t_start:.1f}s)")
        except LLMScrapeError:
            log.warning("[metadata_scraper] scrape_with_context failed, fallback to scrape")
            result = scraper.llm_scraper.scrape(video_filename, subtitle_filenames, conn=conn)

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
        result["confidence"] = confidence_result.final_confidence
        result["scrape_trace"] = confidence_result.scrape_trace
        result["confidence_gate_blocked"] = confidence_result.gate_blocked
        result["confidence_search"] = confidence_result.search_conf
        result["confidence_data_gate"] = confidence_result.data_gate
        result["provider_type"] = provider.provider_type
        result["provider_id"] = search_item.item_id
        log.info(f"[metadata_scraper] done: total={time.time()-t_start:.1f}s")
        return result

    log.info(f"[metadata_scraper] no provider, ai_only start ({time.time()-t_start:.1f}s)")
    result = scraper.llm_scraper.scrape(video_filename, subtitle_filenames, conn=conn)
    llm_raw_confidence = result.get("confidence", None)
    confidence_result = scraper.confidence_engine.calculate_ai_only(
        scrape_result=result,
        clean_result=clean_result,
        llm_raw_confidence=llm_raw_confidence,
        enabled_dims=enabled_dims_set,
        ai_clean_result=ai_clean_result,
        provider_fallback_reasons=last_provider_statuses if last_provider_statuses else None,
    )
    result["confidence"] = confidence_result.final_confidence
    result["scrape_trace"] = confidence_result.scrape_trace
    result["provider_type"] = ""
    result["provider_id"] = ""
    log.info(f"[metadata_scraper] done (ai_only): total={time.time()-t_start:.1f}s")
    return result


def scrape_series_metadata(scraper, series_name: str) -> Dict[str, Any]:
    for provider in scraper.providers:
        try:
            search_result = provider.search(series_name, media_type="tv")
            if search_result.items:
                search_item = search_result.items[0]
                details = provider.get_details(search_item.item_id, "tv")
                clean_result = CleanResult(clean_title=series_name)
                provider_context = scraper._extract_context(details, clean_result, provider)
                try:
                    return scraper.llm_scraper.scrape_series_with_context(
                        series_name, provider_context, provider_name=provider.display_name
                    )
                except LLMScrapeError:
                    pass
        except Exception:
            pass

    return scraper.llm_scraper.scrape_series(series_name)
