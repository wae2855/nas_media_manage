#!/usr/bin/env python3
"""LLM Scraper — public API; implementation distributed to _llm_client_impl / _llm_match_assist."""
from typing import List, Dict, Any, Optional

from media_importer.features.configuration import ConfigView
from media_importer.features.prompts.prompt_builder import LLMPromptBuilder
from media_importer.scraper.exceptions import LLMApiError, LLMWebSearchError, LLMScrapeError

from media_importer.scraper._llm_client_impl import (
    _build_payload_int,
    _send_request_impl,
    _inject_web_search_impl,
    _classify_error_impl,
    _do_call_impl,
    _parse_response_impl,
    _retry_with_fallback_impl,
    _call_with_retry_impl,
    _resolve_connection,
)
from media_importer.scraper._llm_match_assist import (
    _extract_title_impl,
    _tier2_correct_impl,
)


class LLMScraper:

    def __init__(self, config: dict):
        cfg_view = ConfigView.from_dict(config)
        ai_assist = cfg_view.ai_assist
        ai_search = cfg_view.ai_search

        self.view = cfg_view
        self.fast_model = ai_assist.model
        self.fast_base_url = ai_assist.base_url
        self.fast_api_key = ai_assist.api_key

        self.model = ai_search.model
        self.base_url = ai_search.base_url
        self.api_key = ai_search.api_key

        self.timeout = ai_assist.timeout
        self.max_retries = ai_assist.max_retries
        self.retry_delay = ai_assist.retry_delay
        self.verify_ssl = ai_assist.verify_ssl

        self.enabled = ai_assist.is_configured or ai_search.is_effective

        from media_importer.features.scraping.prompt_resolver import PromptResolver
        self.prompt_resolver = PromptResolver.from_config(config)

        from media_importer.features.scraping.scene_strategy import SceneStrategyResolver
        self.scene_strategy = SceneStrategyResolver(cfg_view)

        from media_importer.features.scraping.web_search_config import build_web_search_config
        web_search_cfg = {
            "provider": ai_search.provider,
            "enabled": ai_search.enabled,
            "search_type": ai_search.search_type,
            "base_url": ai_search.base_url,
        }
        self.web_search_config = build_web_search_config(web_search_cfg)
        default_dimensions = [
            {'name': 'media_type', 'label': '影视类型', 'values': ['movie', 'tv'],
             'ai_prompt': '请判断这是电影（movie）还是电视剧（tv）。判断依据：如果文件名中包含季集编号（如S01E01、S2E03等格式），则为电视剧（tv）；如果是完整独立的影视故事，则为电影（movie）。电视电影/网络电影仍归为movie。'},
            {'name': 'documentary', 'label': '是否纪录片', 'values': ['true', 'false'],
             'ai_prompt': '请判断是否为纪录片（true/false）。纪录片是以真实事件、人物、历史、社会等为主题的非虚构影视作品，包括自然纪录片（如《地球脉动》）、历史纪录片、社会纪录片、科学纪录片等。TMDB genres 包含 Documentary (id=99) 则为 true；如 TMDB 未标注，请根据标题和简介判断。真人出演+虚构剧情的作品（如《辛德勒的名单》）应选 false。'},
            {'name': 'restricted_level', 'label': '限制级分类', 'values': ['0-6', '7-12', '13-16', '17+'],
             'ai_prompt': '请判断该影视内容的年龄分级，从以下选项中选择最匹配的一个：0-6（幼儿/儿童）、7-12（家庭向）、13-16（青少年向）、17+（成人内容）。优先使用 TMDB release_dates 中的官方分级；如 TMDB 未提供，请联网搜索后判断。'},
            {'name': 'animation', 'label': '是否动漫', 'values': ['true', 'false'],
             'ai_prompt': '请判断是否为动漫/动画作品（true/false）。以动画/手绘/CG形式制作的作品均为 true，包括日本动画、中国动画、欧美动画电影等。TMDB genres 包含 Animation (id=16) 则为 true。真人拍摄+少量CG特效的作品（如漫威电影）不算动画。'},
            {'name': 'region', 'label': '地区', 'values': ['us', 'cn', 'hk', 'tw', 'jp', 'kr', 'gb', 'fr', 'de', 'it', 'es', 'in', 'other'],
             'ai_prompt': '请判断该影视作品的主要制片国家或地区，从以下选项中选择：us（美国）、cn（中国大陆）、hk（中国香港）、tw（中国台湾）、jp（日本）、kr（韩国）、gb（英国）、fr（法国）、de（德国）、it（意大利）、es（西班牙）、in（印度）、other（其他）。'},
            {'name': 'origin_lang', 'label': '原始语言', 'values': ['zh', 'en', 'ja', 'ko', 'other'],
             'ai_prompt': '请判断该影视作品的原始语言，从以下选项中选择：zh（中文）、en（英语）、ja（日语）、ko（韩语）、other（其他语言）。'},
            {'name': 'broad_genre', 'label': '题材类型', 'values': ['horror_mystery', 'scifi_fantasy', 'war', 'action_adventure', 'comedy', 'drama_romance', 'documentary', 'music', 'kids', 'tv_show', 'other'],
             'ai_prompt': '请判断该影视作品的主要类型，从以下选项中选择风格最鲜明突出的一个：horror_mystery（恐怖/悬疑）、scifi_fantasy（科幻/奇幻）、war（战争/军事）、action_adventure（动作/冒险）、comedy（喜剧）、drama_romance（剧情/情感）、documentary（纪录/纪实）、music（音乐/演出）、kids（儿童/家庭）、tv_show（电视节目）、other（其他）。'},
        ]

        self.prompt_builder = LLMPromptBuilder(dimensions=default_dimensions)

    def load_dimensions_from_db(self, conn):
        from media_importer.features.scraping.dimension_manager import get_dimensions_for_scrape
        db_dims = get_dimensions_for_scrape(conn)
        if db_dims:
            self.prompt_builder.load_dimensions(db_dims)

    def _build_payload(self, system_prompt: str, user_content: str, model: str) -> dict:
        return _build_payload_int(self, system_prompt, user_content, model)

    def _send_request(self, url: str, payload: dict, api_key: str,
                      max_tool_rounds: int = 5) -> str:
        return _send_request_impl(self, url, payload, api_key, max_tool_rounds)

    def _inject_search(self, payload: dict, provider: str) -> None:
        return _inject_web_search_impl(self, payload, provider)

    def _classify_error(self, status_code: int, body: dict) -> Exception:
        return _classify_error_impl(status_code, body)

    def _do_call(self, system_prompt: str, user_content: str, model: str,
                 base_url: str, api_key: str, scenario: str = None) -> str:
        return _do_call_impl(self, system_prompt, user_content, model, base_url, api_key, scenario)

    def _parse_response(self, raw_text: str) -> Dict[str, Any]:
        return _parse_response_impl(self, raw_text)

    def _retry_with_fallback(self, system_prompt: str, user_content: str,
                              scene: str = None, scenario: str = None,
                              use_fast: bool = None) -> Dict[str, Any]:
        return _retry_with_fallback_impl(self, system_prompt, user_content,
                                         scene=scene, scenario=scenario,
                                         use_fast=use_fast)

    def call_with_prompt(self, system_prompt: str, user_prompt: str,
                         scene: str, scenario: str = None) -> str:
        """通用 LLM 调用入口（供 SourceCleaner 等非刮削场景使用）。

        复用 SceneStrategyResolver 的多模型 fallback 与重试逻辑；
        返回原始响应字符串（不调用 _parse_response_impl），由调用方自行解析。
        """
        return _call_with_retry_impl(self, system_prompt, user_prompt,
                                     scene=scene, scenario=scenario)

    def extract_title(self, prompt: str) -> str:
        return _extract_title_impl(self, prompt)

    def scrape(self, video_filename: str, subtitle_filenames: List[str] = None,
               conn=None) -> Dict[str, Any]:
        if subtitle_filenames is None:
            subtitle_filenames = []

        if conn:
            self.load_dimensions_from_db(conn)

        user_content_parts = [
            "视频文件名:",
            video_filename,
            ""
        ]

        if subtitle_filenames:
            user_content_parts.append("字幕文件名:")
            for sub_file in subtitle_filenames:
                user_content_parts.append(f"- {sub_file}")
        else:
            user_content_parts.append("字幕文件: 无")

        user_content = '\n'.join(user_content_parts)
        system_prompt = self.prompt_resolver.get_dimension_supplement_prompt()

        result = _retry_with_fallback_impl(self, system_prompt, user_content,
                                          scene="dimension_supplement", scenario="scrape")
        result["search_enhanced"] = self.web_search_config.should_search("scrape")
        return result

    def scrape_with_context(self, video_filename: str, subtitle_filenames: List[str],
                            provider_context: str, provider_dimensions: dict = None,
                            conn=None, provider_name: str = None,
                            exclude_dims: set = None) -> Dict[str, Any]:
        if conn:
            self.load_dimensions_from_db(conn)

        if exclude_dims is None:
            exclude_dims = set(provider_dimensions.keys()) if provider_dimensions else set()

        user_content_parts = [
            "视频文件名:",
            video_filename,
            ""
        ]

        if subtitle_filenames:
            user_content_parts.append("字幕文件名:")
            for sub_file in subtitle_filenames:
                user_content_parts.append(f"- {sub_file}")
        else:
            user_content_parts.append("字幕文件: 无")

        user_content_parts.append("")
        user_content_parts.append(provider_context)

        user_content = '\n'.join(user_content_parts)
        system_prompt = self.prompt_resolver.get_dimension_mapping_prompt()

        result = _retry_with_fallback_impl(self, system_prompt, user_content,
                                          scene="dimension_mapping", scenario="scrape")

        if provider_dimensions:
            ai_dims = result.get('dimensions', {})
            for dim_name, dim_info in provider_dimensions.items():
                ai_dims[dim_name] = dim_info
            result['dimensions'] = ai_dims

        result["search_enhanced"] = False
        return result

    def scrape_series(self, series_name: str) -> Dict[str, Any]:
        user_content = f"剧名:\n{series_name}"
        system_prompt = self.prompt_resolver.get_dimension_supplement_prompt()

        result = _retry_with_fallback_impl(self, system_prompt, user_content,
                                          scene="dimension_supplement", scenario="series_scrape")
        result["search_enhanced"] = self.web_search_config.should_search("series_scrape")
        return result

    def scrape_series_with_context(self, series_name: str, provider_context: str,
                                   provider_name: str = None) -> Dict[str, Any]:
        user_content_parts = [
            f"剧名:\n{series_name}",
            "",
            provider_context
        ]
        user_content = '\n'.join(user_content_parts)
        system_prompt = self.prompt_resolver.get_dimension_mapping_prompt()

        result = _retry_with_fallback_impl(self, system_prompt, user_content,
                                          scene="dimension_mapping", scenario="series_scrape")
        result["search_enhanced"] = False
        return result

    def tier2_correct(
        self,
        original_filename: str,
        path_context: Optional[dict] = None,
        clean_title: str = "",
        year: Optional[int] = None,
    ) -> dict:
        return _tier2_correct_impl(self, original_filename, path_context, clean_title, year)
