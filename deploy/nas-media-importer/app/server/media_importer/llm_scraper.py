#!/usr/bin/env python3
import json
import re
import time
import urllib.request
import ssl
from typing import List, Dict, Any


class LLMScrapeError(Exception):
    pass


class LLMScraper:
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
        self.dimensions = config.get('dimensions', [])

    def _build_system_prompt(self) -> str:
        prompt_parts = [
            "你是一个专业的影视信息刮削助手。",
            "请根据提供的视频文件名和字幕文件名，提取影视元数据信息。",
            "",
            "重要原则：",
            "1. 先根据文件名提取可确定的元数据（标题、分辨率、季/集编号等）。",
            "2. 对于文件名中缺失但你可以通过对这部的了解推断出的信息（如年份、类型等），",
            "   请大胆填写，不要留空。例如：看到 Breaking Bad S01E02，你应该知道这是",
            "   《绝命毒师》第一季第二集，首播年份为2008年，类型为tv，不是纪录片。",
            "3. 只有当你完全无法判断时，才将字段设为 null。",
            "4. confidence 评分应基于信息完整性：能确定标题+类型+年份的应 ≥0.9，",
            "   确定标题+类型但年份不确定的应 0.8-0.85，信息严重不足的才给低分。",
            "5. 限制级(restricted)判断标准：包含明确的暴力血腥、裸露性爱、深度恐怖等",
            "   成人内容的影视作品应标记为 restricted=yes。以下典型例子都是限制级：",
            "   - 西部世界(Westworld)：大量暴力、裸露、性爱场景 → restricted=yes",
            "   - 绝命毒师(Breaking Bad)：暴力、毒品、犯罪题材 → restricted=yes",
            "   - 权利的游戏(Game of Thrones)：暴力、裸露 → restricted=yes",
            "   - 斯巴达克斯(Spartacus)：极度暴力、大量裸露 → restricted=yes",
            "   普通剧情片、轻喜剧、动画片等通常为 restricted=no。",
            "",
            "当前需要判断的维度："
        ]

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
        prompt_parts = [
            "你是一个专业的影视信息刮削助手。",
            "请根据提供的电视剧名称，判断这部电视剧的整体属性。",
            "",
            "重要原则：",
            "1. 请基于对整部剧的了解来判断，不要针对某一集。",
            "2. 判断应覆盖整部剧的整体风格，而非某一集的特定内容。",
            "3. 限制级(restricted)判断标准：包含明确的暴力血腥、裸露性爱、深度恐怖等",
            "   成人内容的影视作品应标记为 restricted=yes。以下典型例子都是限制级：",
            "   - 西部世界(Westworld)：大量暴力、裸露、性爱场景 → restricted=yes",
            "   - 绝命毒师(Breaking Bad)：暴力、毒品、犯罪题材 → restricted=yes",
            "   - 权利的游戏(Game of Thrones)：暴力、裸露 → restricted=yes",
            "   - 斯巴达克斯(Spartacus)：极度暴力、大量裸露 → restricted=yes",
            "   普通剧情片、轻喜剧、动画片等通常为 restricted=no。",
            "",
            "当前需要判断的维度："
        ]

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
