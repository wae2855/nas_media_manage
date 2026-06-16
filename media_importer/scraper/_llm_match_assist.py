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
    if not self.api_key and not self.fast_api_key:
        raise LLMScrapeError("AI 未配置，无法提取标题")
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

    # AI 未配置时快速返回，避免无效 HTTP 调用
    if not self.api_key and not self.fast_api_key:
        logger.info(
            f"ai.scene.business scene=match_assist skipped=no_ai_config "
            f"filename={original_filename!r}"
        )
        return {
            "corrected_title": clean_title,
            "corrected_year": year,
            "media_type_hint": None,
            "certainty": "low",
            "reason": "AI 未配置，跳过 AI 辅助匹配",
            "suggestion": clean_title,
        }

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
        '{"corrected_title": "纠正后的标题", "corrected_year": 年份或null, "media_type_hint": "movie|tv|null", "certainty": "high|medium|low", "reason": "详细判断理由（200字内）", "short_reason": "≤30字的一句话总结，供列表显示用，必须简洁", "suggestion": "建议的搜索关键词"}',
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
        result.setdefault("short_reason", "")

        # 程序兜底：若 AI 未返回 short_reason 或超长，从 reason 截前 30 字
        if not result.get("short_reason"):
            full_reason = result.get("reason", "")
            result["short_reason"] = full_reason[:30] + ("..." if len(full_reason) > 30 else "")
        elif len(result["short_reason"]) > 33:
            result["short_reason"] = result["short_reason"][:30] + "..."

        if not result["corrected_year"]:
            search_text = f"{result['reason']} {result['suggestion']}"
            year_match = re.search(r'(\d{4})\s*年|[\s\"](\d{4})[\s\"]|^(\d{4})$', search_text)
            if year_match:
                extracted_year = int(year_match.group(1) or year_match.group(2) or year_match.group(3))
                result["corrected_year"] = extracted_year

        if result["certainty"] not in ("high", "medium", "low"):
            result["certainty"] = "low"

        return result
    except Exception as e:
        msg = str(e)
        logger.warning(f"ai.scene.response scene=match_assist parse_error={msg[:100]}")
        if "unknown url type" in msg or "check the api key" in msg.lower():
            reason = "AI 连接未正确配置"
        else:
            reason = f"AI 解析失败: {msg[:200]}"
        return {
            "corrected_title": clean_title,
            "corrected_year": year,
            "media_type_hint": None,
            "certainty": "low",
            "reason": reason,
            "suggestion": clean_title,
        }