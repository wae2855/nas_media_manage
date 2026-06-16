"""三级匹配引擎：Provider精确匹配 → 上下文辅助匹配 → 用户确认。"""
import logging
from typing import List, Optional

from media_importer.features.scraping.match_models import (
    MatchConcern,
    MatchResult,
    MatchTraceStep,
)
from media_importer.features.scraping.confidence_models import CleanResult
from media_importer.scraper.title_matcher import TitleMatcher
from media_importer.scraper.filename_cleaner import FilenameCleaner

from media_importer.features.scraping._match_tiers_impl import (
    _tier1_exact_match_impl,
    _tier2_context_match_impl,
    _tier3_user_confirm_impl,
)

logger = logging.getLogger(__name__)


class MatchEngine:
    """三级匹配引擎。

    第一级：Provider 精确匹配（标题+年份 → TMDB 精确结果）
    第二级：上下文辅助匹配（目录信息 + AI 从候选列表中选出）
    第三级：用户确认（展示候选列表 + 疑虑原因）
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.title_matcher = TitleMatcher()
        self.filename_cleaner = FilenameCleaner()
        self._pending_candidates = []  # Tier 1 找到但未自动通过的候选
        self._pending_concerns = []
        self._pending_trace = []
        self.source_dir = (self.config.get("source_dir") or "").strip()

    def match(self, filename: str, providers: list, conn=None, video_path: str = "") -> MatchResult:
        """执行三级匹配。"""
        clean_result = self.filename_cleaner.clean(filename)
        clean_title = clean_result.clean_title or ""
        cjk_title = clean_result.cjk_title or ""
        year = clean_result.year
        season = clean_result.season
        episode = clean_result.episode

        self._pending_concerns = []
        self._pending_trace = []

        if not clean_title and not cjk_title:
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
            )

        # 通过 wrapper 方法调用（测试 patch 生效）
        result = self._tier1_exact_match(
            clean_title, cjk_title, year, season, episode, providers
        )
        if result:
            return result

        video_path = video_path or filename
        result = self._tier2_context_match(
            clean_title, cjk_title, year, season, episode, providers, video_path
        )
        if result:
            return result

        return self._tier3_user_confirm(
            clean_title, cjk_title, year, season, episode, providers
        )

    def _tier1_exact_match(
        self,
        clean_title: str,
        cjk_title: str,
        year: Optional[int],
        season: Optional[int],
        episode: Optional[int],
        providers: list,
    ) -> Optional[MatchResult]:
        """第一级：Provider 精确匹配（thin wrapper，测试可 patch）。"""
        return _tier1_exact_match_impl(
            self, clean_title, cjk_title, year, season, episode, providers
        )

    def _tier2_context_match(
        self,
        clean_title: str,
        cjk_title: str,
        year: Optional[int],
        season: Optional[int],
        episode: Optional[int],
        providers: list,
        video_path: str = "",
    ) -> Optional[MatchResult]:
        """第二级：上下文辅助匹配（thin wrapper，测试可 patch）。"""
        return _tier2_context_match_impl(
            self, clean_title, cjk_title, year, season, episode, providers, video_path
        )

    def _tier3_user_confirm(
        self,
        clean_title: str,
        cjk_title: str,
        year: Optional[int],
        season: Optional[int],
        episode: Optional[int],
        providers: list,
    ) -> MatchResult:
        """第三级：用户确认（thin wrapper，测试可 patch）。"""
        return _tier3_user_confirm_impl(
            self, clean_title, cjk_title, year, season, episode, providers
        )

    def _collect_context(self, video_path: str) -> dict:
        """收集视频文件所在目录的上下文信息（wrapper，测试可 patch）。"""
        from media_importer.features.scraping._match_tiers_impl import _collect_context_impl
        return _collect_context_impl(self.source_dir, video_path)
