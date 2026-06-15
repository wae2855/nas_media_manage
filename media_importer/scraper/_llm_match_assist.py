"""LLM match assistance implementation — extracted from LLMScraper."""
import logging
import re
import json as _json
from typing import Optional

from media_importer.scraper._llm_client_impl import _call_with_retry_impl
from media_importer.scraper.exceptions import LLMScrapeError

logger = logging.getLogger("media_importer.ai")


def _extract_title_impl(self, prompt: str) -> str:
    logger.info(f"ai.scene.business scene=title_clean trigger=year_suspect_or_low_match prompt_len={len(prompt)}")
    system_prompt = self.prompt_resolver.get_title_clean_prompt()
    raw_response = _call_with_retry_impl(
        self,
        system_prompt,
        prompt,
        scene="title_clean",
        scenario=None,
    )
    text = raw_response.strip()
    think_match = re.search(r'</think\s*>', text, re.DOTALL)
    if think_match:
        text = text[think_match.end():].strip()
    return text


def _tier2_correct_impl(
    self,
    original_filename: str,
    path_context: Optional[dict] = None,
    clean_title: str = "",
    year: Optional[int] = None,
) -> dict:
    """AI 从原始文件名+路径上下文纠正标题（第二级匹配新方案）。"""
    if path_context is None:
        path_context = {}

    logger.info(
        f"ai.scene.business scene=match_assist trigger=tier1_no_match "
        f"filename={original_filename!r} clean_title={clean_title!r}"
    )
    system_prompt = self.prompt_resolver.get_match_assist_prompt()

    user_parts = [
        "## 待匹配文件信息",
        f"- 原始文件名: {original_filename}",
        f"- 正则参考标题: {clean_title or '无'}",
        f"- 正则参考年份: {year or '未知'}",
        "",
        "## 目录上下文",
        f"- 上级文件夹: {path_context.get('parent_folder', '无')}",
        f"- 上两级文件夹: {path_context.get('grandparent_folder', '无')}",
        f"- 路径段: {', '.join(path_context.get('path_segments', [])) if path_context.get('path_segments') else '无'}",
        f"- 同级文件: {', '.join(path_context.get('sibling_files', [])) if path_context.get('sibling_files') else '无'}",
        "",
        "## 输出要求",
        "返回 JSON，不要包含任何其他文字：",
        '{"corrected_title": "纠正后的标题", "corrected_year": 年份或null, "media_type_hint": "movie|tv|null", "certainty": "high|medium|low", "reason": "判断理由", "suggestion": "建议的搜索关键词"}',
    ]
    user_content = "\n".join(user_parts)

    try:
        raw_response = _call_with_retry_impl(
            self,
            system_prompt, user_content,
            scene="match_assist",
            scenario=None,
        )
        text = raw_response.strip()
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
        result = _json.loads(text)
        result.setdefault("corrected_title", clean_title)
        result.setdefault("corrected_year", year)
        result.setdefault("media_type_hint", None)
        result.setdefault("certainty", "low")
        result.setdefault("reason", "")
        result.setdefault("suggestion", result.get("corrected_title", clean_title))
        if result["certainty"] not in ("high", "medium", "low"):
            result["certainty"] = "low"
        return result
    except Exception as e:
        return {
            "corrected_title": clean_title,
            "corrected_year": year,
            "media_type_hint": None,
            "certainty": "low",
            "reason": f"AI 解析失败: {e}",
            "suggestion": clean_title,
        }