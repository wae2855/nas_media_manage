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
2. 对于文件名中缺失但你可以通过对这部的了解推断出的信息（如年份、类型等），
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
  ✅ 正确: title_cn="呼啸山庄", title_en="Wuthering Heights", year=2024, media_type="movie", restricted_level="17+"
  ❌ 错误: title_cn="简风暴", title_en="Wuthering Heights", year=2024, media_type="movie", restricted_level="7-12"

文件名示例：
  文件: "besthd-virgin.territory.2023.1080p.mkv"
  ✅ 正确: title_cn="七日谈", media_type="movie", restricted_level="17+"
  ❌ 错误: title_cn="童贞领地", media_type="movie", restricted_level="0-6"

文件名示例：
  文件: "Breaking.Bad.S01E01.1080p.mkv"
  ✅ 正确: title_cn="绝命毒师", title_en="Breaking Bad", year=2008, media_type="tv", season=1, episode=1, restricted_level="17+"
  ❌ 错误: title_cn="绝命制毒", title_en="Breaking Bad", year=2009, media_type="tv", season=1, episode=1, restricted_level="13-15"

文件名示例：
  文件: "Spirited.Away.2001.720p.mkv"
  ✅ 正确: title_cn="千与千寻", title_en="Spirited Away", year=2001, media_type="movie", animation="true", restricted_level="7-12", documentary="false"
  ❌ 错误: title_cn="神秘失踪", title_en="Spirited Away", year=2001, media_type="tv", restricted_level="0-6"

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

【限制级分类规则 - 非常重要】
restricted_level 分级标准（4选1）：
- "0-6": 适合0-6岁幼儿/儿童观看（幼儿动画、低龄启蒙）
- "7-12": 适合7-12岁儿童/家庭观看（合家欢动画、儿童向剧集、PG/PG-13以下）
- "13-15": 适合13-15岁青少年观看（轻度暴力/恐怖/敏感内容，PG-13或同等分级）
- "17+": 仅适合17岁以上成人观看（暴力血腥、裸露性爱、深度恐怖、美国R级或同等）

典型例子：
- "小猪佩奇" → restricted_level="0-6"
- "寻梦环游记"、"冰雪奇缘" → restricted_level="7-12"
- "复仇者联盟"、"哈利波特"系列 → restricted_level="13-15"
- "西部世界"、"绝命毒师"、"权力的游戏"、"斯巴达克斯" → restricted_level="17+"
- "呼啸山庄"2024/2025/2026 R级翻拍 → restricted_level="17+"
- 成人向动画（如 Death Note, Berserk, Goblin Slayer）→ restricted_level="17+"

【动漫分类规则 - 非常重要】
animation 判断标准（true/false）：
- true: 任何动画形式（日漫、国漫、欧美动画、动画电影）
- false: 真人拍摄的作品
注意：animation=true 的作品仍然有 media_type（movie/tv）区分。
典型例子：
- "进击的巨人" → animation=true, media_type=tv
- "千与千寻" → animation=true, media_type=movie
- "阿凡达"（真人+CG，主要为真人表演）→ animation=false

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
        # 固定维度定义（硬编码）
        self.dimensions = [
            {'name': 'media_type', 'label': '影视类型', 'values': ['movie', 'tv'], 'ai_prompt': '请判断这是电影还是电视剧（movie/tv）'},
            {'name': 'documentary', 'label': '是否纪录片', 'values': ['true', 'false'], 'ai_prompt': '请判断是否为纪录片（true/false）'},
            {'name': 'animation', 'label': '是否动漫', 'values': ['true', 'false'], 'ai_prompt': '请判断是否为动漫/动画作品（true/false）'},
            {'name': 'restricted_level', 'label': '限制级分类', 'values': ['0-6', '7-12', '13-15', '17+'], 'ai_prompt': '请判断内容的年龄分级：0-6、7-12、13-15、17+'},
        ]

        self.custom_system_prompt = llm_config.get('system_prompt', '')

        self._load_prompts_from_file()

    @staticmethod
    def _get_default_prompts() -> dict:
        """返回默认提示词（供 API 层调用，不含分隔线）"""
        sep = "\n【维度判断】\n当前需要判断的维度：\n"
        return {
            "system": LLMScraper.DEFAULT_SYSTEM_PROMPT,
            "sep": sep
        }

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

    def _build_system_prompt(self) -> str:
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

        json_schema = self._build_json_schema()
        prompt_parts.append(json.dumps(json_schema, ensure_ascii=False, indent=2))

        return '\n'.join(prompt_parts)

    def _build_json_schema(self) -> Dict[str, Any]:
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
        url = f"{self.base_url.rstrip('/')}/chat/completions"

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
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

            if not isinstance(result['confidence'], (int, float)):
                result['confidence'] = 0.5

            result['raw_info'] = raw_text
            result['low_confidence'] = result['confidence'] < self.confidence_threshold

            return result
        except json.JSONDecodeError as e:
            raise LLMScrapeError(f"JSON解析失败: {str(e)}, 原始内容: {raw_text[:200]}")

    def _retry_with_fallback(self, system_prompt: str, user_content: str) -> Dict[str, Any]:
        models_to_try = [self.model]
        if self.fallback_model and self.fallback_model != self.model:
            models_to_try.append(self.fallback_model)

        last_error = None

        for model in models_to_try:
            for attempt in range(self.max_retries):
                try:
                    raw_response = self._call_api(system_prompt, user_content, model)
                    return self._parse_response(raw_response)
                except LLMScrapeError as e:
                    last_error = e
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
                    continue

        if last_error:
            raise last_error
        raise LLMScrapeError("所有重试均失败")

    def scrape(self, video_filename: str, subtitle_filenames: List[str] = None) -> Dict[str, Any]:
        if subtitle_filenames is None:
            subtitle_filenames = []

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

    def scrape_series(self, series_name: str) -> Dict[str, Any]:
        user_content = f"剧名:\n{series_name}"
        system_prompt = self._build_series_prompt()

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
