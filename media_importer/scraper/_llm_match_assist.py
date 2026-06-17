"""LLM match assistance implementation — extracted from LLMScraper."""
import logging
import re
import json as _json
from typing import Optional

from media_importer.scraper._llm_client_impl import _call_with_retry_impl
from media_importer.scraper.exceptions import LLMScrapeError

logger = logging.getLogger("media_importer.ai")


def _assemble_prompt(
    instruction: str, data_context: str,
    output_format: str = "", is_legacy: bool = False,
) -> str:
    if is_legacy:
        return data_context
    parts = [p for p in [instruction, output_format, data_context] if p]
    return "\n\n".join(parts)


def _build_match_assist_context(
    original_filename: str, clean_title: str, year: Optional[int],
    path_context: Optional[dict],
) -> str:
    if path_context is None:
        path_context = {}

    candidates_text = "无"
    if path_context.get("provider_candidates"):
        lines = []
        for idx, c in enumerate(path_context["provider_candidates"][:5], 1):
            score = f"⭐{c.get('vote_average', 0)}"
            pop = f"热度{int(c.get('popularity', 0))}"
            title_parts = [c.get("title", "")]
            if c.get("original_title") and c["original_title"] != c.get("title"):
                title_parts.append(f"/ {c['original_title']}")
            year_part = f" ({c['year']})" if c.get("year") else ""
            media_part = f" · {c.get('media_type', '')}"
            id_part = f" · id:{c.get('id', '')}"
            lines.append(f"{idx}. {' '.join(title_parts)}{year_part}{media_part} · {score} · {pop}{id_part}")
        candidates_text = "\n".join(lines)

    tier1_info = path_context.get("tier1_search_info", {})
    tier1_searched = tier1_info.get("searched_title", clean_title)
    tier1_year = tier1_info.get("searched_year")
    tier1_result_count = tier1_info.get("provider_results", "未知")
    tier1_candidate_type = tier1_info.get("candidate_type", "none")
    tier1_hint = (
        f"Step 1 已用 \"{tier1_searched}\""
        + (f" ({tier1_year}年)" if tier1_year else "")
        + f" 搜索 Provider，结果：{tier1_result_count}。"
    )
    if tier1_candidate_type == "none":
        tier1_hint += (
            " 这意味着 Provider 数据库里没有这个标题的作品。"
            " 如果你认为文件名确实包含影视信息，请给出你认为正确的标题（可能是英文原名、别名或更准确的译名），"
            " 程序会用你给的 corrected_title 重新搜索。"
            " 如果你也找不到替代标题，应返回 is_valid=false。"
        )
    elif tier1_candidate_type == "fuzzy":
        tier1_hint += (
            " 这些是标题不完全匹配的模糊结果，可能包含同名但不同年份/类型的作品。"
            " 请结合文件名和目录上下文判断哪条最可能匹配，填 selected_candidate_id 直接采用；"
            " 若都不匹配但你能推测正确标题，填 corrected_title 让程序重新搜索。"
        )

    parts = [
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
        "## Provider 候选（Step 1 已找到，供你参考）",
        candidates_text,
        "",
        "## Step 1 搜索结果",
        tier1_hint,
        "",
    ]
    return "\n".join(parts)


def _build_match_assist_output_format() -> str:
    parts = [
        "## 输出要求",
        "返回 JSON，不要包含任何其他文字：",
        '{"is_valid": true, "certainty": "high", "corrected_title": "...", "corrected_year": 2024, "media_type_hint": "movie", "selected_candidate_id": "637", "reason": "详细理由(200字内)", "short_reason": "≤30字总结"}',
        "",
        "若 is_valid=false：",
        '{"is_valid": false, "certainty": "", "corrected_title": "", "corrected_year": null, "media_type_hint": null, "selected_candidate_id": null, "reason": "判定理由", "short_reason": "≤30字"}',
    ]
    return "\n".join(parts)


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

    instruction = self.prompt_resolver.get_match_assist_instruction()
    is_legacy = (instruction == "")
    data_context = _build_match_assist_context(original_filename, clean_title, year, path_context)
    output_format = "" if is_legacy else _build_match_assist_output_format()
    user_content = _assemble_prompt(instruction, data_context, output_format, is_legacy)

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

        result.setdefault("is_valid", True)
        result.setdefault("selected_candidate_id", None)

        if not result.get("is_valid"):
            result["certainty"] = ""
            result["corrected_title"] = ""
            result["corrected_year"] = None
            result["media_type_hint"] = None
            result["selected_candidate_id"] = None

        if result.get("is_valid"):
            if result.get("certainty") not in ("high", "medium"):
                result["certainty"] = "medium"

        if result.get("short_reason") and len(result["short_reason"]) > 33:
            result["short_reason"] = result["short_reason"][:30] + "..."
        elif not result.get("short_reason") and result.get("reason"):
            full = result["reason"]
            result["short_reason"] = full[:30] + ("..." if len(full) > 30 else "")

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
