from typing import Optional, List

from .base import (
    MetadataProvider, SearchResult, SearchItem,
    MediaDetails, Genre, DimensionMapping
)
from . import register_provider
from media_importer.scraper.tmdb_client import TMDbClient, TMDbError


@register_provider
class TMDbProvider(MetadataProvider):
    provider_type = "tmdb"
    display_name = "TMDb"

    def __init__(self, config: dict):
        self._client = TMDbClient(
            api_key=config.get("api_key", ""),
            language=config.get("language", "zh-CN"),
            fallback_language=config.get("fallback_language", "en-US"),
            timeout=int(config.get("request_timeout", 10) or 10),
            max_retries=int(config.get("max_retries", 3) or 3),
        )
        self._config = config

    @property
    def language(self):
        return self._client.language

    @property
    def fallback_language(self):
        return self._client.fallback_language

    def search(self, query: str, year: Optional[int] = None,
               media_type: Optional[str] = None) -> SearchResult:
        results = []
        total = 0
        last_error = None

        if media_type == "tv" or media_type is None:
            try:
                tv_raw = self._client.search_tv_list(query, year=year)
                for item in tv_raw.get("results", []):
                    results.append(self._to_search_item(item, "tv"))
                total += tv_raw.get("total_results", 0)
            except TMDbError as e:
                last_error = e

        if media_type == "movie" or media_type is None:
            try:
                movie_raw = self._client.search_movie_list(query, year=year)
                for item in movie_raw.get("results", []):
                    results.append(self._to_search_item(item, "movie"))
                total += movie_raw.get("total_results", 0)
            except TMDbError as e:
                last_error = e

        if not results and last_error is not None:
            raise last_error

        return SearchResult(items=results, total_results=total)

    def _to_search_item(self, raw: dict, media_type: str) -> SearchItem:
        date_field = "release_date" if media_type == "movie" else "first_air_date"
        release_date = raw.get(date_field, "")
        year = None
        if release_date and len(release_date) >= 4:
            try:
                year = int(release_date[:4])
            except (ValueError, TypeError):
                pass
        poster_path = raw.get("poster_path", "")
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
        return SearchItem(
            provider_type="tmdb",
            item_id=str(raw.get("id", "")),
            title=raw.get("title") or raw.get("name", ""),
            original_title=raw.get("original_title") or raw.get("original_name", ""),
            year=year,
            media_type=media_type,
            poster_url=poster_url,
            vote_average=raw.get("vote_average"),
            raw_data=raw,
        )

    def get_details(self, item_id: str, media_type: str) -> MediaDetails:
        if media_type == "movie":
            raw = self._client.get_movie_details(int(item_id))
        else:
            raw = self._client.get_tv_details(int(item_id))
        return self._to_media_details(raw, media_type)

    def _to_media_details(self, raw: dict, media_type: str) -> MediaDetails:
        date_field = "release_date" if media_type == "movie" else "first_air_date"
        release_date = raw.get(date_field, "")
        year = None
        if release_date and len(release_date) >= 4:
            try:
                year = int(release_date[:4])
            except (ValueError, TypeError):
                pass
        genres = [Genre(id=str(g.get("id", "")), name=g.get("name", "")) for g in raw.get("genres", [])]
        poster_path = raw.get("poster_path", "")
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
        return MediaDetails(
            provider_type="tmdb",
            item_id=str(raw.get("id", "")),
            media_type=media_type,
            title=raw.get("title") or raw.get("name", ""),
            original_title=raw.get("original_title") or raw.get("original_name", ""),
            year=year,
            genres=genres,
            overview=raw.get("overview", ""),
            vote_average=raw.get("vote_average", 0),
            origin_country=raw.get("origin_country", []),
            original_language=raw.get("original_language", ""),
            adult=raw.get("adult", False),
            tagline=raw.get("tagline", ""),
            poster_url=poster_url,
            raw_data=raw,
            rating_info={"adult": raw.get("adult", False)},
        )

    def get_genres(self, media_type: Optional[str] = None) -> list:
        return self._client.get_genre_list()

    def test_connection(self) -> bool:
        return self._client.test_connection()

    def map_dimensions(self, dim_configs: list, details: MediaDetails) -> List[DimensionMapping]:
        from media_importer.features.scraping.dimension_manager import map_provider_to_dimension
        release_dates = self._get_release_dates(details.item_id, details.media_type)
        results = []
        for dim_config in dim_configs:
            mapping = map_provider_to_dimension(
                dim_config, details.raw_data, release_dates, provider_type="tmdb"
            )
            if mapping and mapping.get("value") is not None:
                results.append(DimensionMapping(
                    name=mapping["name"],
                    value=mapping["value"],
                    source_reliability=mapping.get("source_reliability", 1.0),
                    source="tmdb",
                ))
        return results

    def _get_release_dates(self, item_id: str, media_type: str) -> list:
        try:
            if media_type == "movie":
                return self._client.get_movie_release_dates(int(item_id))
            else:
                return self._client.get_tv_release_dates(int(item_id))
        except Exception:
            return []

    @classmethod
    def get_config_schema(cls) -> dict:
        return {
            "fields": [
                {"key": "api_key", "label": "API Key", "type": "password", "required": True},
                {"key": "language", "label": "优先语言", "type": "select",
                 "options": [
                     {"value": "zh-CN", "label": "中文"},
                     {"value": "en-US", "label": "英文"},
                     {"value": "ja-JP", "label": "日文"},
                     {"value": "ko-KR", "label": "韩文"},
                 ]},
                {"key": "fallback_language", "label": "回退语言", "type": "select",
                 "options": [
                     {"value": "en-US", "label": "英文"},
                     {"value": "zh-CN", "label": "中文"},
                 ]},
                {"key": "request_timeout", "label": "请求超时(秒)", "type": "number", "default": 10},
                {"key": "max_retries", "label": "最大重试次数", "type": "number", "default": 3},
            ],
        }

    @classmethod
    def get_context_template(cls) -> str:
        return (
            "你是一个专业的影视信息整理助手。\n"
            "系统已通过 TMDb API 获取到该影视作品的元数据，请基于这些数据整理为系统所需的格式化信息。\n\n"
            "重要原则：\n"
            "1. TMDb 数据是优先参考来源，标题、年份、类型等基础信息优先采用 TMDb 数据。\n"
            "2. 若 TMDb 数据不完整或存疑（如缺少某些维度信息、类型标签不够精确），请结合你的知识进行补充判断。"
            "例如：TMDb 可能未明确标注是否动漫，但你可以根据作品信息自行判断。\n"
            "3. 如果 TMDb 数据与文件名信息有冲突，以 TMDb 数据为准，但季/集编号以文件名为准。\n\n"
            "以下维度的映射数据已自动提取为参考（如为 null 表示未提供），请对每个维度给出判断：\n"
        )
