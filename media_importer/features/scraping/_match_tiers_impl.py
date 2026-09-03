"""Match engine tier implementations — extracted from MatchEngine."""
import logging
import os as _os
from typing import Optional, Union

from media_importer.features.scraping.match_enums import TierShortReason, WhySelected
from media_importer.features.scraping.match_models import (
    MatchConcern,
    MatchResult,
    MatchTraceStep,
    SelectedCandidate,
)
from media_importer.features.scraping.title_normalizer import TitleNormalizer


def _sort_candidates_by_trust(candidates: list) -> list:
    """按可信度排序：popularity DESC → vote_average DESC → vote_count DESC"""
    return sorted(candidates, key=lambda c: (
        c.get("popularity", 0) or 0,
        c.get("vote_average", 0) or 0,
        c.get("vote_count", 0) or 0,
    ), reverse=True)


def _entry_evidence_score(entry: dict, media_type_hint: str, season, episode) -> tuple[float, list[str]]:
    """Rank candidates by explainable identity evidence; popularity is not identity evidence."""
    reasons: list[str] = []
    best_match = max(
        (match for _, _, match in entry.get("matches", [])),
        key=lambda match: (getattr(match, "T", 0.0), getattr(match, "similarity", 0.0)),
        default=None,
    )
    level = getattr(best_match, "level", "")
    similarity = float(getattr(best_match, "similarity", 0.0) or 0.0)
    if level in {"L1", "L2", "L3"}:
        score = 60.0
        reasons.append("标题严格一致")
    elif similarity >= 0.999:
        score = 50.0
        reasons.append("标题宽松一致")
    else:
        score = similarity * 40.0
        if similarity:
            reasons.append(f"标题相似度 {similarity:.2f}")

    years = entry.get("signal_years") or set()
    item = entry["item"]
    if years and item.year is not None:
        if years == {item.year}:
            score += 25.0
            reasons.append("年份一致")
        elif item.year not in years:
            score -= 40.0
            reasons.append("年份冲突")
    if media_type_hint:
        if item.media_type == media_type_hint:
            score += 15.0
            reasons.append("媒体类型一致")
        else:
            score -= 50.0
            reasons.append("媒体类型冲突")
    if season is not None or episode is not None:
        if item.media_type == "tv":
            score += 10.0
            reasons.append("季集结构支持剧集")
    sources = entry.get("sources") or set()
    if "file" in sources:
        score += 8.0
        reasons.append("文件名证据")
    if "folder" in sources:
        score += 4.0
        reasons.append("目录证据")
    if {"file", "folder"}.issubset(sources):
        score += 12.0
        reasons.append("文件与目录收敛")
    if entry.get("alias_matches"):
        score += 30.0
        reasons.append("Provider 官方别名")
    return round(score, 3), reasons


def _candidate_ambiguity(entry: dict, runner_up: dict, config: dict) -> tuple[bool, str]:
    """Judge candidate proximity from evidence shape, not one global score gap."""
    best_score = float(entry["evidence_score"])
    second_score = float(runner_up["evidence_score"])
    margin = round(best_score - second_score, 3)
    best_reasons = set(entry.get("evidence_reasons") or [])
    second_reasons = set(runner_up.get("evidence_reasons") or [])
    strong_markers = {"Provider 官方别名", "文件与目录收敛"}

    if best_reasons & strong_markers and not second_reasons & strong_markers:
        return False, f"第一候选有独立强证据，差距 {margin:.1f} 分"

    # Reuse TitleMatcher's configured fuzzy boundary: when two candidates have
    # the same evidence shape, the untrusted part of the title-similarity range
    # defines how much separation is required. This avoids a detached magic
    # number and becomes stricter when the configured fuzzy boundary is stricter.
    similarity_uncertainty = 1.0 - float(config.get("title_min_similarity", 0.3))
    required_margin = round(max(0.05, similarity_uncertainty * 0.2) * 100, 1)
    comparable_evidence = (
        best_reasons == second_reasons
        or bool(best_reasons & second_reasons & {"年份一致", "标题严格一致", "标题宽松一致"})
    )
    is_close = comparable_evidence and margin < required_margin
    detail = (
        f"第一候选 {best_score:.1f} 分，第二候选 {second_score:.1f} 分，"
        f"差距 {margin:.1f} 分；同类证据要求至少拉开 {required_margin:.1f} 分"
    )
    return is_close, detail


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
    """Provider matching over independent file/folder title signals."""
    trace_steps: list[MatchTraceStep] = list(getattr(self, "_pending_trace", []) or [])
    evidence = getattr(self, "_identity_evidence", {}) or {}
    signals = evidence.get("signals") or [{
        "source": "file",
        "titles": [title for title in (cjk_title, clean_title) if title],
        "year": year,
        "season": season,
        "episode": episode,
        "weak": False,
    }]
    # Only season/episode in the file is strong enough to constrain Provider type.
    # A user-created folder called "TV" or "电影" must not veto an otherwise
    # exact filename match.
    media_type_hint = "tv" if season is not None or episode is not None else ""
    search_cache = {}
    alias_cache = {}
    candidate_hits = {}

    def normalized_title(value: str) -> str:
        return TitleNormalizer.strict(str(value or ""))

    titles_by_source = {
        source: {
            normalized_title(title)
            for signal in signals
            if signal.get("source") == source
            for title in signal.get("titles", [])
            if normalized_title(title)
        }
        for source in ("file", "folder")
    }
    file_folder_title_overlap = bool(
        titles_by_source["file"] & titles_by_source["folder"]
    )

    def candidate_payload(item) -> dict:
        raw_data = item.raw_data or {}
        return {
            "id": item.item_id,
            "title": item.title,
            "original_title": getattr(item, "original_title", "") or "",
            "year": item.year,
            "media_type": item.media_type,
            "provider_type": item.provider_type,
            "poster_url": getattr(item, "poster_url", "") or "",
            "vote_average": item.vote_average or 0,
            "vote_count": raw_data.get("vote_count", 0) or 0,
            "popularity": raw_data.get("popularity", 0) or 0,
        }

    def make_result(entry, short_reason: str, why_selected: str) -> MatchResult:
        item = entry["item"]
        evidence_score, evidence_reasons = _entry_evidence_score(
            entry, media_type_hint, season, episode
        )
        payload = candidate_payload(item)
        payload["identity_sources"] = sorted(entry["sources"])
        payload["evidence_score"] = evidence_score
        payload["evidence_reasons"] = evidence_reasons
        return MatchResult(
            match_level="AUTO_PASS",
            provider_id=item.item_id,
            provider_title=item.title,
            match_tier=1,
            trace_steps=trace_steps,
            candidates=[payload],
            tier_short_reason=short_reason,
            selected_candidate=SelectedCandidate(
                provider_type=item.provider_type,
                provider_id=str(item.item_id),
                title=item.title,
                year=item.year,
                media_type=item.media_type,
                why_selected=why_selected,
                score=evidence_score,
            ),
        )

    # Query every independent file title across every Provider before any
    # directory evidence. A strong file identity remains authoritative, while
    # multiple strong file identities are evaluated together below.
    work_items = [
        (provider, signal)
        for signal in sorted(signals, key=lambda item: item.get("source") != "file")
        for provider in providers
    ]
    for provider, signal in work_items:
            source = signal.get("source", "file")
            if source == "folder" and any(
                "file" in entry["strong_exact_sources"]
                for entry in candidate_hits.values()
            ):
                continue
            signal_year = signal.get("year")
            signal_season = signal.get("season")
            seen_titles = set()
            for search_title in signal.get("titles", []):
                title_key = str(search_title).strip().casefold()
                if not title_key or title_key in seen_titles:
                    continue
                seen_titles.add(title_key)
                cache_key = (id(provider), title_key, signal_year, media_type_hint)
                search_result = search_cache.get(cache_key)
                if cache_key not in search_cache:
                    search_result = None
                    search_years: list[Union[int, None]] = (
                        [signal_year, None] if signal_year is not None else [None]
                    )
                    for try_year in search_years:
                        try:
                            search_result = provider.search(
                                search_title,
                                year=try_year,
                                media_type=media_type_hint or None,
                            )
                        except Exception as exc:
                            logger.warning(
                                "Provider %s 搜索失败: %s",
                                provider.__class__.__name__, exc,
                            )
                            continue
                        if search_result and search_result.items:
                            break
                    search_cache[cache_key] = search_result

                items = list(getattr(search_result, "items", []) or [])
                eligible_items = [
                    item for item in items
                    if not media_type_hint or item.media_type == media_type_hint
                ]
                matches = []
                for item in eligible_items:
                    title_match = self.title_matcher.match_standard(
                        search_title, item, signal_year, signal_season
                    )
                    alias_matched = ""
                    if (
                        source == "file"
                        and len(eligible_items) == 1
                        and signal_year is not None
                        and item.year == signal_year
                        and title_match.level not in ("L1", "L2", "L3")
                    ):
                        alias_key = (id(provider), item.media_type, str(item.item_id))
                        if alias_key not in alias_cache:
                            try:
                                alias_cache[alias_key] = list(
                                    provider.get_alternative_titles(item.item_id, item.media_type)
                                )
                            except Exception as exc:
                                logger.warning(
                                    "Provider %s 官方别名读取失败: %s",
                                    provider.__class__.__name__, exc,
                                )
                                alias_cache[alias_key] = []
                        alias_matched = next((
                            alias for alias in alias_cache[alias_key]
                            if normalized_title(alias) == normalized_title(search_title)
                        ), "")
                        if alias_matched:
                            title_match.level = "L1"
                            title_match.T = 1.0
                            title_match.similarity = 1.0
                            title_match.year_match = True
                            title_match.reason = f"L1: 标题精确命中 Provider 官方别名 {alias_matched} + 年份一致"
                    key = (item.provider_type, item.media_type, str(item.item_id))
                    entry = candidate_hits.setdefault(key, {
                        "item": item,
                        "sources": set(),
                        "exact_sources": set(),
                        "strong_exact_sources": set(),
                        "strong_file_titles": set(),
                        "support_sources": set(),
                        "matches": [],
                        "signal_years": set(),
                    })
                    entry["sources"].add(source)
                    entry["matches"].append((source, search_title, title_match))
                    if signal_year is not None:
                        entry["signal_years"].add(signal_year)
                    if title_match.level in ("L1", "L2", "L3"):
                        entry["exact_sources"].add(source)
                    if title_match.level in ("L1", "L2"):
                        entry["strong_exact_sources"].add(source)
                        if source == "file":
                            entry["strong_file_titles"].add(normalized_title(search_title))
                    if alias_matched:
                        entry.setdefault("alias_matches", set()).add(alias_matched)
                    if (
                        source == "file"
                        and len(eligible_items) == 1
                        and signal_year is not None
                        and item.year == signal_year
                        and file_folder_title_overlap
                    ):
                        entry["support_sources"].add(source)
                    if title_match.level in ("L1", "L2"):
                        matches.append((item, title_match, entry))

                label = "文件名检索" if source == "file" else "文件夹辅助检索"
                if len(matches) == 1:
                    item, title_match, entry = matches[0]
                    trace_steps.append(MatchTraceStep(
                        tier=1,
                        name=label,
                        matched=True,
                        search_query=f"{search_title} (year={signal_year})",
                        match_level=title_match.level,
                        reason=f"唯一精确匹配: {item.title}",
                    ))
                    if source == "file" and alias_matched:
                        trace_steps[-1].reason = f"官方别名精确匹配: {alias_matched} → {item.title}"
                else:
                    trace_steps.append(MatchTraceStep(
                        tier=1,
                        name=label,
                        matched=False,
                        search_query=f"{search_title} (year={signal_year})",
                        reason=(
                            f"找到 {len(matches)} 条精确候选，需要更多证据"
                            if matches else f"未精确匹配，Provider 返回 {len(items)} 条候选"
                        ),
                    ))

    def year_compatible(entry) -> bool:
        item_year = entry["item"].year
        years = entry["signal_years"]
        return not years or item_year is None or years == {item_year}

    strong_file_entries = [
        entry for entry in candidate_hits.values()
        if "file" in entry["strong_exact_sources"] and year_compatible(entry)
    ]
    file_identity_conflict = len(strong_file_entries) > 1
    if file_identity_conflict:
        self._pending_concerns.append(MatchConcern(
            code="CONFLICTING_INFO",
            message="文件名中的多个标题指向不同作品",
            detail="系统已完成全部文件名标题候选查询，没有采用第一个命中结果，请人工确认",
        ))
        trace_steps.append(MatchTraceStep(
            tier=1,
            name="文件名多标题一致性校验",
            matched=False,
            reason=f"{len(strong_file_entries)} 个强匹配指向不同作品，禁止自动入库",
        ))
    elif len(strong_file_entries) == 1:
        entry = strong_file_entries[0]
        alias_matched = bool(entry.get("alias_matches"))
        trace_steps.append(MatchTraceStep(
            tier=1,
            name="文件名完整证据校验",
            matched=True,
            reason=f"全部文件名标题候选查询完成，唯一强匹配为 {entry['item'].title}",
        ))
        return make_result(
            entry,
            (
                TierShortReason.TIER1_PROVIDER_ALIAS
                if alias_matched else TierShortReason.TIER1_UNIQUE
            ),
            WhySelected.PROVIDER_ALIAS if alias_matched else WhySelected.UNIQUE_MATCH,
        )

    converged = [
        entry for entry in candidate_hits.values()
        if {"file", "folder"}.issubset(entry["sources"])
        and "folder" in entry["exact_sources"]
        and (
            "file" in entry["exact_sources"]
            or "file" in entry["support_sources"]
        )
        and year_compatible(entry)
        and (entry["signal_years"] or season is not None or episode is not None)
    ]
    if not file_identity_conflict and len(converged) == 1:
        entry = converged[0]
        trace_steps.append(MatchTraceStep(
            tier=1,
            name="多语言证据收敛",
            matched=True,
            reason=f"文件名与目录名均指向 {entry['item'].title} ({entry['item'].year or '年份未知'})",
        ))
        return make_result(
            entry,
            TierShortReason.TIER1_EVIDENCE_CONVERGED,
            WhySelected.EVIDENCE_CONVERGED,
        )

    file_signal = next((item for item in signals if item.get("source") == "file"), {})
    if not file_identity_conflict and file_signal.get("weak"):
        folder_exact = [
            entry for entry in candidate_hits.values()
            if "folder" in entry["exact_sources"]
            and year_compatible(entry)
            and (entry["signal_years"] or entry["item"].year is not None)
        ]
        if len(folder_exact) == 1:
            entry = folder_exact[0]
            trace_steps.append(MatchTraceStep(
                tier=1,
                name="弱文件名目录补足",
                matched=True,
                reason=f"文件名信息不足，可信目录精确指向 {entry['item'].title}",
            ))
            return make_result(
                entry,
                TierShortReason.TIER1_FOLDER_RESCUE,
                WhySelected.FOLDER_RESCUE,
            )

    exact_by_source = {
        source: {
            key for key, entry in candidate_hits.items()
            if source in entry["exact_sources"]
        }
        for source in ("file", "folder")
    }
    if not file_identity_conflict and exact_by_source["file"] and exact_by_source["folder"] and not (
        exact_by_source["file"] & exact_by_source["folder"]
    ):
        self._pending_concerns.append(MatchConcern(
            code="CONFLICTING_INFO",
            message="文件名和文件夹名指向不同作品",
            detail="系统没有自动入库，请人工确认正确作品",
        ))

    for entry in candidate_hits.values():
        entry["evidence_score"], entry["evidence_reasons"] = _entry_evidence_score(
            entry, media_type_hint, season, episode
        )

    ranked_entries = sorted(
        candidate_hits.values(),
        key=lambda entry: (
            entry["evidence_score"],
            entry["item"].raw_data.get("popularity", 0) if entry["item"].raw_data else 0,
            entry["item"].vote_average or 0,
        ),
        reverse=True,
    )
    self._pending_candidates = []
    for entry in ranked_entries[:10]:
        payload = candidate_payload(entry["item"])
        payload["identity_sources"] = sorted(entry["sources"])
        payload["evidence_score"] = entry["evidence_score"]
        payload["evidence_reasons"] = entry["evidence_reasons"]
        self._pending_candidates.append(payload)

    if len(ranked_entries) >= 2:
        is_ambiguous, detail = _candidate_ambiguity(
            ranked_entries[0], ranked_entries[1], self.title_matcher._config
        )
        if is_ambiguous:
            self._pending_concerns.append(MatchConcern(
                code="CLOSE_CANDIDATES",
                message="前两名候选过于接近",
                detail=detail,
            ))
            trace_steps.append(MatchTraceStep(
                tier=1,
                name="候选差距保护",
                matched=False,
                reason=f"{detail}，没有强身份 ID，交由用户确认",
            ))

    if candidate_hits and trace_steps and not self._pending_concerns:
        self._pending_concerns.append(MatchConcern(
            code="FUZZY_TITLE",
            message="标题证据尚不足以自动确认",
            detail="已保留文件名和可信目录检索到的候选，请人工确认",
        ))
    if not candidate_hits:
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



def _collect_context_impl(source_dir: str, video_path: str, *, candidate_policy=None) -> dict:
    """收集视频文件所在目录的上下文信息。"""
    context = {}
    parent_dir = _os.path.basename(_os.path.dirname(video_path))
    if parent_dir and parent_dir not in (".", "..", "/"):
        context["parent_folder"] = parent_dir
    dir_path = _os.path.dirname(video_path)
    if dir_path:
        try:
            sibling_paths = [
                _os.path.join(dir_path, f) for f in _os.listdir(dir_path)
                if f != _os.path.basename(video_path)
                and any(f.lower().endswith(ext) for ext in (
                    ".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".wmv", ".flv"
                ))
            ][:20]
            if candidate_policy and sibling_paths:
                decisions = candidate_policy.classify_tree(
                    source_dir or dir_path,
                    [video_path, *sibling_paths],
                )
                sibling_paths = [
                    path for path in sibling_paths
                    if decisions.get(_os.path.realpath(path)) is None
                    or decisions[_os.path.realpath(path)].accepted
                ]
            siblings = [_os.path.basename(path) for path in sibling_paths]
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


def _tier2_user_confirm_impl(
    self,
    clean_title: str,
    cjk_title: str,
    year: Optional[int],
    season: Optional[int],
    episode: Optional[int],
    providers: list,
) -> MatchResult:
    """第二级：用户确认；match_tier 暂保留历史存储值 3。"""
    concerns = self._pending_concerns[:]
    trace_steps = self._pending_trace[:]
    candidates = list(getattr(self, "_pending_candidates", []) or [])

    for provider in providers if not candidates else []:
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
