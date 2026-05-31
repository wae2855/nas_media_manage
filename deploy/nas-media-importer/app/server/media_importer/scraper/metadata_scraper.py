#!/usr/bin/env python3
import os
import re
import json
from typing import Dict, List, Optional, Any
from .tmdb_client import TMDbClient, TMDbError
from .llm_scraper import LLMScraper, LLMScrapeError
from .confidence_engine import (
    FilenameCleaner, TitleMatcher, ConfidenceEngine, CleanResult, MatchResult
)
from media_importer.core.db import get_enabled_dimensions


class MetadataScraper:
    def __init__(self, config: dict):
        self.config = config
        self.metadata_config = config.get("metadata", {})
        self.tmdb_config = self.metadata_config.get("tmdb", {})
        self.tmdb_enabled = self.tmdb_config.get("enabled", False)
        self.tmdb_api_key = self.tmdb_config.get("api_key", "")

        if self.tmdb_enabled and self.tmdb_api_key:
            self.tmdb_client = TMDbClient(
                api_key=self.tmdb_api_key,
                language=self.tmdb_config.get("language", "zh-CN"),
                fallback_language=self.tmdb_config.get("fallback_language", "en-US"),
                timeout=self.tmdb_config.get("request_timeout", 10),
                max_retries=self.tmdb_config.get("max_retries", 3)
            )
        else:
            self.tmdb_client = None

        self.llm_scraper = LLMScraper(config)
        self.confidence_engine = ConfidenceEngine(config.get("confidence", {}))
        self._cleaner = FilenameCleaner()
        self._matcher = TitleMatcher(config.get("confidence", {}))

    def _preprocess_filename(self, filename: str) -> tuple:
        clean_name = os.path.splitext(filename)[0]

        season = None
        episode = None

        season_match = re.search(r'[sS](\d+)', clean_name)
        if season_match:
            season = int(season_match.group(1))

        episode_match = re.search(r'[eE](\d+)', clean_name)
        if episode_match:
            episode = int(episode_match.group(1))

        year = None
        year_match = re.search(r'[.(](19\d\d|20\d\d)[.)]|\.(19\d\d|20\d\d)\.', clean_name)
        if year_match:
            year_candidate = year_match.group(1) or year_match.group(2)
            if year_candidate:
                year = int(year_candidate)

        patterns = [
            r'\.(1080p|720p|2160p|4K|BluRay|WEB-DL|HDTV|x264|x265|HDR|DDP5\.1|Atmos|AAC|DTS)[^.]*',
            r'\[(.*?)\]',
            r'\((.*?)\)',
            r'[sS]\d+[eE]\d+',
            r'Season\.\d+',
            r'Episode\.\d+',
            r'[._](19\d\d|20\d\d)',
        ]
        for pattern in patterns:
            clean_name = re.sub(pattern, '', clean_name)

        clean_name = re.sub(r'[._]', ' ', clean_name)
        clean_name = clean_name.strip()
        clean_name = re.sub(r'\s+', ' ', clean_name)

        return clean_name, year, season, episode

    def _extract_tmdb_context(self, tmdb_data: dict, media_type: str,
                              year: Optional[int], season: Optional[int],
                              episode: Optional[int]) -> str:
        title_field = "title" if media_type == "movie" else "name"
        original_title_field = "original_title" if media_type == "movie" else "original_name"
        date_field = "release_date" if media_type == "movie" else "first_air_date"

        title_cn = tmdb_data.get(title_field, "")
        title_en = tmdb_data.get(original_title_field, "")
        release_date = tmdb_data.get(date_field, "")
        tmdb_year = int(release_date[:4]) if release_date else None
        final_year = year if year else tmdb_year

        genres = tmdb_data.get("genres", [])
        genre_names = [g.get("name", "") for g in genres if g.get("name")]

        overview = tmdb_data.get("overview", "")

        adult = tmdb_data.get("adult", False)

        vote_average = tmdb_data.get("vote_average", 0)

        origin_country = tmdb_data.get("origin_country", [])
        production_countries = tmdb_data.get("production_countries", [])
        country_names = [c.get("name", "") for c in production_countries if c.get("name")]
        if not country_names and origin_country:
            country_names = origin_country

        tagline = tmdb_data.get("tagline", "")

        context_parts = [
            f"【TMDb 元数据参考】",
            f"中文标题: {title_cn}",
            f"原始标题: {title_en}",
            f"年份: {final_year or '未知'}",
            f"类型: {media_type}",
        ]

        if genre_names:
            context_parts.append(f"类型标签(genres): {', '.join(genre_names)}")
        if overview:
            context_parts.append(f"简介: {overview[:300]}")
        if adult:
            context_parts.append(f"成人内容标记: 是")
        if vote_average:
            context_parts.append(f"评分: {vote_average}")
        if country_names:
            context_parts.append(f"制片国家: {', '.join(country_names)}")
        if tagline:
            context_parts.append(f"标语: {tagline}")
        if media_type == "tv":
            if season is not None:
                context_parts.append(f"季: {season}")
            if episode is not None:
                context_parts.append(f"集: {episode}")
            number_of_seasons = tmdb_data.get("number_of_seasons")
            if number_of_seasons:
                context_parts.append(f"总季数: {number_of_seasons}")

        context_parts.append(f"\n请基于以上 TMDb 权威数据，整理为系统所需格式。")

        return "\n".join(context_parts)

    def _search_tmdb_with_match(self, clean_title: str, year: Optional[int],
                                season: Optional[int],
                                min_threshold: Optional[float] = None) -> Optional[tuple]:
        if not self.tmdb_client:
            return None

        import logging
        _log = logging.getLogger(__name__)

        match_threshold = min_threshold if min_threshold is not None else self.confidence_engine._config.get("tmdb_match_threshold", 0.85)

        if season is not None:
            search_methods = [
                (self.tmdb_client.search_tv_list, "tv"),
                (self.tmdb_client.search_movie_list, "movie"),
            ]
        else:
            search_methods = [
                (self.tmdb_client.search_movie_list, "movie"),
                (self.tmdb_client.search_tv_list, "tv"),
            ]

        best_match = None
        best_T = 0.0
        best_search_info = None
        best_media_type = None
        best_result_item = None
        consecutive_errors = 0

        def _do_search(search_fn, media_type, query, year_val):
            nonlocal best_match, best_T, best_result_item, best_media_type, best_search_info, consecutive_errors
            try:
                search_result = search_fn(query, year_val)
                results = search_result.get("results", [])
                total_results = search_result.get("total_results", 0)
                consecutive_errors = 0

                for item in results:
                    match_result = self._matcher.match(query, item, year_val, season)
                    if match_result.T > best_T:
                        best_T = match_result.T
                        best_match = match_result
                        best_result_item = item
                        best_media_type = media_type
                        best_search_info = {
                            "query": query,
                            "total_results": total_results,
                            "selected_index": results.index(item),
                            "selected_title": item.get("title") or item.get("name", ""),
                            "selected_original_title": item.get("original_title") or item.get("original_name", ""),
                            "selected_year": item.get("release_date", "")[:4] if item.get("release_date") else None,
                            "title_match_level": match_result.level,
                            "title_similarity": match_result.similarity,
                            "year_match": match_result.year_match,
                            "fallback_used": False,
                            "original_filename": "",
                        }
            except TMDbError as e:
                consecutive_errors += 1
                _log.warning(f"[tmdb_search] {media_type} search failed ({consecutive_errors}): {e}")

        for search_fn, media_type in search_methods:
            _do_search(search_fn, media_type, clean_title, year)
            if consecutive_errors >= 2:
                _log.warning("[tmdb_search] consecutive network errors, skipping remaining searches")
                break
            if best_T >= match_threshold:
                break

        if best_T >= match_threshold and best_result_item:
            return best_result_item, best_media_type, best_match, best_search_info

        if best_T < match_threshold and year is not None and consecutive_errors < 2:
            for search_fn, media_type in search_methods:
                _do_search(search_fn, media_type, clean_title, None)
                if consecutive_errors >= 2:
                    break

        if best_T >= match_threshold and best_result_item:
            return best_result_item, best_media_type, best_match, best_search_info

        if best_T < match_threshold and consecutive_errors < 2 and self.tmdb_client.language != self.tmdb_client.fallback_language:
            for search_fn, media_type in search_methods:
                try:
                    params_backup = self.tmdb_client.language
                    self.tmdb_client.language = self.tmdb_client.fallback_language
                    _do_search(search_fn, media_type, clean_title, year)
                    self.tmdb_client.language = params_backup
                    if consecutive_errors >= 2:
                        break
                except TMDbError as e:
                    consecutive_errors += 1
                    _log.warning(f"[tmdb_search] fallback {media_type} search failed: {e}")

        if best_T >= match_threshold and best_result_item:
            return best_result_item, best_media_type, best_match, best_search_info

        return None

    def scrape(self, video_filename: str, subtitle_filenames: List[str] = None,
               conn=None) -> Dict[str, Any]:
        if subtitle_filenames is None:
            subtitle_filenames = []

        import time
        import logging
        _log = logging.getLogger(__name__)

        enabled_dims_set = None
        if conn:
            try:
                enabled_dims_set = {d["name"] for d in get_enabled_dimensions(conn)}
            except Exception:
                pass

        t_start = time.time()
        clean_result = self._cleaner.clean(video_filename)
        ai_clean_result = None
        _log.info(f"[metadata_scraper] regex_clean: title={clean_result.clean_title}, year={clean_result.year}, season={clean_result.season}, year_suspect={clean_result.year_suspect}")

        match_threshold = self.confidence_engine._config.get("tmdb_match_threshold", 0.85)
        ai_research_threshold = self.confidence_engine._config.get("confirm_threshold", 0.5)

        if clean_result.year_suspect:
            try:
                _log.info(f"[metadata_scraper] year_suspect=True, ai_clean first ({time.time()-t_start:.1f}s)")
                ai_clean_result = self._cleaner.ai_clean(video_filename, self.llm_scraper)
                _log.info(f"[metadata_scraper] ai_clean done: title={ai_clean_result.clean_title}, year={ai_clean_result.year} ({time.time()-t_start:.1f}s)")
                tmdb_search_result = self._search_tmdb_with_match(
                    ai_clean_result.clean_title, ai_clean_result.year, clean_result.season,
                    min_threshold=ai_research_threshold
                )
                _log.info(f"[metadata_scraper] tmdb_search (post-ai-clean) done: found={tmdb_search_result is not None} ({time.time()-t_start:.1f}s)")
            except Exception as e:
                _log.warning(f"[metadata_scraper] ai_clean + tmdb_search failed: {e}")
                tmdb_search_result = None
        else:
            if clean_result.cjk_title and self.tmdb_client:
                _log.info(f"[metadata_scraper] tmdb_search_cjk start: query={clean_result.cjk_title}")
                tmdb_search_result = self._search_tmdb_with_match(
                    clean_result.cjk_title, clean_result.year, clean_result.season
                )
                _log.info(f"[metadata_scraper] tmdb_search_cjk done: found={tmdb_search_result is not None} ({time.time()-t_start:.1f}s)")

                if tmdb_search_result:
                    _, cjk_mt, cjk_match, _ = tmdb_search_result
                    if cjk_match.T < match_threshold:
                        _log.info(f"[metadata_scraper] cjk T={cjk_match.T:.3f} < threshold, eng search start")
                        eng_search_result = self._search_tmdb_with_match(
                            clean_result.clean_title, clean_result.year, clean_result.season
                        )
                        if eng_search_result:
                            _, eng_mt, eng_match, _ = eng_search_result
                            if eng_match.T > cjk_match.T:
                                tmdb_search_result = eng_search_result
                                _log.info(f"[metadata_scraper] eng search better: T={eng_match.T:.3f} > cjk T={cjk_match.T:.3f}")
                else:
                    _log.info(f"[metadata_scraper] cjk no result, eng search start: query={clean_result.clean_title}")
                    tmdb_search_result = self._search_tmdb_with_match(
                        clean_result.clean_title, clean_result.year, clean_result.season
                    )
                    _log.info(f"[metadata_scraper] eng search done: found={tmdb_search_result is not None} ({time.time()-t_start:.1f}s)")
            else:
                _log.info(f"[metadata_scraper] tmdb_search_1 start: query={clean_result.clean_title}")
                tmdb_search_result = self._search_tmdb_with_match(
                    clean_result.clean_title, clean_result.year, clean_result.season
                )
                _log.info(f"[metadata_scraper] tmdb_search_1 done: found={tmdb_search_result is not None} ({time.time()-t_start:.1f}s)")

            if tmdb_search_result:
                _, _, match_result, search_info = tmdb_search_result
                _log.info(f"[metadata_scraper] match T={match_result.T:.3f}, threshold={match_threshold}")
                if match_result.T < match_threshold:
                    try:
                        _log.info(f"[metadata_scraper] ai_clean start ({time.time()-t_start:.1f}s)")
                        ai_clean_result = self._cleaner.ai_clean(video_filename, self.llm_scraper)
                        _log.info(f"[metadata_scraper] ai_clean done: title={ai_clean_result.clean_title}, year={ai_clean_result.year} ({time.time()-t_start:.1f}s)")
                        _search_year_2 = ai_clean_result.year if ai_clean_result.year is not None else clean_result.year
                        tmdb_search_result_2 = self._search_tmdb_with_match(
                            ai_clean_result.clean_title, _search_year_2, clean_result.season,
                            min_threshold=ai_research_threshold
                        )
                        if tmdb_search_result_2:
                            _, _, match_result_2, search_info_2 = tmdb_search_result_2
                            if match_result_2.T > match_result.T:
                                tmdb_search_result = tmdb_search_result_2
                                _log.info(f"[metadata_scraper] tmdb_search_2 better: T={match_result_2.T:.3f}")
                    except Exception as e:
                        _log.warning(f"[metadata_scraper] ai_clean + tmdb_search_2 failed: {e}")
            else:
                try:
                    _log.info(f"[metadata_scraper] no tmdb result, ai_clean start ({time.time()-t_start:.1f}s)")
                    ai_clean_result = self._cleaner.ai_clean(video_filename, self.llm_scraper)
                    _log.info(f"[metadata_scraper] ai_clean done: title={ai_clean_result.clean_title}, year={ai_clean_result.year} ({time.time()-t_start:.1f}s)")
                    _search_year = ai_clean_result.year if ai_clean_result.year is not None else clean_result.year
                    tmdb_search_result = self._search_tmdb_with_match(
                        ai_clean_result.clean_title, _search_year, clean_result.season,
                        min_threshold=ai_research_threshold
                    )
                    _log.info(f"[metadata_scraper] tmdb_search_2 done: found={tmdb_search_result is not None} ({time.time()-t_start:.1f}s)")
                except Exception as e:
                    _log.warning(f"[metadata_scraper] ai_clean + tmdb_search failed: {e}")

        if tmdb_search_result:
            tmdb_item, media_type, match_result, search_info = tmdb_search_result
            tmdb_id = tmdb_item.get("id")
            try:
                _log.info(f"[metadata_scraper] get_tmdb_details start: id={tmdb_id} ({time.time()-t_start:.1f}s)")
                if media_type == "movie":
                    tmdb_data = self.tmdb_client.get_movie_details(tmdb_id)
                else:
                    tmdb_data = self.tmdb_client.get_tv_details(tmdb_id)
                _log.info(f"[metadata_scraper] get_tmdb_details done ({time.time()-t_start:.1f}s)")
            except TMDbError:
                _log.warning(f"[metadata_scraper] tmdb_details failed, fallback to ai_only")
                result = self.llm_scraper.scrape(video_filename, subtitle_filenames, conn=conn)
                llm_raw_confidence = result.get("confidence", None)
                confidence_result = self.confidence_engine.calculate_ai_only(
                    scrape_result=result,
                    clean_result=clean_result,
                    llm_raw_confidence=llm_raw_confidence,
                    enabled_dims=enabled_dims_set,
                    ai_clean_result=ai_clean_result,
                )
                result["confidence"] = confidence_result.final_confidence
                result["scrape_trace"] = confidence_result.scrape_trace
                return result

            search_info["original_filename"] = video_filename

            tmdb_dimensions = {
                'media_type': {
                    'value': media_type,
                    'confidence': 1.0,
                    'source': 'tmdb',
                }
            }
            if conn:
                tmdb_dimensions.update(self._map_tmdb_dimensions(
                    tmdb_data, conn, media_type=media_type, tmdb_id=tmdb_id
                ))
            tmdb_context = self._extract_tmdb_context(
                tmdb_data, media_type, clean_result.year, clean_result.season, clean_result.episode
            )

            try:
                _log.info(f"[metadata_scraper] scrape_with_context start ({time.time()-t_start:.1f}s)")
                result = self.llm_scraper.scrape_with_context(
                    video_filename, subtitle_filenames, tmdb_context,
                    tmdb_dimensions=tmdb_dimensions, conn=conn
                )
                _log.info(f"[metadata_scraper] scrape_with_context done ({time.time()-t_start:.1f}s)")
            except LLMScrapeError:
                _log.warning(f"[metadata_scraper] scrape_with_context failed, fallback to scrape")
                result = self.llm_scraper.scrape(video_filename, subtitle_filenames, conn=conn)

            llm_raw_confidence = result.get("confidence", None)
            confidence_result = self.confidence_engine.calculate(
                scrape_result=result,
                tmdb_search_info=search_info,
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
            _log.info(f"[metadata_scraper] done: total={time.time()-t_start:.1f}s")
            return result

        _log.info(f"[metadata_scraper] no tmdb, ai_only start ({time.time()-t_start:.1f}s)")
        result = self.llm_scraper.scrape(video_filename, subtitle_filenames, conn=conn)
        llm_raw_confidence = result.get("confidence", None)
        confidence_result = self.confidence_engine.calculate_ai_only(
            scrape_result=result,
            clean_result=clean_result,
            llm_raw_confidence=llm_raw_confidence,
            enabled_dims=enabled_dims_set,
            ai_clean_result=ai_clean_result,
        )
        result["confidence"] = confidence_result.final_confidence
        result["scrape_trace"] = confidence_result.scrape_trace
        _log.info(f"[metadata_scraper] done (ai_only): total={time.time()-t_start:.1f}s")
        return result

    def _map_tmdb_dimensions(self, tmdb_data: dict, conn, media_type: str = "movie",
                            tmdb_id: int = None) -> dict:
        from .dimension_manager import get_dimensions_for_tmdb, map_tmdb_to_dimension
        tmdb_dims = get_dimensions_for_tmdb(conn)

        release_dates = []
        if tmdb_id and self.tmdb_client:
            try:
                if media_type == "movie":
                    release_dates = self.tmdb_client.get_movie_release_dates(tmdb_id)
                else:
                    release_dates = self.tmdb_client.get_tv_release_dates(tmdb_id)
            except Exception:
                pass

        result = {}
        for dim_config in tmdb_dims:
            mapped = map_tmdb_to_dimension(dim_config, tmdb_data, release_dates)
            if mapped and mapped.get('value') is not None:
                result[mapped['name']] = {
                    'value': mapped['value'],
                    'confidence': mapped.get('confidence', 1.0),
                    'source': 'tmdb',
                }
        return result

    def scrape_series(self, series_name: str) -> Dict[str, Any]:
        if self.tmdb_client:
            try:
                tmdb_result = self.tmdb_client.search_tv(series_name)
                if tmdb_result:
                    tmdb_context = self._extract_tmdb_context(
                        tmdb_result, "tv", None, None, None
                    )
                    try:
                        result = self.llm_scraper.scrape_series_with_context(
                            series_name, tmdb_context
                        )
                        return result
                    except LLMScrapeError:
                        pass
            except TMDbError:
                pass

        return self.llm_scraper.scrape_series(series_name)
