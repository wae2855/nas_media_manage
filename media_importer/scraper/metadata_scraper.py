#!/usr/bin/env python3
import os
import re
from typing import Dict, List, Optional, Any
from .providers import create_providers
from .providers.base import MetadataProvider, SearchItem, MediaDetails, DimensionMapping
from .llm_scraper import LLMScraper
from .confidence_engine import (
    FilenameCleaner, TitleMatcher, ConfidenceEngine, CleanResult, MatchResult
)
from media_importer.features.configuration import ConfigView
from .metadata_scrape_flow import scrape_metadata, scrape_series_metadata


class MetadataScraper:
    def __init__(self, config: dict):
        self.config = config
        self.view = ConfigView.from_dict(config)
        self.providers = create_providers(config)
        self.llm_scraper = LLMScraper(config)
        self.confidence_engine = ConfidenceEngine(self.view.metadata.confidence)
        self._cleaner = FilenameCleaner()
        self._matcher = TitleMatcher(self.view.metadata.confidence)

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

    def _search_with_match(self, provider, clean_title, year, season, min_threshold=None):
        import logging
        _log = logging.getLogger(__name__)

        match_threshold = min_threshold if min_threshold is not None else self.confidence_engine._config.get("provider_match_threshold", 0.85)
        media_type_hint = "tv" if season is not None else None

        best_match = None
        best_T = 0.0
        best_search_info = None
        best_media_type = None
        best_result_item = None
        search_error = None
        has_any_results = False

        def _do_search(query, year_val, media_type=None):
            nonlocal best_match, best_T, best_result_item, best_media_type, best_search_info, search_error, has_any_results
            try:
                search_result = provider.search(query, year=year_val, media_type=media_type)
                if search_result.items:
                    has_any_results = True
                for idx, item in enumerate(search_result.items):
                    match_result = self._matcher.match_standard(query, item, year_val, season)
                    if match_result.T > best_T:
                        best_T = match_result.T
                        best_match = match_result
                        best_result_item = item
                        best_media_type = item.media_type
                        best_search_info = {
                            "query": query,
                            "total_results": search_result.total_results,
                            "selected_index": idx,
                            "selected_title": item.title,
                            "selected_original_title": item.original_title,
                            "selected_year": item.year,
                            "title_match_level": match_result.level,
                            "title_similarity": match_result.similarity,
                            "year_match": match_result.year_match,
                            "fallback_used": False,
                            "original_filename": "",
                            "provider_type": provider.provider_type,
                        }
            except Exception as e:
                search_error = str(e)
                _log.warning(f"[provider_search] {provider.provider_type} search failed: {e}")

        _do_search(clean_title, year, media_type=media_type_hint)

        if best_T >= match_threshold and best_result_item:
            return (best_result_item, best_media_type, best_match, best_search_info), None

        if best_T < match_threshold and year is not None:
            _do_search(clean_title, None, media_type=media_type_hint)

        if best_T >= match_threshold and best_result_item:
            return (best_result_item, best_media_type, best_match, best_search_info), None

        if best_T < match_threshold and hasattr(provider, 'fallback_language') and hasattr(provider, 'language') and provider.fallback_language != provider.language:
            original_lang = None
            try:
                if hasattr(provider, '_client') and hasattr(provider._client, 'language'):
                    original_lang = provider._client.language
                    provider._client.language = provider.fallback_language
                _do_search(clean_title, year, media_type=media_type_hint)
            except Exception as e:
                search_error = str(e)
                _log.warning(f"[provider_search] {provider.provider_type} fallback search failed: {e}")
            finally:
                if original_lang is not None and hasattr(provider, '_client') and hasattr(provider._client, 'language'):
                    provider._client.language = original_lang

        if best_T >= match_threshold and best_result_item:
            return (best_result_item, best_media_type, best_match, best_search_info), None

        if search_error:
            status = {"provider_type": provider.provider_type, "display_name": provider.display_name,
                      "status": "error", "reason": f"搜索失败: {search_error}", "best_T": best_T}
        elif not has_any_results:
            status = {"provider_type": provider.provider_type, "display_name": provider.display_name,
                      "status": "no_results", "reason": f"{provider.display_name} 搜索无结果", "best_T": 0.0}
        else:
            status = {"provider_type": provider.provider_type, "display_name": provider.display_name,
                      "status": "below_threshold", "reason": f"匹配度低于阈值 (T={best_T:.3f})", "best_T": best_T}

        return None, status

    def _search_tmdb_with_match(self, clean_title, year, season, min_threshold=None):
        if self.providers:
            result, _status = self._search_with_match(self.providers[0], clean_title, year, season, min_threshold=min_threshold)
            return result
        return None

    def _search_all_providers(self, clean_title, year, season, min_threshold=None):
        best_result = None
        best_T = 0.0
        provider_statuses = []
        for provider in self.providers:
            result, status = self._search_with_match(provider, clean_title, year, season, min_threshold=min_threshold)
            if result:
                item, media_type, match_result, search_info = result
                if match_result.T > best_T:
                    best_T = match_result.T
                    best_result = (provider, item, media_type, match_result, search_info)
                    if status is None:
                        status = {"provider_type": provider.provider_type, "display_name": provider.display_name,
                                  "status": "success", "reason": "", "best_T": match_result.T}
            if status:
                provider_statuses.append(status)
        if not self.providers:
            provider_statuses.append({"provider_type": "none", "display_name": "无",
                                      "status": "not_configured", "reason": "未配置任何元数据源", "best_T": 0.0})
        return best_result, provider_statuses

    def _extract_context(self, details, clean_result, provider):
        title_cn = details.title
        title_en = details.original_title
        final_year = clean_result.year if clean_result.year else details.year

        genre_names = [g.name for g in details.genres if g.name]

        overview = details.overview
        adult = details.adult
        vote_average = details.vote_average

        origin_country = details.origin_country
        production_countries = details.raw_data.get("production_countries", [])
        country_names = [c.get("name", "") for c in production_countries if c.get("name")]
        if not country_names and origin_country:
            country_names = origin_country

        tagline = details.tagline

        context_parts = [
            f"【{provider.display_name} 元数据参考】",
            f"中文标题: {title_cn}",
            f"原始标题: {title_en}",
            f"年份: {final_year or '未知'}",
            f"类型: {details.media_type}",
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
        if details.media_type == "tv":
            if clean_result.season is not None:
                context_parts.append(f"季: {clean_result.season}")
            if clean_result.episode is not None:
                context_parts.append(f"集: {clean_result.episode}")
            number_of_seasons = details.raw_data.get("number_of_seasons")
            if number_of_seasons:
                context_parts.append(f"总季数: {number_of_seasons}")

        context_parts.append(f"\n请基于以上 {provider.display_name} 权威数据，整理为系统所需格式。")

        return "\n".join(context_parts)

    def _extract_tmdb_context(self, tmdb_data: dict, media_type: str,
                              year: Optional[int], season: Optional[int],
                              episode: Optional[int]) -> str:
        if not self.providers:
            return ""
        provider = self.providers[0]
        date_field = "release_date" if media_type == "movie" else "first_air_date"
        release_date = tmdb_data.get(date_field, "")
        tmdb_year = None
        if release_date and len(release_date) >= 4:
            try:
                tmdb_year = int(release_date[:4])
            except (ValueError, TypeError):
                pass
        from .providers.base import MediaDetails as _MD, Genre as _G
        details = _MD(
            provider_type="tmdb",
            item_id=str(tmdb_data.get("id", "")),
            media_type=media_type,
            title=tmdb_data.get("title") or tmdb_data.get("name", ""),
            original_title=tmdb_data.get("original_title") or tmdb_data.get("original_name", ""),
            year=tmdb_year,
            genres=[_G(id=str(g.get("id", "")), name=g.get("name", "")) for g in tmdb_data.get("genres", [])],
            overview=tmdb_data.get("overview", ""),
            vote_average=tmdb_data.get("vote_average", 0),
            origin_country=tmdb_data.get("origin_country", []),
            original_language=tmdb_data.get("original_language", ""),
            adult=tmdb_data.get("adult", False),
            tagline=tmdb_data.get("tagline", ""),
            poster_url="",
            raw_data=tmdb_data,
        )
        clean_result = CleanResult(clean_title="", year=year, season=season, episode=episode)
        return self._extract_context(details, clean_result, provider)

    def _map_provider_dimensions(self, provider, details, conn):
        from .dimension_manager import get_dimensions_for_provider
        dim_configs = get_dimensions_for_provider(conn, provider.provider_type)
        dim_mappings = provider.map_dimensions(dim_configs, details)
        return {dm.name: {'value': dm.value, 'confidence': dm.confidence, 'source': dm.source} for dm in dim_mappings}

    def _map_tmdb_dimensions(self, tmdb_data: dict, conn, media_type: str = "movie",
                            tmdb_id: int = None) -> dict:
        if not self.providers:
            return {}
        provider = self.providers[0]
        from .providers.base import MediaDetails as _MD, Genre as _G
        date_field = "release_date" if media_type == "movie" else "first_air_date"
        release_date = tmdb_data.get(date_field, "")
        tmdb_year = None
        if release_date and len(release_date) >= 4:
            try:
                tmdb_year = int(release_date[:4])
            except (ValueError, TypeError):
                pass
        details = _MD(
            provider_type="tmdb",
            item_id=str(tmdb_id or tmdb_data.get("id", "")),
            media_type=media_type,
            title=tmdb_data.get("title") or tmdb_data.get("name", ""),
            original_title=tmdb_data.get("original_title") or tmdb_data.get("original_name", ""),
            year=tmdb_year,
            genres=[_G(id=str(g.get("id", "")), name=g.get("name", "")) for g in tmdb_data.get("genres", [])],
            overview=tmdb_data.get("overview", ""),
            vote_average=tmdb_data.get("vote_average", 0),
            origin_country=tmdb_data.get("origin_country", []),
            original_language=tmdb_data.get("original_language", ""),
            adult=tmdb_data.get("adult", False),
            tagline=tmdb_data.get("tagline", ""),
            poster_url="",
            raw_data=tmdb_data,
        )
        return self._map_provider_dimensions(provider, details, conn)

    def scrape(self, video_filename: str, subtitle_filenames: List[str] = None,
               conn=None) -> Dict[str, Any]:
        return scrape_metadata(self, video_filename, subtitle_filenames, conn)

    def scrape_series(self, series_name: str) -> Dict[str, Any]:
        return scrape_series_metadata(self, series_name)
