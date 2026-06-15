"""LLM match assistance implementation — extracted from LLMScraper."""
import re
import json as _json
from typing import Dict, Any, Optional, List

from media_importer.scraper.exceptions import LLMScrapeError


def _extract_title_impl(self, prompt: str) -> str:
    system_prompt = self.prompt_resolver.get_title_clean_prompt() or (
        "你是一个影视标题提取助手。从用户给出的文件名中提取影视作品标题，只返回标题本身，不要返回任何其他内容。"
    )
    # Use self._do_call (thin wrapper) so test patches on scraper._do_call take effect.
    raw_response = self._do_call(
        system_prompt,
        prompt,
        self.fast_model,
        self.fast_base_url,
        self.fast_api_key,
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

    system_prompt = self.prompt_resolver.get_match_assist_prompt() or (
        "你是一个影视标题纠正助手。根据文件信息纠正影视标题，返回JSON格式的纠正结果。"
    )

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
        # Use self._do_call so test patches on scraper._do_call take effect.
        raw_response = self._do_call(
            system_prompt, user_content,
            self.fast_model, self.fast_base_url, self.fast_api_key,
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


def _tier2_judge_impl(
    self,
    original_filename: str,
    clean_title: str,
    cjk_title: str = "",
    year: Optional[int] = None,
    season: Optional[int] = None,
    episode: Optional[int] = None,
    context: Optional[dict] = None,
    candidates: Optional[List] = None,
) -> dict:
    """AI 建议更精确的搜索关键词（第二级关键词建议回搜）。"""
    if context is None:
        context = {}
    if candidates is None:
        candidates = []

    system_prompt = self.prompt_resolver.get_match_assist_prompt() or (
        "你是一个影视搜索关键词优化助手。根据文件信息和当前搜索结果，"
        "建议一个更精确的搜索关键词，以便在影视数据库中精确匹配。\n"
        "你必须返回合法的 JSON，不要包含任何其他文字。"
    )

    candidates_json = _json.dumps(candidates[:10], ensure_ascii=False, indent=2)

    user_parts = [
        "## 待匹配文件信息",
        f"- 文件名: {original_filename}",
        f"- 清洗标题: {clean_title}",
        f"- CJK标题: {cjk_title or '无'}",
        f"- 年份: {year or '未知'}",
        f"- 季: {season or '未知'}",
        f"- 集: {episode or '未知'}",
        "",
        "## 目录上下文",
        f"- 上级文件夹: {context.get('parent_folder', '无')}",
        f"- 上两级文件夹: {context.get('grandparent_folder', '无')}",
        f"- 同级文件: {', '.join(context.get('sibling_files', [])) if context.get('sibling_files') else '无'}",
        "",
        "## 当前搜索结果（供参考）",
        candidates_json,
        "",
        "## 输出要求",
        "返回 JSON:",
        '{"suggested_query": "精确搜索关键词", "certainty": "high", "reason": "建议原因"}',
        "",
        "建议原则：",
        "- 如果原标题已足够精确，suggested_query 可以等于 clean_title",
        "- 如果原标题含有多余信息（分辨率、编码等），去除后给出纯净标题",
        "- 如果目录上下文提供了系列名，可结合系列名和标题",
        "- 如果有年份信息，建议包含年份的搜索词",
        "- 如果当前搜索结果中已有精确匹配，certainty 设为 high",
        "- 如果无法确定，设置 certainty 为 low 并说明原因",
    ]
    user_content = "\n".join(user_parts)

    try:
        # Use self._do_call so test patches on scraper._do_call take effect.
        raw_response = self._do_call(
            system_prompt, user_content,
            self.fast_model, self.fast_base_url, self.fast_api_key,
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
        if "suggested_query" not in result:
            result["suggested_query"] = clean_title
        if "certainty" not in result:
            result["certainty"] = "low"
        if "reason" not in result:
            result["reason"] = ""
        if result["certainty"] not in ("high", "low"):
            result["certainty"] = "low"
        return result
    except Exception as e:
        return {
            "suggested_query": clean_title,
            "certainty": "low",
            "reason": f"AI 解析失败: {e}",
        }
