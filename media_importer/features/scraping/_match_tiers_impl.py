"""Match engine tier implementations — extracted from MatchEngine."""
import logging
import os as _os
from typing import List, Optional, Tuple

from media_importer.features.scraping.match_models import (
    MatchConcern,
    MatchResult,
    MatchTraceStep,
)


def _call_collect_context(self, video_path):
    """Lazy import to resolve _collect_context from match_engine at call time."""
    from media_importer.features.scraping.match_engine import MatchEngine
    return MatchEngine._collect_context(self, video_path)


# ─────────────────────────────────────────────────────────────────────────────
# 实际实现
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)


def _tier1_exact_match_impl(
    self,
    clean_title: str,
    cjk_title: str,
    year: Optional[int],
    season: Optional[int],
    episode: Optional[int],
    providers: list,
) -> Optional[MatchResult]:
    """第一级：Provider 精确匹配。"""
    trace_steps = []
    title_matcher = self.title_matcher

    for provider in providers:
        search_titles = []
        if cjk_title:
            search_titles.append(cjk_title)
        if clean_title and clean_title != cjk_title:
            search_titles.append(clean_title)
        if not search_titles and clean_title:
            search_titles.append(clean_title)

        for search_title in search_titles:
            try:
                search_result = provider.search(search_title, year=year)
            except Exception as e:
                logger.warning(f"Provider {provider.__class__.__name__} 搜索失败: {e}")
                continue

            if not search_result or not search_result.items:
                continue

            items = search_result.items

            exact_matches = []
            for item in items:
                match_result = title_matcher.match_standard(
                    clean_title, item, year, season
                )
                if match_result.level in ("L1", "L2"):
                    exact_matches.append((item, match_result))
                elif match_result.level == "L3" and year is None:
                    exact_matches.append((item, match_result))

            if len(exact_matches) == 1:
                item, match_result = exact_matches[0]
                trace_steps.append(MatchTraceStep(
                    tier=1,
                    name="Provider精确匹配",
                    matched=True,
                    search_query=f"{search_title} (year={year})",
                    match_level=match_result.level,
                    reason=f"唯一精确匹配: {item.title}",
                ))
                return MatchResult(
                    match_level="AUTO_PASS",
                    provider_id=item.item_id,
                    provider_title=item.title,
                    match_tier=1,
                    trace_steps=trace_steps,
                    confirm_reason=f"标题精确匹配({match_result.level})，年份{'一致' if year else '无但唯一'}",
                )

            elif len(exact_matches) > 1:
                self._pending_concerns.append(MatchConcern(
                    code="NO_YEAR_MULTI_MATCH",
                    message=f"找到 {len(exact_matches)} 部同名作品",
                    detail=f"搜索 '{search_title}' 返回 {len(exact_matches)} 条精确匹配",
                ))
                trace_steps.append(MatchTraceStep(
                    tier=1,
                    name="Provider精确匹配",
                    matched=False,
                    search_query=f"{search_title} (year={year})",
                    reason=f"多个精确匹配({len(exact_matches)}条)，无法自动确定",
                ))

            else:
                if year and search_result and search_result.items:
                    self._pending_concerns.append(MatchConcern(
                        code="FUZZY_TITLE",
                        message="标题不完全匹配，最高相似度不足",
                        detail=f"搜索 '{search_title}' 无精确匹配",
                    ))
                trace_steps.append(MatchTraceStep(
                    tier=1,
                    name="Provider精确匹配",
                    matched=False,
                    search_query=f"{search_title} (year={year})",
                    reason="无精确匹配",
                ))

    if not trace_steps:
        self._pending_concerns.append(MatchConcern(
            code="NO_PROVIDER_RESULT",
            message="刮削源未找到匹配作品",
            detail="",
        ))
        trace_steps.append(MatchTraceStep(
            tier=1,
            name="Provider精确匹配",
            matched=False,
            reason="所有 Provider 搜索无结果",
        ))

    self._pending_trace = trace_steps
    return None


def _tier2_high_certainty_impl(
    self,
    corrected_title: str,
    corrected_year: Optional[int],
    media_type_hint: Optional[str],
    providers: list,
    ai_reason: str,
    concerns: list,
    trace_steps: list,
) -> Optional[MatchResult]:
    """AI 高确定性：用纠正后的标题搜 Provider → CONTEXT_PASS。"""
    candidates = _search_providers_impl(self.title_matcher, corrected_title, corrected_year, providers)
    if candidates:
        selected = candidates[0]
        trace_steps.append(MatchTraceStep(
            tier=2,
            name="上下文辅助匹配(高确定性)",
            matched=True,
            search_query=f"{corrected_title} (year={corrected_year})",
            reason=f"AI高确定性纠正后搜索结果: {selected['title']}",
            ai_reason=ai_reason,
        ))
        return MatchResult(
            match_level="CONTEXT_PASS",
            provider_id=selected.get("id"),
            provider_title=selected.get("title", ""),
            match_tier=2,
            concerns=concerns,
            trace_steps=trace_steps,
            candidates=candidates[:5],
            confirm_reason=f"AI高确定性纠正: {ai_reason}",
        )
    logger.warning(f"AI high certainty 但搜索结果为空，降级为 medium: {corrected_title}")
    return _tier2_medium_certainty_impl(
        self, corrected_title, corrected_year, media_type_hint,
        providers, f"高确定性但未搜到结果: {ai_reason}", concerns, trace_steps,
    )


def _tier2_medium_certainty_impl(
    self,
    corrected_title: str,
    corrected_year: Optional[int],
    media_type_hint: Optional[str],
    providers: list,
    ai_reason: str,
    concerns: list,
    trace_steps: list,
) -> Optional[MatchResult]:
    """AI 中确定性：搜 Provider → NEEDS_CONFIRM（带候选列表）。"""
    candidates = _search_providers_impl(self.title_matcher, corrected_title, corrected_year, providers)
    concerns.append(MatchConcern(
        code="AI_UNCERTAIN",
        message="AI 中等确定性，需要人工确认",
        detail=ai_reason,
    ))
    trace_steps.append(MatchTraceStep(
        tier=2,
        name="上下文辅助匹配(中确定性)",
        matched=False,
        search_query=f"{corrected_title} (year={corrected_year})",
        reason=f"AI中确定性，提供候选列表供确认: {ai_reason}",
        ai_reason=ai_reason,
    ))
    return MatchResult(
        match_level="NEEDS_CONFIRM",
        match_tier=2,
        concerns=concerns,
        trace_steps=trace_steps,
        candidates=candidates[:5],
        confirm_reason=f"AI中等确定性: {ai_reason}",
    )


def _tier2_low_certainty_impl(
    self,
    corrected_title: str,
    ai_reason: str,
    concerns: list,
    trace_steps: list,
    original_title: str = "",
) -> Optional[MatchResult]:
    """AI 低确定性：不搜 Provider → NEEDS_CONFIRM。"""
    concerns.append(MatchConcern(
        code="AI_UNCERTAIN",
        message="AI 无法确定标题，需要人工确认",
        detail=ai_reason,
    ))
    trace_steps.append(MatchTraceStep(
        tier=2,
        name="上下文辅助匹配(低确定性)",
        matched=False,
        reason=f"AI低确定性，需要人工确认: {ai_reason}",
        ai_reason=ai_reason,
    ))
    return MatchResult(
        match_level="NEEDS_CONFIRM",
        match_tier=2,
        concerns=concerns,
        trace_steps=trace_steps,
        candidates=[],
        confirm_reason=f"AI低确定性: {ai_reason}",
    )


def _search_providers_impl(title_matcher, title: str, year: Optional[int], providers: list) -> list:
    """统一搜索 Provider 返回候选列表。"""
    candidates = []
    for provider in providers:
        try:
            search_result = provider.search(title, year=year)
            if search_result and search_result.items:
                for item in search_result.items[:5]:
                    candidates.append({
                        "id": item.item_id,
                        "title": item.title,
                        "original_title": getattr(item, 'original_title', '') or '',
                        "year": item.year,
                        "media_type": item.media_type,
                        "overview": getattr(item, 'overview', '')[:100] if hasattr(item, 'overview') and getattr(item, 'overview', None) else '',
                    })
        except Exception as e:
            logger.warning(f"Provider {provider.__class__.__name__} 搜索失败: {e}")
            continue
        if candidates:
            break
    return candidates


def _tier2_context_match_impl(
    self,
    clean_title: str,
    cjk_title: str,
    year: Optional[int],
    season: Optional[int],
    episode: Optional[int],
    providers: list,
    video_path: str = "",
) -> Optional[MatchResult]:
    """第二级：上下文辅助匹配。"""
    concerns = self._pending_concerns
    trace_steps = self._pending_trace

    context = _call_collect_context(self, video_path) if video_path else {}
    original_filename = video_path or clean_title

    try:
        from media_importer.scraper.llm_scraper import LLMScraper
        llm = LLMScraper(self.config)
        ai_result = llm.tier2_correct(
            original_filename=original_filename,
            path_context=context,
            clean_title=clean_title,
            year=year,
        )
    except Exception as e:
        logger.warning(f"AI 标题纠正失败: {e}")
        concerns.append(MatchConcern(
            code="AI_UNCERTAIN",
            message="AI 标题纠正不可用",
            detail=f"AI 调用失败: {e}",
        ))
        trace_steps.append(MatchTraceStep(
            tier=2,
            name="上下文辅助匹配",
            matched=False,
            reason=f"AI 调用失败: {e}",
        ))
        self._pending_concerns = concerns
        self._pending_trace = trace_steps
        return None

    certainty = ai_result.get("certainty", "low")
    corrected_title = ai_result.get("corrected_title", clean_title) or clean_title
    corrected_year = ai_result.get("corrected_year", year)
    ai_reason = ai_result.get("reason", "")
    suggestion = ai_result.get("suggestion", corrected_title)
    media_type_hint = ai_result.get("media_type_hint")

    if certainty == "high":
        return _tier2_high_certainty_impl(
            self, corrected_title, corrected_year, media_type_hint,
            providers, ai_reason, concerns, trace_steps,
        )
    elif certainty == "medium":
        return _tier2_medium_certainty_impl(
            self, corrected_title, corrected_year, media_type_hint,
            providers, ai_reason, concerns, trace_steps,
        )
    else:
        return _tier2_low_certainty_impl(
            self, corrected_title, ai_reason, concerns, trace_steps,
            clean_title,
        )


def _collect_context_impl(source_dir: str, video_path: str) -> dict:
    """收集视频文件所在目录的上下文信息。"""
    context = {}
    parent_dir = _os.path.basename(_os.path.dirname(video_path))
    if parent_dir and parent_dir not in (".", "..", "/"):
        context["parent_folder"] = parent_dir
    dir_path = _os.path.dirname(video_path)
    if dir_path:
        try:
            siblings = [
                f for f in _os.listdir(dir_path)
                if f != _os.path.basename(video_path)
                and any(f.endswith(ext) for ext in (".mkv", ".mp4", ".avi", ".ts", ".wmv", ".flv"))
            ][:20]
            if siblings:
                context["sibling_files"] = siblings
        except OSError:
            pass
        grandparent = _os.path.basename(_os.path.dirname(dir_path))
        if grandparent and grandparent not in (".", "..", "/"):
            context["grandparent_folder"] = grandparent
    else:
        context["filename_hint"] = _os.path.basename(video_path)

    if source_dir and dir_path:
        try:
            rel_path = _os.path.relpath(dir_path, source_dir)
            if rel_path and rel_path != ".":
                context["path_segments"] = rel_path.split(_os.sep)
        except (ValueError, OSError):
            pass
    return context


def _tier3_user_confirm_impl(
    self,
    clean_title: str,
    cjk_title: str,
    year: Optional[int],
    season: Optional[int],
    episode: Optional[int],
    providers: list,
) -> MatchResult:
    """第三级：用户确认。"""
    concerns = self._pending_concerns[:]
    trace_steps = self._pending_trace[:]
    candidates = []

    for provider in providers:
        search_titles = []
        if cjk_title:
            search_titles.append(cjk_title)
        if clean_title and clean_title != cjk_title:
            search_titles.append(clean_title)
        if not search_titles and clean_title:
            search_titles.append(clean_title)

        for search_title in search_titles:
            try:
                search_result = provider.search(search_title, year=year)
                if search_result and search_result.items:
                    for item in search_result.items[:5]:
                        candidates.append({
                            "id": item.item_id,
                            "title": item.title,
                            "year": item.year,
                            "media_type": item.media_type,
                            "overview": getattr(item, 'overview', '')[:100] if hasattr(item, 'overview') else '',
                        })
            except Exception:
                continue
            if candidates:
                break
        if candidates:
            break

    trace_steps.append(MatchTraceStep(
        tier=3,
        name="用户确认",
        matched=False,
        reason="需要用户从候选列表中选择",
    ))

    if not concerns:
        concerns.append(MatchConcern(
            code="FUZZY_TITLE",
            message="无法自动匹配，需要人工确认",
            detail="",
        ))

    return MatchResult(
        match_level="NEEDS_CONFIRM",
        match_tier=3,
        concerns=concerns,
        trace_steps=trace_steps,
        candidates=candidates[:5],
        confirm_reason="；".join(c.message for c in concerns),
    )
