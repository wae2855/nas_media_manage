#!/usr/bin/env python3
import os
import re
import json
from typing import Dict, List, Optional, Any
from tmdb_client import TMDbClient, TMDbError
from llm_scraper import LLMScraper, LLMScrapeError


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

    def _search_tmdb(self, clean_title: str, year: Optional[int],
                     season: Optional[int], episode: Optional[int]) -> Optional[tuple]:
        if not self.tmdb_client:
            return None

        try:
            if season is not None:
                tmdb_result = self.tmdb_client.search_tv(clean_title, year)
                if tmdb_result:
                    return tmdb_result, "tv"

            tmdb_result = self.tmdb_client.search_movie(clean_title, year)
            if tmdb_result:
                return tmdb_result, "movie"

            if season is None:
                tmdb_result = self.tmdb_client.search_tv(clean_title, year)
                if tmdb_result:
                    return tmdb_result, "tv"

        except TMDbError:
            pass

        return None

    def scrape(self, video_filename: str, subtitle_filenames: List[str] = None,
               conn=None) -> Dict[str, Any]:
        if subtitle_filenames is None:
            subtitle_filenames = []

        clean_title, year, season, episode = self._preprocess_filename(video_filename)

        tmdb_match = self._search_tmdb(clean_title, year, season, episode)

        tmdb_dimensions = {}
        if tmdb_match:
            tmdb_data, media_type = tmdb_match
            if conn:
                tmdb_dimensions = self._map_tmdb_dimensions(tmdb_data, conn)
            tmdb_context = self._extract_tmdb_context(
                tmdb_data, media_type, year, season, episode
            )
            try:
                result = self.llm_scraper.scrape_with_context(
                    video_filename, subtitle_filenames, tmdb_context,
                    tmdb_dimensions=tmdb_dimensions, conn=conn
                )
                return result
            except LLMScrapeError:
                pass

        return self.llm_scraper.scrape(video_filename, subtitle_filenames, conn=conn)

    def _map_tmdb_dimensions(self, tmdb_data: dict, conn) -> dict:
        from dimension_manager import get_dimensions_for_tmdb, map_tmdb_to_dimension
        tmdb_dims = get_dimensions_for_tmdb(conn)
        result = {}
        for dim_config in tmdb_dims:
            mapped = map_tmdb_to_dimension(dim_config, tmdb_data)
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
