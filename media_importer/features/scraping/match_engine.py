"""两级匹配引擎：Provider 证据匹配 → 用户确认。"""
import logging
from typing import Optional

from media_importer.features.scraping._match_tiers_impl import (
    _tier1_exact_match_impl,
    _tier2_user_confirm_impl,
)
from media_importer.features.scraping.match_models import (
    MatchConcern,
    MatchResult,
    MatchTraceStep,
)
from media_importer.features.source_files.media_candidates import MediaCandidatePolicy

from .filename_cleaner import FilenameCleaner
from .identity_evidence import build_identity_evidence, evidence_to_dict
from .title_matcher import TitleMatcher

logger = logging.getLogger(__name__)


class MatchEngine:
    """文件名为主、可信目录为辅的两级匹配引擎。

    第一级：Provider 证据匹配；第二级：展示候选和疑虑供用户确认。
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.title_matcher = TitleMatcher()
        self.filename_cleaner = FilenameCleaner()
        self.candidate_policy = MediaCandidatePolicy(self.config)
        self._pending_candidates = []  # Tier 1 找到但未自动通过的候选
        self._pending_concerns = []
        self._pending_trace = []
        self.source_dir = (self.config.get("source_dir") or "").strip()

    def match(self, filename: str, providers: list, conn=None, video_path: str = "") -> MatchResult:
        """执行两级匹配。"""
        video_path = video_path or filename
        context = self._collect_context(video_path) if video_path else {}
        identity_evidence = build_identity_evidence(
            filename,
            video_path=video_path,
            source_dir=self.source_dir,
            cleaner=self.filename_cleaner,
            path_context=context,
        )
        clean_result = identity_evidence["file_clean_result"]
        self._current_clean_result = clean_result
        self._identity_evidence = identity_evidence
        clean_title = clean_result.clean_title or ""
        cjk_title = clean_result.cjk_title or ""
        year = clean_result.year
        season = clean_result.season
        episode = clean_result.episode

        self._pending_concerns = []
        self._pending_trace = []

        has_any_title = any(
            signal.get("titles") for signal in identity_evidence.get("signals", [])
        )
        if not has_any_title:
            return MatchResult(
                match_level="NEEDS_CONFIRM",
                match_tier=0,
                concerns=[MatchConcern(
                    code="NO_TITLE",
                    message="无法从文件名提取有效标题",
                    detail=f"文件名: {filename}",
                )],
                trace_steps=[MatchTraceStep(
                    tier=0, name="文件名清洗", matched=False,
                    reason="清洗后标题为空",
                )],
                identity_evidence=evidence_to_dict(identity_evidence),
            )

        # 通过 wrapper 方法调用（测试 patch 生效）
        result = self._tier1_exact_match(
            clean_title, cjk_title, year, season, episode, providers, path_context=context
        )
        if result:
            result.identity_evidence = evidence_to_dict(identity_evidence)
            if result.match_level == "AUTO_PASS" and clean_result.year_suspect:
                result.match_level = "NEEDS_CONFIRM"
                result.concerns.append(MatchConcern(
                    code="AMBIGUOUS_YEAR",
                    message="文件名中有多个可能的年份",
                    detail="系统已找到候选，但需要确认哪一个年份属于作品",
                ))
            return result
        # ADR-0010：原 Tier2 AI 上下文匹配已移除；不确定直接进人工确认
        result = self._tier2_user_confirm(
            clean_title, cjk_title, year, season, episode, providers
        )
        result.identity_evidence = evidence_to_dict(identity_evidence)
        return result

    def _tier1_exact_match(
        self,
        clean_title: str,
        cjk_title: str,
        year: Optional[int],
        season: Optional[int],
        episode: Optional[int],
        providers: list,
        path_context=None,
    ) -> Optional[MatchResult]:
        """第一级：Provider 精确匹配（thin wrapper，测试可 patch）。"""
        return _tier1_exact_match_impl(
            self, clean_title, cjk_title, year, season, episode, providers, path_context=path_context
        )

    def _tier2_user_confirm(
        self,
        clean_title: str,
        cjk_title: str,
        year: Optional[int],
        season: Optional[int],
        episode: Optional[int],
        providers: list,
    ) -> MatchResult:
        """第二级：用户确认（原 Tier3，thin wrapper，测试可 patch）。"""
        return _tier2_user_confirm_impl(
            self, clean_title, cjk_title, year, season, episode, providers
        )

    def _collect_context(self, video_path: str) -> dict:
        """收集视频文件所在目录的上下文信息（wrapper，测试可 patch）。"""
        from media_importer.features.scraping._match_tiers_impl import _collect_context_impl
        return _collect_context_impl(
            self.source_dir,
            video_path,
            candidate_policy=self.candidate_policy,
        )
