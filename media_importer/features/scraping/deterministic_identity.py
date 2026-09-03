"""Resolve strong provider identifiers before any fuzzy title search."""

from __future__ import annotations

import logging

from .match_enums import WhySelected
from .match_models import MatchConcern, MatchResult, MatchTraceStep, SelectedCandidate
from .title_normalizer import TitleNormalizer

logger = logging.getLogger(__name__)


def _identity_source_label(source: str) -> str:
    return {
        "filename": "filename_provider_id",
        "nfo": "nfo_provider_id",
        "folder": "folder_provider_id",
        "history": "historical_provider_binding",
    }.get(source, source)


def _why_selected(source: str) -> str:
    return {
        "filename": WhySelected.EXPLICIT_ID,
        "nfo": WhySelected.NFO_ID,
        "folder": WhySelected.FOLDER_ID,
        "history": WhySelected.HISTORICAL_BINDING,
    }.get(source, WhySelected.FIRST_CANDIDATE)


def _candidate_payload(item, *, identity_source: str, id_type: str, id_value: str) -> dict:
    raw = item.raw_data or {}
    return {
        "id": str(item.item_id),
        "title": item.title,
        "original_title": item.original_title,
        "year": item.year,
        "media_type": item.media_type,
        "provider_type": item.provider_type,
        "poster_url": item.poster_url or "",
        "vote_average": item.vote_average or 0,
        "vote_count": raw.get("vote_count", 0) or 0,
        "popularity": raw.get("popularity", 0) or 0,
        "identity_sources": [_identity_source_label(identity_source)],
        "resolved_from": {"id_type": id_type, "value": id_value},
    }


def _conflict_reason(item, *, year: int | None, media_type_hint: str) -> list[str]:
    reasons = []
    if media_type_hint and item.media_type and item.media_type != media_type_hint:
        reasons.append(f"媒体类型冲突：文件为 {media_type_hint}，ID 指向 {item.media_type}")
    if year is not None and item.year is not None and item.year != year:
        reasons.append(f"年份冲突：文件为 {year}，ID 指向 {item.year}")
    return reasons


def resolve_deterministic_identity(
    evidence: dict,
    providers: list,
    *,
    year: int | None,
    media_type_hint: str,
) -> tuple[MatchResult | None, list[MatchTraceStep]]:
    """Resolve filename IDs first, then NFO IDs; never throw provider errors."""
    trace: list[MatchTraceStep] = []
    references = list(evidence.get("provider_ids") or [])
    episode_references = [
        ref for ref in references if ref.get("identity_scope") == "episode"
    ]
    if episode_references:
        trace.append(MatchTraceStep(
            tier=1,
            name="NFO 身份范围校验",
            matched=False,
            search_query=", ".join(
                f"{ref.get('id_type')}:{ref.get('value')}" for ref in episode_references
            ),
            reason="episode NFO ID 不是 series ID，跳过确定性剧集查询并回退标题识别",
        ))
        references = [
            ref for ref in references if ref.get("identity_scope") != "episode"
        ]
    for source in ("filename", "nfo", "folder", "history"):
        source_refs = [ref for ref in references if ref.get("source") == source]
        if not source_refs:
            continue
        resolved: dict[tuple[str, str, str], tuple[object, dict]] = {}
        had_lookup_error = False
        for ref in source_refs:
            id_type = str(ref.get("id_type") or "").casefold()
            id_value = str(ref.get("value") or "").strip()
            for provider in providers:
                try:
                    ref_hint = str(ref.get("media_type_hint") or media_type_hint or "")
                    if id_type == str(getattr(provider, "provider_type", "")).casefold():
                        search_result = provider.get_by_provider_id(id_value, ref_hint or None)
                    else:
                        search_result = provider.lookup_external_id(
                            id_value, id_type, ref_hint or None
                        )
                except Exception as exc:
                    had_lookup_error = True
                    logger.warning(
                        "Provider %s ID lookup failed for %s=%s: %s",
                        provider.__class__.__name__, id_type, id_value, exc,
                    )
                    trace.append(MatchTraceStep(
                        tier=1,
                        name="确定性身份查询",
                        matched=False,
                        search_query=f"{id_type}:{id_value}",
                        reason=f"{getattr(provider, 'display_name', provider.__class__.__name__)} 查询异常，已保守降级",
                    ))
                    continue
                for item in list(getattr(search_result, "items", []) or []):
                    key = (str(item.provider_type), str(item.item_id), str(item.media_type))
                    resolved[key] = (item, ref)

        if not resolved:
            reason = (
                "身份编号查询异常，不能安全回退到标题匹配"
                if had_lookup_error
                else "身份编号未解析到作品，不能安全回退到标题匹配"
            )
            trace.append(MatchTraceStep(
                tier=1,
                name="确定性身份查询",
                matched=False,
                search_query=", ".join(
                    f"{ref.get('id_type')}:{ref.get('value')}" for ref in source_refs
                ),
                reason=reason,
            ))
            evidence["identity_resolution"] = {
                "source": source,
                "identity_source": _identity_source_label(source),
                "status": "lookup_failed" if had_lookup_error else "not_found",
                "reason": reason,
            }
            return MatchResult(
                match_level="NEEDS_CONFIRM",
                match_tier=3,
                concerns=[MatchConcern(
                    code="IDENTITY_LOOKUP_FAILED",
                    message="身份编号无法验证",
                    detail=reason,
                )],
                trace_steps=trace,
                tier_short_reason="身份编号无法验证，需确认",
            ), trace

        candidates = [
            _candidate_payload(
                item,
                identity_source=source,
                id_type=str(ref.get("id_type") or ""),
                id_value=str(ref.get("value") or ""),
            )
            for item, ref in resolved.values()
        ]
        distinct_inputs = {
            (str(ref.get("id_type")), str(ref.get("value"))) for ref in source_refs
        }
        if len(resolved) > 1 and len(distinct_inputs) > 1:
            reason = "同一优先级的身份 ID 指向多个不同作品"
            trace.append(MatchTraceStep(
                tier=1, name="确定性身份查询", matched=False, reason=reason,
            ))
            evidence["identity_resolution"] = {
                "source": source,
                "identity_source": _identity_source_label(source),
                "status": "conflict",
                "reason": reason,
                "candidate_count": len(candidates),
            }
            return MatchResult(
                match_level="NEEDS_CONFIRM",
                match_tier=3,
                concerns=[MatchConcern(
                    code="IDENTITY_CONFLICT",
                    message="文件中的身份编号存在冲突",
                    detail=reason,
                )],
                trace_steps=trace,
                candidates=candidates[:10],
                tier_short_reason="身份编号冲突，需确认",
            ), trace

        resolved_values = list(resolved.values())
        if len(resolved_values) > 1:
            compatible = []
            for candidate_item, candidate_ref in resolved_values:
                candidate_year = year if year is not None else candidate_ref.get("year")
                candidate_type = media_type_hint or str(candidate_ref.get("media_type_hint") or "")
                if not _conflict_reason(
                    candidate_item,
                    year=candidate_year,
                    media_type_hint=candidate_type,
                ):
                    compatible.append((candidate_item, candidate_ref))
            titles = [
                title
                for signal in evidence.get("signals", [])
                for title in signal.get("titles", [])
            ]
            exact = [
                pair for pair in compatible
                if any(
                    TitleNormalizer.compare(title, candidate_title).strict_exact
                    for title in titles
                    for candidate_title in (pair[0].title, pair[0].original_title)
                    if candidate_title
                )
            ]
            if len(exact) == 1:
                resolved_values = exact
            elif len(compatible) == 1:
                resolved_values = compatible
            else:
                reason = "同一身份编号在多个媒体类型中均有合理结果"
                trace.append(MatchTraceStep(
                    tier=1, name="确定性身份消歧", matched=False, reason=reason,
                ))
                evidence["identity_resolution"] = {
                    "source": source,
                    "identity_source": _identity_source_label(source),
                    "status": "ambiguous",
                    "reason": reason,
                    "candidate_count": len(candidates),
                }
                return MatchResult(
                    match_level="NEEDS_CONFIRM",
                    match_tier=3,
                    concerns=[MatchConcern(
                        code="IDENTITY_CONFLICT",
                        message="身份编号对应多个可能作品",
                        detail=reason,
                    )],
                    trace_steps=trace,
                    candidates=candidates[:10],
                    tier_short_reason="身份编号结果不唯一，需确认",
                ), trace

        item, ref = resolved_values[0]
        selected_payload = _candidate_payload(
            item,
            identity_source=source,
            id_type=str(ref.get("id_type") or ""),
            id_value=str(ref.get("value") or ""),
        )
        effective_year = year
        effective_type = media_type_hint
        if source in {"nfo", "folder"}:
            effective_year = effective_year if effective_year is not None else ref.get("year")
            effective_type = effective_type or str(ref.get("media_type_hint") or "")
        if source == "nfo":
            nfo = next((entry for entry in evidence.get("nfo_identities", []) if entry.get("path") == ref.get("path")), {})
            effective_year = effective_year if effective_year is not None else nfo.get("year")
            effective_type = effective_type or str(nfo.get("media_type_hint") or "")
        conflicts = _conflict_reason(item, year=effective_year, media_type_hint=effective_type)
        if source == "nfo":
            nfo_titles = [str(nfo.get("title") or "").strip()]
            nfo_titles = [title for title in nfo_titles if title]
            if not nfo_titles:
                nfo_titles = [
                    title
                    for signal in evidence.get("signals", [])
                    if signal.get("source") == "folder"
                    for title in signal.get("titles", [])
                    if title
                ]
            provider_titles = [item.title, item.original_title]
            title_matches = any(
                TitleNormalizer.compare(nfo_title, provider_title).strict_exact
                for nfo_title in nfo_titles
                for provider_title in provider_titles
                if provider_title
            )
            if nfo_titles and not title_matches:
                conflicts.append("标题冲突：NFO 所在作品目录与身份编号指向的作品不一致")
        if source == "folder":
            file_signal = next(
                (
                    signal
                    for signal in evidence.get("signals", [])
                    if signal.get("source") == "file"
                ),
                {},
            )
            file_titles = list(file_signal.get("titles") or [])
            provider_titles = [item.title, item.original_title]
            title_matches = any(
                TitleNormalizer.compare(file_title, provider_title).strict_exact
                for file_title in file_titles
                for provider_title in provider_titles
                if file_title and provider_title
            )
            if file_titles and not file_signal.get("weak") and not title_matches:
                conflicts.append("标题冲突：文件名与目录身份编号指向的作品不一致")
        if conflicts:
            reason = "；".join(conflicts)
            trace.append(MatchTraceStep(
                tier=1,
                name="确定性身份校验",
                matched=False,
                search_query=f"{ref.get('id_type')}:{ref.get('value')}",
                reason=reason,
            ))
            evidence["identity_resolution"] = {
                "source": source,
                "identity_source": _identity_source_label(source),
                "provider": item.provider_type,
                "resolved_id": str(item.item_id),
                "status": "conflict",
                "reason": reason,
            }
            return MatchResult(
                match_level="NEEDS_CONFIRM",
                provider_id=str(item.item_id),
                provider_title=item.title,
                match_tier=3,
                concerns=[MatchConcern(
                    code="IDENTITY_CONFLICT",
                    message="身份编号与文件信息不一致",
                    detail=reason,
                )],
                trace_steps=trace,
                candidates=[selected_payload],
                tier_short_reason="身份信息冲突，需确认",
                selected_candidate=SelectedCandidate(
                    provider_type=item.provider_type,
                    provider_id=str(item.item_id),
                    title=item.title,
                    year=item.year,
                    media_type=item.media_type,
                    why_selected=_why_selected(source),
                    score=1.0,
                ),
            ), trace

        short_reason = {
            "filename": "文件名身份编号精确命中",
            "nfo": "NFO 身份编号精确命中",
            "folder": "作品目录身份编号精确命中",
            "history": "历史身份绑定精确命中",
        }.get(source, "身份编号精确命中")
        trace.append(MatchTraceStep(
            tier=1,
            name="确定性身份查询",
            matched=True,
            search_query=f"{ref.get('id_type')}:{ref.get('value')}",
            match_level="ID_EXACT",
            reason=f"{short_reason}：{item.title} ({item.year or '年份未知'})",
        ))
        evidence["identity_resolution"] = {
            "source": source,
            "identity_source": _identity_source_label(source),
            "id_type": ref.get("id_type"),
            "input_id": ref.get("value"),
            "provider": item.provider_type,
            "resolved_id": str(item.item_id),
            "status": "resolved",
        }
        return MatchResult(
            match_level="AUTO_PASS",
            provider_id=str(item.item_id),
            provider_title=item.title,
            match_tier=1,
            trace_steps=trace,
            candidates=[selected_payload],
            tier_short_reason=short_reason,
            selected_candidate=SelectedCandidate(
                provider_type=item.provider_type,
                provider_id=str(item.item_id),
                title=item.title,
                year=item.year,
                media_type=item.media_type,
                why_selected=_why_selected(source),
                score=1.0,
            ),
        ), trace
    return None, trace
