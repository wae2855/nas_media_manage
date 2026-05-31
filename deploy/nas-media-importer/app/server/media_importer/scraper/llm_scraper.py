#!/usr/bin/env python3
import json
import re
import time
import urllib.request
import ssl
import os
from typing import List, Dict, Any, Optional


class LLMScrapeError(Exception):
    pass


class LLMScraper:
    DEFAULT_SYSTEM_PROMPT = """你是一个专业的影视信息刮削助手。
请根据提供的视频文件名和字幕文件名，提取影视元数据信息。

重要原则：
1. 先根据文件名提取可确定的元数据（标题、分辨率、季/集编号等）。
2. 对于文件名中缺失但你可以通过对这部作品的了解推断出的信息（如年份、类型等），
   请大胆填写，不要留空。例如：看到 Breaking Bad S01E02，你应该知道这是
   《绝命毒师》第一季第二集，首播年份为2008年，类型为tv，不是纪录片。
3. 只有当你完全无法判断时，才将字段设为 null。
4. confidence 评分应基于信息完整性：能确定标题+类型+年份的应 ≥0.9，
   确定标题+类型但年份不确定的应 0.8-0.85，信息严重不足的才给低分。

【数据源优先级 - 非常重要】
刮削时请优先参考以下权威数据源（按优先级从高到低）：
1. 豆瓣 (douban.com) - 中文影视信息最全面权威，优先参考中文译名、评分、分类
2. TMDB (themoviedb.org) - 全球影视元数据标准，辅助验证
3. IMDb (imdb.com) - 英语影视信息参考
4. 维基百科 - 辅助验证年代、分类等基础信息
5. 其他粉丝站点 - 仅供小众作品参考

注意事项：
- 对于中文影视，优先以豆瓣信息为准
- 若各数据源信息不一致，优先信任官方数据
- 对于年代久远或小众作品，可参考粉丝站点
- AI可能产生"幻觉"，请交叉验证关键信息

【正确与错误刮削示例】
文件名示例：
  文件: "Wuthering.Heights.2024.1080p.BluRay.x264.mkv"
  ✅ 正确: title_cn="呼啸山庄", title_en="Wuthering Heights", year=2024
  ❌ 错误: title_cn="简风暴", title_en="Wuthering Heights", year=2024

文件名示例：
  文件: "besthd-virgin.territory.2023.1080p.mkv"
  ✅ 正确: title_cn="七日谈"
  ❌ 错误: title_cn="童贞领地"

文件名示例：
  文件: "Breaking.Bad.S01E01.1080p.mkv"
  ✅ 正确: title_cn="绝命毒师", title_en="Breaking Bad", year=2008, season=1, episode=1
  ❌ 错误: title_cn="绝命制毒", year=2009

文件名示例：
  文件: "Spirited.Away.2001.720p.mkv"
  ✅ 正确: title_cn="千与千寻", title_en="Spirited Away", year=2001
  ❌ 错误: title_cn="神秘失踪"

【标题翻译规则 - 非常重要】
- 对于已知的影视作品，请使用官方中文译名，不要直译英文标题
- 常见经典作品的正确译名：
  * Wuthering Heights → 呼啸山庄（不是"简风暴"或"呼啸的山丘"）
  * besthd-virgin.territory → 七日谈（成人系列频道，非直译"童贞领地"）
  * Spirited Away → 千与千寻（不是"神秘失踪"）
  * Inception → 盗梦空间（不是"奠基"）
  * Interstellar → 星际穿越（不是"星际"）
  * 各种成人影视/系列请使用其公认的中文名称
- 如果不确定某个标题的官方译名，可以：
  1. 尝试搜索对应的中文名称
  2. 使用常见的意译名称
  3. 切勿机械直译导致歧义

【维度判断】
当前需要判断的维度："""

    TMDB_CONTEXT_PROMPT = """你是一个专业的影视信息整理助手。
系统已通过 TMDb API 获取到该影视作品的元数据，请基于这些数据整理为系统所需的格式化信息。

重要原则：
1. TMDb 数据是优先参考来源，标题、年份、类型等基础信息优先采用 TMDb 数据。
2. 若 TMDb 数据不完整或存疑（如缺少某些维度信息、类型标签不够精确），请结合你的知识进行补充判断。例如：TMDb 可能未明确标注是否动漫，但你可以根据作品信息自行判断。
3. 如果 TMDb 数据与文件名信息有冲突，以 TMDb 数据为准，但季/集编号以文件名为准。

【维度判断规则 - 请严格遵循】
以下维度的 TMDB 映射数据已自动提取为参考（如为 null 表示 TMDB 未提供），请对每个维度给出判断：
- 是否纪录片：TMDB genres 包含 Documentary (id=99) 则为 true，无此标签但有其他 genres 则为 false
- 是否动漫：TMDB genres 包含 Animation (id=16) 则为 true
- 限制级分类：优先使用 TMDB release_dates 中的官方分级（如 MPAA R、PG-13 等），其次参考 adult 标记；如 TMDB 未提供分级，请联网搜索该影视的官方分级后判断

【维度判断】
当前需要判断的维度："""

    def __init__(self, config: dict):
        llm_config = config.get('llm', {})
        self.api_key = llm_config.get('api_key', '')
        self.base_url = llm_config.get('base_url', 'https://api.openai.com/v1')
        self.model = llm_config.get('model', 'gpt-3.5-turbo')
        self.timeout = llm_config.get('timeout', 30)
        self.max_retries = llm_config.get('max_retries', 2)
        self.retry_delay = llm_config.get('retry_delay', 3)
        self.fallback_model = llm_config.get('fallback_model')
        self.confidence_threshold = llm_config.get('confidence_threshold', 0.8)
        self.verify_ssl = llm_config.get('verify_ssl', True)

        self.fast_model = llm_config.get('fast_model') or self.fallback_model or self.model
        self.fast_base_url = llm_config.get('fast_base_url') or self.base_url
        self.fast_api_key = llm_config.get('fast_api_key') or self.api_key
        self.dimensions = [
            {'name': 'media_type', 'label': '影视类型', 'values': ['movie', 'tv'], 'ai_prompt': '请判断这是电影（movie）还是电视剧（tv）。判断依据：如果文件名中包含季集编号（如S01E01、S2E03等格式），则为电视剧（tv）；如果是完整独立的影视故事，则为电影（movie）。电视电影/网络电影仍归为movie。'},
            {'name': 'documentary', 'label': '是否纪录片', 'values': ['true', 'false'], 'ai_prompt': '请判断是否为纪录片（true/false）。纪录片是以真实事件、人物、历史、社会等为主题的非虚构影视作品，包括自然纪录片（如《地球脉动》）、历史纪录片、社会纪录片、科学纪录片等。TMDB genres 包含 Documentary (id=99) 则为 true；如 TMDB 未标注，请根据标题和简介判断。真人出演+虚构剧情的作品（如《辛德勒的名单》）应选 false。'},
            {'name': 'restricted_level', 'label': '限制级分类', 'values': ['0-6', '7-12', '13-16', '17+'], 'ai_prompt': '请判断该影视内容的年龄分级，从以下选项中选择最匹配的一个：0-6（幼儿/儿童）、7-12（家庭向）、13-16（青少年向）、17+（成人内容）。优先使用 TMDB release_dates 中的官方分级；如 TMDB 未提供，请联网搜索后判断。'},
            {'name': 'animation', 'label': '是否动漫', 'values': ['true', 'false'], 'ai_prompt': '请判断是否为动漫/动画作品（true/false）。以动画/手绘/CG形式制作的作品均为 true，包括日本动画、中国动画、欧美动画电影等。TMDB genres 包含 Animation (id=16) 则为 true。真人拍摄+少量CG特效的作品（如漫威电影）不算动画。'},
            {'name': 'region', 'label': '地区', 'values': ['us', 'cn', 'hk', 'tw', 'jp', 'kr', 'gb', 'fr', 'de', 'it', 'es', 'in', 'other'], 'ai_prompt': '请判断该影视作品的主要制片国家或地区，从以下选项中选择：us（美国）、cn（中国大陆）、hk（中国香港）、tw（中国台湾）、jp（日本）、kr（韩国）、gb（英国）、fr（法国）、de（德国）、it（意大利）、es（西班牙）、in（印度）、other（其他）。'},
            {'name': 'origin_lang', 'label': '原始语言', 'values': ['zh', 'en', 'ja', 'ko', 'other'], 'ai_prompt': '请判断该影视作品的原始语言，从以下选项中选择：zh（中文）、en（英语）、ja（日语）、ko（韩语）、other（其他语言）。'},
            {'name': 'broad_genre', 'label': '题材类型', 'values': ['horror_mystery', 'scifi_fantasy', 'war', 'action_adventure', 'comedy', 'drama_romance', 'documentary', 'music', 'kids', 'tv_show', 'other'], 'ai_prompt': '请判断该影视作品的主要类型，从以下选项中选择风格最鲜明突出的一个：horror_mystery（恐怖/悬疑）、scifi_fantasy（科幻/奇幻）、war（战争/军事）、action_adventure（动作/冒险）、comedy（喜剧）、drama_romance（剧情/情感）、documentary（纪录/纪实）、music（音乐/演出）、kids（儿童/家庭）、tv_show（电视节目）、other（其他）。'},
        ]

        self.custom_system_prompt = llm_config.get('system_prompt', '')

        self._load_prompts_from_file()

        self.custom_tmdb_prompt = ''
        self._load_tmdb_prompts_from_file()

    def load_dimensions_from_db(self, conn):
        from .dimension_manager import get_dimensions_for_scrape
        db_dims = get_dimensions_for_scrape(conn)
        if db_dims:
            self.dimensions = db_dims

    @staticmethod
    def _get_default_prompts() -> dict:
        """返回默认提示词（供 API 层调用，不含分隔线）"""
        sep = "\n【维度判断】\n当前需要判断的维度：\n"
        return {
            "system": LLMScraper.DEFAULT_SYSTEM_PROMPT,
            "sep": sep
        }

    @staticmethod
    def _get_default_tmdb_prompt() -> str:
        """返回默认 TMDB 版提示词（供 API 层调用，不含分隔线）"""
        sep = "【维度判断】\n当前需要判断的维度："
        prompt = LLMScraper.TMDB_CONTEXT_PROMPT
        if prompt.endswith(sep):
            prompt = prompt[:-len(sep)]
        return prompt.strip()

    def _load_prompts_from_file(self):
        """
        从配置文件加载用户自定义提示词（仅上半部）
        优先级：scraper_prompts.md > scraper_prompts.example.md > 代码内置默认值
        """
        possible_paths = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'scraper_prompts.md'),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'config', 'scraper_prompts.md'),
            '/vol3/@appdata/nas-media-importer/config/scraper_prompts.md',
        ]
        example_paths = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'scraper_prompts.example.md'),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'config', 'scraper_prompts.example.md'),
            '/vol3/@appdata/nas-media-importer/config/scraper_prompts.example.md',
        ]

        SEP = "【维度判断】\n当前需要判断的维度："

        prompts_file = None
        for path in possible_paths:
            if os.path.exists(path):
                prompts_file = path
                break

        if prompts_file is None:
            for path in example_paths:
                if os.path.exists(path):
                    prompts_file = path
                    break

        if prompts_file is None:
            return

        try:
            import yaml
            with open(prompts_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if data and isinstance(data, dict):
                sp = (data.get('system_prompt') or '').strip()

                if SEP in sp:
                    sp = sp.split(SEP)[0].strip()

                if sp:
                    self.custom_system_prompt = sp
        except Exception:
            pass

    def _load_tmdb_prompts_from_file(self):
        possible_paths = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'tmdb_prompts.md'),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'config', 'tmdb_prompts.md'),
            '/vol3/@appdata/nas-media-importer/config/tmdb_prompts.md',
        ]
        SEP = "【维度判断】\n当前需要判断的维度："

        prompts_file = None
        for path in possible_paths:
            if os.path.exists(path):
                prompts_file = path
                break

        if prompts_file is None:
            return

        try:
            import yaml
            with open(prompts_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if data and isinstance(data, dict):
                sp = (data.get('system_prompt') or '').strip()

                if SEP in sp:
                    sp = sp.split(SEP)[0].strip()

                if sp:
                    self.custom_tmdb_prompt = sp
        except Exception:
            pass

    def _build_system_prompt(self, exclude_dims: set = None) -> str:
        SEP = "【维度判断】\n当前需要判断的维度："

        if self.custom_system_prompt:
            base = self.custom_system_prompt
        else:
            base = self.DEFAULT_SYSTEM_PROMPT

        if base.endswith(SEP):
            base = base[:-len(SEP)]

        prompt_parts = [base, "", SEP, ""]

        dims = [d for d in self.dimensions if d.get('name') not in (exclude_dims or set())]
        for i, dim in enumerate(dims, 1):
            name = dim.get('name', '')
            label = dim.get('label', name)
            values = dim.get('values', [])
            values_str = ', '.join(str(v) for v in values) if values else ''
            ai_hint = dim.get('ai_prompt', '')
            if ai_hint:
                prompt_parts.append(f"{i}. {label}（{name}）: [{values_str}] — {ai_hint}")
            else:
                prompt_parts.append(f"{i}. {label}（{name}）: [{values_str}]")

        prompt_parts.append("")
        prompt_parts.append("请严格按以下JSON格式返回，不要添加任何解释文字：")

        json_schema = self._build_json_schema(exclude_dims)
        prompt_parts.append(json.dumps(json_schema, ensure_ascii=False, indent=2))

        return '\n'.join(prompt_parts)

    def _build_system_prompt_with_context(self, exclude_dims: set = None) -> str:
        SEP = "【维度判断】\n当前需要判断的维度："

        if self.custom_tmdb_prompt:
            base = self.custom_tmdb_prompt
        else:
            base = self.TMDB_CONTEXT_PROMPT

        if base.endswith(SEP):
            base = base[:-len(SEP)]

        prompt_parts = [base, "", SEP, ""]

        dims = [d for d in self.dimensions if d.get('name') not in (exclude_dims or set())]
        for i, dim in enumerate(dims, 1):
            name = dim.get('name', '')
            label = dim.get('label', name)
            values = dim.get('values', [])
            values_str = ', '.join(str(v) for v in values) if values else ''
            ai_hint = dim.get('ai_prompt', '')
            if ai_hint:
                prompt_parts.append(f"{i}. {label}（{name}）: [{values_str}] — {ai_hint}")
            else:
                prompt_parts.append(f"{i}. {label}（{name}）: [{values_str}]")

        prompt_parts.append("")
        prompt_parts.append("请严格按以下JSON格式返回，不要添加任何解释文字：")

        json_schema = self._build_json_schema(exclude_dims)
        prompt_parts.append(json.dumps(json_schema, ensure_ascii=False, indent=2))

        return '\n'.join(prompt_parts)

    def _build_json_schema(self, exclude_dims: set = None) -> Dict[str, Any]:
        dimensions_schema = {}
        for dim in self.dimensions:
            name = dim.get('name')
            if exclude_dims and name in exclude_dims:
                continue
            values = dim.get('values', [])
            if values:
                dimensions_schema[name] = f"{'|'.join(str(v) for v in values)}|null"
            else:
                dimensions_schema[name] = "string|null"

        schema = {
            "title_cn": "string|null",
            "title_en": "string|null",
            "year": "int|null",
            "resolution": "string|null",
            "quality": "string|null",
            "language": "string|null",
            "type": "movie|tv",
            "season": "int|null",
            "episode": "int|null",
            "dimensions": dimensions_schema,
            "confidence": "float"
        }

        return schema

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

            known_dim_names = {d['name'] for d in self.dimensions if d.get('name')}
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
        system_prompt = self._build_system_prompt()

        return self._retry_with_fallback(system_prompt, user_content)

    def scrape_with_context(self, video_filename: str, subtitle_filenames: List[str],
                            tmdb_context: str, tmdb_dimensions: dict = None,
                            conn=None) -> Dict[str, Any]:
        if conn:
            self.load_dimensions_from_db(conn)

        exclude_dims = set(tmdb_dimensions.keys()) if tmdb_dimensions else set()

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
        user_content_parts.append(tmdb_context)

        user_content = '\n'.join(user_content_parts)
        system_prompt = self._build_system_prompt_with_context(exclude_dims=exclude_dims)

        result = self._retry_with_fallback(system_prompt, user_content, use_fast=True)

        if tmdb_dimensions:
            ai_dims = result.get('dimensions', {})
            for dim_name, dim_info in tmdb_dimensions.items():
                ai_dims[dim_name] = dim_info
            result['dimensions'] = ai_dims

        return result

    def scrape_series(self, series_name: str) -> Dict[str, Any]:
        user_content = f"剧名:\n{series_name}"
        system_prompt = self._build_series_prompt()

        return self._retry_with_fallback(system_prompt, user_content)

    def scrape_series_with_context(self, series_name: str, tmdb_context: str) -> Dict[str, Any]:
        user_content_parts = [
            f"剧名:\n{series_name}",
            "",
            tmdb_context
        ]
        user_content = '\n'.join(user_content_parts)
        system_prompt = self._build_series_prompt_with_context()

        return self._retry_with_fallback(system_prompt, user_content)

    def _build_series_prompt(self) -> str:
        """电视剧系列刮削提示词：复用同一份用户提示词，仅 JSON Schema 不同"""
        SEP = "【维度判断】\n当前需要判断的维度："

        if self.custom_system_prompt:
            base = self.custom_system_prompt
        else:
            base = self.DEFAULT_SYSTEM_PROMPT

        if base.endswith(SEP):
            base = base[:-len(SEP)]

        prompt_parts = [base, "", SEP, ""]

        for i, dim in enumerate(self.dimensions, 1):
            name = dim.get('name', '')
            label = dim.get('label', name)
            values = dim.get('values', [])
            values_str = ', '.join(str(v) for v in values) if values else ''
            prompt_parts.append(f"{i}. {label}（{name}）: [{values_str}]")

        prompt_parts.append("")
        prompt_parts.append("请严格按以下JSON格式返回，不要添加任何解释文字：")

        dimensions_schema = {}
        for dim in self.dimensions:
            name = dim.get('name')
            values = dim.get('values', [])
            if values:
                dimensions_schema[name] = f"{'|'.join(str(v) for v in values)}|null"
            else:
                dimensions_schema[name] = "string|null"

        schema = {
            "title_cn": "string|null",
            "title_en": "string|null",
            "year": "int|null",
            "type": "tv",
            "dimensions": dimensions_schema,
            "confidence": "float"
        }

        prompt_parts.append(json.dumps(schema, ensure_ascii=False, indent=2))

        return '\n'.join(prompt_parts)

    def _build_series_prompt_with_context(self) -> str:
        SEP = "【维度判断】\n当前需要判断的维度："

        base = self.TMDB_CONTEXT_PROMPT

        if base.endswith(SEP):
            base = base[:-len(SEP)]

        prompt_parts = [base, "", SEP, ""]

        for i, dim in enumerate(self.dimensions, 1):
            name = dim.get('name', '')
            label = dim.get('label', name)
            values = dim.get('values', [])
            values_str = ', '.join(str(v) for v in values) if values else ''
            prompt_parts.append(f"{i}. {label}（{name}）: [{values_str}]")

        prompt_parts.append("")
        prompt_parts.append("请严格按以下JSON格式返回，不要添加任何解释文字：")

        dimensions_schema = {}
        for dim in self.dimensions:
            name = dim.get('name')
            values = dim.get('values', [])
            if values:
                dimensions_schema[name] = f"{'|'.join(str(v) for v in values)}|null"
            else:
                dimensions_schema[name] = "string|null"

        schema = {
            "title_cn": "string|null",
            "title_en": "string|null",
            "year": "int|null",
            "type": "tv",
            "dimensions": dimensions_schema,
            "confidence": "float"
        }

        prompt_parts.append(json.dumps(schema, ensure_ascii=False, indent=2))

        return '\n'.join(prompt_parts)
