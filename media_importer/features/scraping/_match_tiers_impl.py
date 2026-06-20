"""Match engine tier implementations — extracted from MatchEngine."""
import logging
import os as _os
from typing import List, Optional, Tuple, Union

from media_importer.features.scraping.match_models import (
    MatchConcern,
    MatchResult,
    MatchTraceStep,
    SelectedCandidate,
)
from media_importer.features.scraping.match_enums import TierShortReason, WhySelected


def _sort_candidates_by_trust(candidates: list) -> list:
    """按可信度排序：popularity DESC → vote_average DESC → vote_count DESC"""
    return sorted(candidates, key=lambda c: (
        c.get("popularity", 0) or 0,
        c.get("vote_average", 0) or 0,
        c.get("vote_count", 0) or 0,
    ), reverse=True)


def _infer_media_type_from_path(path_context: dict | None) -> str:
    """从路径上下文推断 media_type。"""
    if not path_context:
        return ""

    tv_keywords = ("电视剧", "TV", "Series", "剧集", "国产剧", "日剧", "韩剧", "美剧", "动漫")
    movie_keywords = ("电影", "Movie", "Film", "Movies", "Films")

    parent = (path_context.get("parent_folder") or "").lower()
    grandparent = (path_context.get("grandparent_folder") or "").lower()
    combined = f"{parent} {grandparent}"

    for kw in tv_keywords:
        if kw.lower() in combined:
            return "tv"

    for kw in movie_keywords:
        if kw.lower() in combined:
            return "movie"

    return ""


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
    path_context=None,
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
            search_result = None
            search_years: list[Union[int, None]] = [year] if year is not None else [None]
            if year is not None:
                search_years.append(None)
            for try_year in search_years:
                try:
                    search_result = provider.search(search_title, year=try_year)
                except Exception as e:
                    logger.warning(f"Provider {provider.__class__.__name__} 搜索失败: {e}")
                    continue
                if search_result and search_result.items:
                    break

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
                    candidates=[{
                        "id": item.item_id,
                        "title": item.title,
                        "original_title": getattr(item, 'original_title', '') or '',
                        "year": item.year,
                        "media_type": item.media_type,
                        "overview": getattr(item, 'overview', '')[:100] if hasattr(item, 'overview') and getattr(item, 'overview', None) else '',
                        "provider_type": item.provider_type,
                        "poster_url": getattr(item, 'poster_url', '') or '',
                        "vote_average": item.vote_average or 0,
                        "vote_count": item.raw_data.get("vote_count", 0) if item.raw_data else 0,
                        "popularity": item.raw_data.get("popularity", 0) if item.raw_data else 0,
                    }],
                    tier_short_reason=TierShortReason.TIER1_UNIQUE,
                    selected_candidate=SelectedCandidate(
                        provider_type=item.provider_type,
                        provider_id=str(item.item_id),
                        title=item.title,
                        year=item.year,
                        media_type=item.media_type,
                        why_selected=WhySelected.UNIQUE_MATCH,
                        score=item.vote_average,
                    ),
                )
                # == end of single-match ==

            elif len(exact_matches) > 1:
                self._pending_candidates = [
                    {
                        "id": item.item_id,
                        "title": item.title,
                        "original_title": getattr(item, 'original_title', '') or '',
                        "year": item.year,
                        "media_type": item.media_type,
                        "provider_type": item.provider_type,
                        "vote_average": item.vote_average,
                        "popularity": item.raw_data.get("popularity", 0) if item.raw_data else 0,
                        "vote_count": item.raw_data.get("vote_count", 0) if item.raw_data else 0,
                        "poster_url": getattr(item, 'poster_url', '') or '',
                    }
                    for item, _ in exact_matches
                ]

                if year is None:
                    preferred_type = _infer_media_type_from_path(path_context)
                    if preferred_type:
                        filtered = [c for c in self._pending_candidates if c.get("media_type") == preferred_type]
                        if filtered:
                            self._pending_candidates = filtered

                self._pending_candidates = _sort_candidates_by_trust(self._pending_candidates)
                self._pending_candidates = self._pending_candidates[:10]
                self._pending_candidate_type = "exact"
                top = self._pending_candidates[0]

                self._pending_concerns.append(MatchConcern(
                    code="NO_YEAR_MULTI_MATCH",
                    message=f"找到 {len(exact_matches)} 部同名作品",
                    detail=f"已按热度预选: {top['title']} ({top.get('year', '')})",
                ))
                trace_steps.append(MatchTraceStep(
                    tier=1,
                    name="Provider精确匹配",
                    matched=False,
                    search_query=f"{search_title} (year={year})",
                    reason=f"多个精确匹配({len(exact_matches)}条)，已预选: {top['title']} ({top.get('year', '')})",
                ))

                return MatchResult(
                    match_level="NEEDS_CONFIRM",
                    provider_id=top["id"],
                    provider_title=top["title"],
                    match_tier=1,
                    concerns=self._pending_concerns,
                    trace_steps=trace_steps,
                    candidates=self._pending_candidates[:5],
                    tier_short_reason=TierShortReason.TIER1_MULTI.format(count=len(exact_matches)),
                    selected_candidate=SelectedCandidate(
                        provider_type=top["provider_type"],
                        provider_id=str(top["id"]),
                        title=top["title"],
                        year=top.get("year"),
                        media_type=top.get("media_type", ""),
                        why_selected=WhySelected.TOP_RATED,
                        score=top.get("vote_average"),
                    ),
                )

            else:
                # 有 Provider 结果但无精确匹配：保留模糊候选传给 Tier 2 AI
                fuzzy_candidates = [
                    {
                        "id": item.item_id,
                        "title": item.title,
                        "original_title": getattr(item, 'original_title', '') or '',
                        "year": item.year,
                        "media_type": item.media_type,
                        "provider_type": item.provider_type,
                        "vote_average": item.vote_average or 0,
                        "popularity": item.raw_data.get("popularity", 0) if item.raw_data else 0,
                        "vote_count": item.raw_data.get("vote_count", 0) if item.raw_data else 0,
                        "poster_url": getattr(item, 'poster_url', '') or '',
                    }
                    for item in items[:10]
                ]
                fuzzy_candidates = _sort_candidates_by_trust(fuzzy_candidates)
                self._pending_candidates = fuzzy_candidates
                self._pending_candidate_type = "fuzzy"
                if year and search_result and search_result.items:
                    self._pending_concerns.append(MatchConcern(
                        code="FUZZY_TITLE",
                        message="标题不完全匹配，最高相似度不足",
                        detail=f"搜索 '{search_title}' 无精确匹配，保留 {len(fuzzy_candidates)} 条模糊候选供 AI 参考",
                    ))
                trace_steps.append(MatchTraceStep(
                    tier=1,
                    name="Provider精确匹配",
                    matched=False,
                    search_query=f"{search_title} (year={year})",
                    reason=f"无精确匹配，Provider 返回 {len(items)} 条结果，保留 {len(fuzzy_candidates)} 条模糊候选",
                ))

    if not trace_steps:
        self._pending_concerns.append(MatchConcern(
            code="NO_PROVIDER_RESULT",
            message="Provider 未找到精准匹配作品",
            detail="",
        ))
        self._pending_candidate_type = "none"
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
    ai_short_reason: str,
    concerns: list,
    trace_steps: list,
    tier1_candidates=None,
    selected_candidate_id=None,
) -> Optional[MatchResult]:
    """AI 高确定性：用纠正后的标题搜 Provider → CONTEXT_PASS。"""
    candidates = []
    # 优先用 AI 指定的候选
    if selected_candidate_id and tier1_candidates:
        candidates = [c for c in tier1_candidates if str(c.get("id")) == str(selected_candidate_id)]
    if not candidates and tier1_candidates:
        candidates = [
            c for c in tier1_candidates
            if (not corrected_year or c.get("year") == corrected_year)
        ]
    if not candidates:
        candidates = _search_providers_impl(self.title_matcher, corrected_title, corrected_year, providers)
    if candidates:
        selected = candidates[0]
        trace_steps.append(MatchTraceStep(
            tier=2,
            name="上下文辅助匹配(高确定性)",
            matched=True,
            search_query=f"AI 纠正后搜索词: {corrected_title}" + (f" ({corrected_year}年)" if corrected_year else ""),
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
            tier_short_reason=ai_short_reason or TierShortReason.TIER2_HIGH_PASS,
            ai_reason=ai_reason,
            selected_candidate=SelectedCandidate(
                provider_type=selected.get("provider_type", ""),
                provider_id=str(selected.get("id", "")),
                title=selected.get("title", ""),
                year=selected.get("year"),
                media_type=selected.get("media_type", ""),
                why_selected=WhySelected.AI_SUGGESTION,
                score=selected.get("vote_average"),
            ),
        )
    logger.warning(f"AI high certainty 但搜索结果为空，降级为 medium: {corrected_title}")
    return _tier2_medium_certainty_impl(
        self, corrected_title, corrected_year, media_type_hint,
        providers, f"高确定性但未搜到结果: {ai_reason}", ai_short_reason, concerns, trace_steps,
        tier1_candidates=tier1_candidates,
    )


def _tier2_medium_certainty_impl(
    self,
    corrected_title: str,
    corrected_year: Optional[int],
    media_type_hint: Optional[str],
    providers: list,
    ai_reason: str,
    ai_short_reason: str,
    concerns: list,
    trace_steps: list,
    tier1_candidates=None,
) -> Optional[MatchResult]:
    """AI 中确定性：搜 Provider → NEEDS_CONFIRM（带候选列表）。"""
    candidates = []
    if tier1_candidates:
        candidates = [
            c for c in tier1_candidates
            if (not corrected_year or c.get("year") == corrected_year)
        ]
    if not candidates:
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
        search_query=f"AI 建议搜索词: {corrected_title}" + (f" ({corrected_year}年)" if corrected_year else ""),
        reason=f"AI中确定性，提供候选列表供确认: {ai_reason}",
        ai_reason=ai_reason,
    ))
    return MatchResult(
        match_level="NEEDS_CONFIRM",
        match_tier=2,
        concerns=concerns,
        trace_steps=trace_steps,
        candidates=candidates[:5],
        tier_short_reason=ai_short_reason or TierShortReason.TIER2_MEDIUM,
        ai_reason=ai_reason,
        selected_candidate=SelectedCandidate(
            provider_type=candidates[0].get("provider_type", ""),
            provider_id=str(candidates[0].get("id", "")),
            title=candidates[0].get("title", ""),
            year=candidates[0].get("year"),
            media_type=candidates[0].get("media_type", ""),
            why_selected=WhySelected.AI_SUGGESTION,
            score=candidates[0].get("vote_average"),
        ) if candidates else None,
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
        search_query=f"AI 建议搜索词: {corrected_title}" if corrected_title else "AI 未给出有效搜索词",
        reason=f"AI低确定性，需要人工确认: {ai_reason}",
        ai_reason=ai_reason,
    ))
    return MatchResult(
        match_level="NEEDS_CONFIRM",
        match_tier=2,
        concerns=concerns,
        trace_steps=trace_steps,
        candidates=[],
        tier_short_reason=TierShortReason.TIER2_LOW,
        ai_reason=ai_reason,
        selected_candidate=None,
    )


def _extract_year_from_raw(raw_data: dict):
    """从 TMDB 原始数据兜底提取年份"""
    if not raw_data:
        return None
    for key in ("release_date", "first_air_date"):
        val = raw_data.get(key, "")
        if val and len(val) >= 4:
            try:
                return int(val[:4])
            except ValueError:
                pass
    return None


def _search_providers_impl(title_matcher, title: str, year: Optional[int], providers: list) -> list:
    """统一搜索 Provider 返回候选列表。"""
    candidates = []
    for provider in providers:
        search_years: list[Union[int, None]] = [year] if year is not None else [None]
        if year is not None:
            search_years.append(None)
        for try_year in search_years:
            try:
                search_result = provider.search(title, year=try_year)
                if search_result and search_result.items:
                    for item in search_result.items[:5]:
                        candidates.append({
                            "id": item.item_id,
                            "title": item.title,
                            "original_title": getattr(item, 'original_title', '') or item.title,
                            "year": item.year or _extract_year_from_raw(item.raw_data),
                            "media_type": item.media_type,
                            "overview": getattr(item, 'overview', '')[:100] if hasattr(item, 'overview') and getattr(item, 'overview', None) else '',
                            "provider_type": item.provider_type,
                            "poster_url": getattr(item, 'poster_url', '') or '',
                            "vote_average": item.vote_average or 0,
                            "vote_count": item.raw_data.get("vote_count", 0) if item.raw_data else 0,
                            "popularity": item.raw_data.get("popularity", 0) if item.raw_data else 0,
                        })
            except Exception as e:
                logger.warning(f"Provider {provider.__class__.__name__} 搜索失败: {e}")
                continue
            if candidates:
                break
        if candidates:
            break
    candidates = _sort_candidates_by_trust(candidates)
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
    # 把 Tier 1 候选塞入 AI 上下文
    context["provider_candidates"] = getattr(self, '_pending_candidates', None) or []
    # 把 Tier 1 搜索结果传给 AI：让它知道这个名字已经搜过了，要换名字
    candidate_type = getattr(self, '_pending_candidate_type', 'none')
    candidate_count = len(context.get("provider_candidates", []))
    context["tier1_search_info"] = {
        "searched_title": clean_title,
        "searched_year": year,
        "candidate_type": candidate_type,  # "exact" / "fuzzy" / "none"
        "candidate_count": candidate_count,
        "provider_results": (
            "0 条结果" if candidate_type == "none"
            else f"{candidate_count} 条精确匹配" if candidate_type == "exact"
            else f"{candidate_count} 条模糊匹配（标题不完全一致）"
        ),
    }
    original_filename = video_path or clean_title

    try:
        from media_importer.features.scraping.llm_scraper import LLMScraper
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
    ai_short_reason = ai_result.get("short_reason", "")
    ai_is_valid = ai_result.get("is_valid", True)
    ai_selected_id = ai_result.get("selected_candidate_id")
    suggestion = ai_result.get("suggestion", corrected_title)
    media_type_hint = ai_result.get("media_type_hint")

    # 优先使用 AI 纠正后的标题，suggestion 只作辅助日志
    search_title = corrected_title

    tier1_candidates = getattr(self, '_pending_candidates', None) or []

    # is_valid=false → 立即 FAILED
    if not ai_is_valid:
        concerns.append(MatchConcern(
            code="INVALID_FILENAME",
            message="AI 判定文件名无可识别影视信息",
            detail=ai_reason,
        ))
        trace_steps.append(MatchTraceStep(
            tier=2,
            name="AI 辅助匹配",
            matched=False,
            reason=f"AI 判定为非影视文件: {ai_short_reason or ''}",
            ai_reason=ai_reason,
        ))
        self._pending_concerns = concerns
        self._pending_trace = trace_steps
        return MatchResult(
            match_level="FAILED",
            match_tier=2,
            concerns=concerns,
            trace_steps=trace_steps,
            tier_short_reason=ai_short_reason or "文件名无可识别影视信息",
            ai_reason=ai_reason,
            selected_candidate=None,
        )

    if certainty == "high":
        return _tier2_high_certainty_impl(
            self, search_title, corrected_year, media_type_hint,
            providers, ai_reason, ai_short_reason, concerns, trace_steps,
            tier1_candidates=tier1_candidates,
            selected_candidate_id=ai_selected_id,
        )
    elif certainty == "medium":
        return _tier2_medium_certainty_impl(
            self, search_title, corrected_year, media_type_hint,
            providers, ai_reason, ai_short_reason, concerns, trace_steps,
            tier1_candidates=tier1_candidates,
        )
    else:
        return _tier2_medium_certainty_impl(
            self, search_title, corrected_year, media_type_hint,
            providers, ai_reason, ai_short_reason, concerns, trace_steps,
            tier1_candidates=tier1_candidates,
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
        tier_short_reason=TierShortReason.TIER3_FALLBACK,
        ai_reason="",
        selected_candidate=SelectedCandidate(
            provider_type=candidates[0].get("provider_type", ""),
            provider_id=str(candidates[0].get("id", "")),
            title=candidates[0].get("title", ""),
            year=candidates[0].get("year"),
            media_type=candidates[0].get("media_type", ""),
            why_selected=WhySelected.FIRST_CANDIDATE,
            score=candidates[0].get("vote_average"),
        ) if candidates else None,
    )
