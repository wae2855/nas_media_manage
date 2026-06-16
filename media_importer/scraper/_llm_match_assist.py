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

    # 渲染 Provider 候选列表
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
        "## Provider 候选（Step 1 已找到，供你参考）",
        candidates_text,
        "",
        "## 判定规则",
        "",
        "### 第一步：判断 is_valid（文件名是否包含可识别影视信息）",
        "",
        "返回 false 的情况（宁可保守）：",
        "1. 文件名为随机字符或乱码：如 123uyyt、asdfgh、855、yyu",
        "2. 文件名为纯通用名词，对应影视过多无法具体指向：",
        '   - 单字词："消防"、"大楼"、"飞机"、"爱情"',
        '   - 通用短语："我的女神"、"那些日子"（对应几十部作品）',
        '3. 文件名明显非影视内容：如 "新建文件夹"、"未命名"、"sample"',
        "",
        "返回 true 的情况：",
        "- 包含具体片名（中文译名或原文）",
        "- 含影视特征任一：年份(2024)、季集(S01E01)、画质(1080p)、人名",
        "",
        "候选数量影响：",
        "- 同名候选 ≥ 3 部 → 倾向 is_valid=false（歧义太大）",
        "- 同名候选唯一且高分 → 倾向 is_valid=true + certainty=high",
        "",
        "### 第二步：若 is_valid=true，判断 certainty",
        "",
        "- high: 高度确信是某部具体作品（明确译名、含年份+片名、候选首位完美匹配）",
        "- medium: 有合理猜测但无法 100% 确定（同名多版本缺年份、翻译有歧义）",
        "- low: 不应出现。若 is_valid=true 但完全无法推测，应该返回 is_valid=false",
        "",
        "### 第三步：候选利用规则",
        "",
        "- 若 Step 1 候选中已有完美匹配项：填 selected_candidate_id（候选的 provider_id），程序直接采用",
        "- 若候选都不匹配但你能推测：填 corrected_title + corrected_year，程序重新搜 Provider",
        "- 若 is_valid=false：所有其他字段留空/null",
        "",
        "## 关键要求",
        "- 无论 certainty 是 high 还是 medium，都必须填写 corrected_title 和 corrected_year",
        "- corrected_title 至少应等于 clean_title（不要空着）",
        "- 如果 reason 中提到具体年份（如'2004年王家卫'），corrected_year 必须填写该年份，不能留 null",
        "- certainty 只决定'是否自动入库'，不是你'能不能给出建议'",
        "- 即使同时匹配多部同名作品（medium），也要给出你认为最可能的标题和年份",
        "",
        "## 输出要求",
        "返回 JSON，不要包含任何其他文字：",
        '{"is_valid": true, "certainty": "high", "corrected_title": "...", "corrected_year": 2024, "media_type_hint": "movie", "selected_candidate_id": "637", "reason": "详细理由(200字内)", "short_reason": "≤30字总结"}',
        "",
        "若 is_valid=false：",
        '{"is_valid": false, "certainty": "", "corrected_title": "", "corrected_year": null, "media_type_hint": null, "selected_candidate_id": null, "reason": "判定理由", "short_reason": "≤30字"}',
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

        # Phase P 新增字段
        result.setdefault("is_valid", True)
        result.setdefault("selected_candidate_id", None)

        # 防御：is_valid=false 时强制清空其他字段
        if not result.get("is_valid"):
            result["certainty"] = ""
            result["corrected_title"] = ""
            result["corrected_year"] = None
            result["media_type_hint"] = None
            result["selected_candidate_id"] = None

        # 防御：is_valid=true 但 certainty 异常
        if result.get("is_valid"):
            if result.get("certainty") not in ("high", "medium"):
                result["certainty"] = "medium"

        # short_reason 长度兜底
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