#!/usr/bin/env python3
import json
import re
import time
import urllib.request
import ssl
from typing import List, Dict, Any, Optional

from media_importer.core.config_view import ConfigView
from .llm_prompts import LLMPromptBuilder


class LLMScrapeError(Exception):
    pass


class LLMScraper:
    DEFAULT_SYSTEM_PROMPT = LLMPromptBuilder.DEFAULT_SYSTEM_PROMPT

    def __init__(self, config: dict):
        llm_config = ConfigView.from_dict(config).llm
        self.api_key = llm_config.api_key
        self.base_url = llm_config.base_url
        self.model = llm_config.model
        self.timeout = llm_config.timeout
        self.max_retries = llm_config.max_retries
        self.retry_delay = llm_config.retry_delay
        self.fallback_model = llm_config.fallback_model or None
        self.confidence_threshold = llm_config.confidence_threshold
        self.verify_ssl = llm_config.verify_ssl

        self.fast_model = llm_config.effective_fast_model
        self.fast_base_url = llm_config.effective_fast_base_url
        self.fast_api_key = llm_config.effective_fast_api_key
        default_dimensions = [
            {'name': 'media_type', 'label': '影视类型', 'values': ['movie', 'tv'], 'ai_prompt': '请判断这是电影（movie）还是电视剧（tv）。判断依据：如果文件名中包含季集编号（如S01E01、S2E03等格式），则为电视剧（tv）；如果是完整独立的影视故事，则为电影（movie）。电视电影/网络电影仍归为movie。'},
            {'name': 'documentary', 'label': '是否纪录片', 'values': ['true', 'false'], 'ai_prompt': '请判断是否为纪录片（true/false）。纪录片是以真实事件、人物、历史、社会等为主题的非虚构影视作品，包括自然纪录片（如《地球脉动》）、历史纪录片、社会纪录片、科学纪录片等。TMDB genres 包含 Documentary (id=99) 则为 true；如 TMDB 未标注，请根据标题和简介判断。真人出演+虚构剧情的作品（如《辛德勒的名单》）应选 false。'},
            {'name': 'restricted_level', 'label': '限制级分类', 'values': ['0-6', '7-12', '13-16', '17+'], 'ai_prompt': '请判断该影视内容的年龄分级，从以下选项中选择最匹配的一个：0-6（幼儿/儿童）、7-12（家庭向）、13-16（青少年向）、17+（成人内容）。优先使用 TMDB release_dates 中的官方分级；如 TMDB 未提供，请联网搜索后判断。'},
            {'name': 'animation', 'label': '是否动漫', 'values': ['true', 'false'], 'ai_prompt': '请判断是否为动漫/动画作品（true/false）。以动画/手绘/CG形式制作的作品均为 true，包括日本动画、中国动画、欧美动画电影等。TMDB genres 包含 Animation (id=16) 则为 true。真人拍摄+少量CG特效的作品（如漫威电影）不算动画。'},
            {'name': 'region', 'label': '地区', 'values': ['us', 'cn', 'hk', 'tw', 'jp', 'kr', 'gb', 'fr', 'de', 'it', 'es', 'in', 'other'], 'ai_prompt': '请判断该影视作品的主要制片国家或地区，从以下选项中选择：us（美国）、cn（中国大陆）、hk（中国香港）、tw（中国台湾）、jp（日本）、kr（韩国）、gb（英国）、fr（法国）、de（德国）、it（意大利）、es（西班牙）、in（印度）、other（其他）。'},
            {'name': 'origin_lang', 'label': '原始语言', 'values': ['zh', 'en', 'ja', 'ko', 'other'], 'ai_prompt': '请判断该影视作品的原始语言，从以下选项中选择：zh（中文）、en（英语）、ja（日语）、ko（韩语）、other（其他语言）。'},
            {'name': 'broad_genre', 'label': '题材类型', 'values': ['horror_mystery', 'scifi_fantasy', 'war', 'action_adventure', 'comedy', 'drama_romance', 'documentary', 'music', 'kids', 'tv_show', 'other'], 'ai_prompt': '请判断该影视作品的主要类型，从以下选项中选择风格最鲜明突出的一个：horror_mystery（恐怖/悬疑）、scifi_fantasy（科幻/奇幻）、war（战争/军事）、action_adventure（动作/冒险）、comedy（喜剧）、drama_romance（剧情/情感）、documentary（纪录/纪实）、music（音乐/演出）、kids（儿童/家庭）、tv_show（电视节目）、other（其他）。'},
        ]

        custom_system_prompt = llm_config.system_prompt

        self.prompt_builder = LLMPromptBuilder(
            dimensions=default_dimensions,
            custom_system_prompt=custom_system_prompt,
        )

    def load_dimensions_from_db(self, conn):
        from .dimension_manager import get_dimensions_for_scrape
        db_dims = get_dimensions_for_scrape(conn)
        if db_dims:
            self.prompt_builder.load_dimensions(db_dims)

    @staticmethod
    def _get_default_prompts() -> dict:
        return LLMPromptBuilder._get_default_prompts()

    @staticmethod
    def _get_default_provider_prompt(provider_type='tmdb') -> str:
        return LLMPromptBuilder._get_default_provider_prompt(provider_type)

    @staticmethod
    def _get_default_tmdb_prompt() -> str:
        return LLMPromptBuilder._get_default_tmdb_prompt()

    def _call_api(self, system_prompt: str, user_content: str, model: str) -> str:
        return self._do_call(system_prompt, user_content, model,
                             self.base_url, self.api_key)

    def _call_fast_api(self, system_prompt: str, user_content: str) -> str:
        return self._do_call(system_prompt, user_content, self.fast_model,
                             self.fast_base_url, self.fast_api_key)

    def _do_call(self, system_prompt: str, user_content: str, model: str,
                 base_url: str, api_key: str) -> str:
        url = f"{base_url.rstrip('/')}/chat/completions"

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }

        payload = {
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_content}
            ],
            'temperature': 0.3
        }

        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')

        try:
            if self.verify_ssl:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    response_data = response.read().decode('utf-8')
                    result = json.loads(response_data)
                    return result['choices'][0]['message']['content']
            else:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as response:
                    response_data = response.read().decode('utf-8')
                    result = json.loads(response_data)
                    return result['choices'][0]['message']['content']
        except Exception as e:
            raise LLMScrapeError(f"API请求失败: {str(e)}")

    def _parse_response(self, raw_text: str) -> Dict[str, Any]:
        try:
            text = raw_text.strip()

            think_match = re.search(r'</think\s*>', text, re.DOTALL)
            if think_match:
                text = text[think_match.end():].strip()

            if text.startswith('```json'):
                text = text[7:]
            if text.endswith('```'):
                text = text[:-3]
            text = text.strip()

            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                text = json_match.group(0)

            result = json.loads(text)

            required_fields = ['title_cn', 'title_en', 'year', 'type', 'confidence']
            for field in required_fields:
                if field not in result:
                    result[field] = None

            for field in ['resolution', 'quality', 'language', 'season', 'episode']:
                if field not in result:
                    result[field] = None

            if 'dimensions' not in result:
                result['dimensions'] = {}

            known_dim_names = {d['name'] for d in self.prompt_builder.dimensions if d.get('name')}
            if known_dim_names and isinstance(result['dimensions'], dict):
                result['dimensions'] = {
                    k: v for k, v in result['dimensions'].items()
                    if k in known_dim_names
                }

            if not isinstance(result['confidence'], (int, float)):
                result['confidence'] = 0.5

            result['raw_info'] = raw_text
            result['low_confidence'] = result['confidence'] < self.confidence_threshold

            return result
        except json.JSONDecodeError as e:
            raise LLMScrapeError(f"JSON解析失败: {str(e)}, 原始内容: {raw_text[:200]}")

    def _retry_with_fallback(self, system_prompt: str, user_content: str,
                              use_fast: bool = False) -> Dict[str, Any]:
        if use_fast:
            models_to_try = [self.fast_model]
            call_fn = self._call_fast_api
        else:
            models_to_try = [self.model]
            if self.fallback_model and self.fallback_model != self.model:
                models_to_try.append(self.fallback_model)
            call_fn = self._call_api

        last_error = None

        for model in models_to_try:
            for attempt in range(self.max_retries):
                try:
                    if use_fast:
                        raw_response = call_fn(system_prompt, user_content)
                    else:
                        raw_response = call_fn(system_prompt, user_content, model)
                    return self._parse_response(raw_response)
                except LLMScrapeError as e:
                    last_error = e
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
                    continue

        if last_error:
            raise last_error
        raise LLMScrapeError("所有重试均失败")

    def extract_title(self, prompt: str) -> str:
        raw_response = self._call_fast_api(
            "你是一个影视标题提取助手。从用户给出的文件名中提取影视作品标题，只返回标题本身，不要返回任何其他内容。",
            prompt
        )
        text = raw_response.strip()
        think_match = re.search(r'</think\s*>', text, re.DOTALL)
        if think_match:
            text = text[think_match.end():].strip()
        return text

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
        system_prompt = self.prompt_builder._build_system_prompt()

        return self._retry_with_fallback(system_prompt, user_content)

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
        system_prompt = self.prompt_builder._build_system_prompt_with_provider(exclude_dims=exclude_dims, provider_name=provider_name)

        result = self._retry_with_fallback(system_prompt, user_content, use_fast=True)

        if provider_dimensions:
            ai_dims = result.get('dimensions', {})
            for dim_name, dim_info in provider_dimensions.items():
                ai_dims[dim_name] = dim_info
            result['dimensions'] = ai_dims

        return result

    def scrape_series(self, series_name: str) -> Dict[str, Any]:
        user_content = f"剧名:\n{series_name}"
        system_prompt = self.prompt_builder._build_series_prompt()

        return self._retry_with_fallback(system_prompt, user_content)

    def scrape_series_with_context(self, series_name: str, provider_context: str,
                                   provider_name: str = None) -> Dict[str, Any]:
        user_content_parts = [
            f"剧名:\n{series_name}",
            "",
            provider_context
        ]
        user_content = '\n'.join(user_content_parts)
        system_prompt = self.prompt_builder._build_series_prompt_with_provider(provider_name=provider_name)

        return self._retry_with_fallback(system_prompt, user_content)
