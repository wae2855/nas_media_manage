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
        self._pending_concerns = []
        self._pending_trace = []

    def match(self, filename: str, providers: list, conn=None, video_path: str = "") -> MatchResult:
        """执行三级匹配。

        Args:
            filename: 原始视频文件名
            providers: 已启用的 Provider 实例列表
            conn: 数据库连接（用于维度查询）

        Returns:
            MatchResult 包含匹配级别、疑虑原因和追踪信息
        """
        # 清洗文件名
        clean_result = self.filename_cleaner.clean(filename)
        clean_title = clean_result.clean_title or ""
        cjk_title = clean_result.cjk_title or ""
        year = clean_result.year
        season = clean_result.season
        episode = clean_result.episode

        # 重置暂存
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

        # 第一级：Provider 精确匹配
        result = self._tier1_exact_match(
            clean_title, cjk_title, year, season, episode, providers
        )
        if result:
            return result

        # 第二级：上下文辅助匹配
        video_path = video_path or filename  # 优先使用外部传入的完整路径
        result = self._tier2_context_match(
            clean_title, cjk_title, year, season, episode, providers, video_path
        )
        if result:
            return result

        # 第三级：用户确认
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
        """第一级：Provider 精确匹配。

        逻辑：
        1. 用标题+年份搜索 Provider
        2. 对每个搜索结果用 TitleMatcher 计算匹配级别
        3. 如果 L1/L2 精确匹配且唯一 → AUTO_PASS
        4. 如果 L3（精确但无年份）且唯一 → AUTO_PASS
        5. 否则返回 None，进入下一级
        """
        trace_steps = []

        for provider in providers:
            # 优先用 CJK 标题搜索
            search_titles = []
            if cjk_title:
                search_titles.append(cjk_title)
            if clean_title and clean_title != cjk_title:
                search_titles.append(clean_title)
            if not search_titles and clean_title:
                search_titles.append(clean_title)

            for search_title in search_titles:
                try:
                    search_results = provider.search(search_title, year=year)
                except Exception as e:
                    logger.warning(f"Provider {provider.__class__.__name__} 搜索失败: {e}")
                    continue

                if not search_results:
                    continue

                # 对每个结果计算匹配级别
                exact_matches = []
                for item in search_results:
                    match_result = self.title_matcher.match_standard(
                        clean_title, item, year, season
                    )
                    if match_result.level in ("L1", "L2"):
                        exact_matches.append((item, match_result))
                    elif match_result.level == "L3" and year is None:
                        exact_matches.append((item, match_result))

                if len(exact_matches) == 1:
                    # 唯一精确匹配 → AUTO_PASS
                    item, match_result = exact_matches[0]
                    trace_steps.append(MatchTraceStep(
                        tier=1,
                        name="Provider精确匹配",
                        matched=True,
                        search_query=f"{search_title} (year={year})",
                        match_level=match_result.level,
                        reason=f"唯一精确匹配: {item.title} (T={match_result.T:.2f})",
                    ))
                    return MatchResult(
                        match_level="AUTO_PASS",
                        provider_id=item.item_id,
                        provider_title=item.title,
                        match_tier=1,
                        trace_steps=trace_steps,
                        confidence_reason=f"标题精确匹配({match_result.level})，年份{'一致' if year else '无但唯一'}",
                    )

                elif len(exact_matches) > 1:
                    # 多个精确匹配 → 需要进一步判断
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
                    # 无精确匹配
                    if year and search_results:
                        self._pending_concerns.append(MatchConcern(
                            code="FUZZY_TITLE",
                            message=f"标题不完全匹配，最高相似度不足",
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
            # 所有 Provider 都无结果
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
        """第二级：上下文辅助匹配。

        逻辑：
        1. 收集目录上下文（上级文件夹、同级文件等）
        2. 用标题+年份搜索 Provider，获取候选列表
        3. 将候选列表 + 上下文信息交给 AI 判断
        4. AI 高置信度选中 → CONTEXT_PASS
        5. AI 低置信度或无法判断 → 返回 None，进入第三级
        """
        concerns = getattr(self, '_pending_concerns', [])
        trace_steps = getattr(self, '_pending_trace', [])

        # 收集上下文
        context = self._collect_context(video_path) if video_path else {}

        # 收集候选列表
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
                    results = provider.search(search_title, year=year)
                    for item in results[:5]:
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
            if candidates:
                break

        if not candidates:
            trace_steps.append(MatchTraceStep(
                tier=2,
                name="上下文辅助匹配",
                matched=False,
                reason="无候选列表可供 AI 判断",
            ))
            return None

        # 调用 AI 判断
        try:
            from media_importer.scraper.llm_scraper import LLMScraper
            llm = LLMScraper(self.config)
            ai_result = llm.tier2_judge(
                original_filename=video_path,
                clean_title=clean_title,
                cjk_title=cjk_title,
                year=year,
                season=season,
                episode=episode,
                context=context,
                candidates=candidates,
            )
        except Exception as e:
            logger.warning(f"AI 辅助判断失败: {e}")
            concerns.append(MatchConcern(
                code="AI_UNCERTAIN",
                message="AI 辅助判断不可用",
                detail=f"AI 调用失败: {e}",
            ))
            trace_steps.append(MatchTraceStep(
                tier=2,
                name="上下文辅助匹配",
                matched=False,
                reason=f"AI 调用失败: {e}",
            ))
            return None

        selected_index = ai_result.get("selected_index", -1)
        confidence = ai_result.get("confidence", 0)
        ai_reason = ai_result.get("reason", "")

        if selected_index >= 0 and confidence >= 0.7 and selected_index < len(candidates):
            # AI 高置信度选中 → CONTEXT_PASS
            selected = candidates[selected_index]
            trace_steps.append(MatchTraceStep(
                tier=2,
                name="上下文辅助匹配",
                matched=True,
                reason=f"AI 选中: {selected['title']} (置信度={confidence:.2f})",
                ai_reason=ai_reason,
            ))
            return MatchResult(
                match_level="CONTEXT_PASS",
                provider_id=selected.get("id"),
                provider_title=selected.get("title", ""),
                match_tier=2,
                concerns=concerns,
                trace_steps=trace_steps,
                candidates=candidates,
                confidence_reason=f"AI辅助匹配: {ai_reason}",
            )

        # AI 低置信度或未选中 → 进入第三级
        if selected_index < 0 or confidence < 0.7:
            concerns.append(MatchConcern(
                code="AI_UNCERTAIN",
                message=f"AI 无法确定匹配结果（置信度={confidence:.2f}）",
                detail=ai_reason,
            ))
        trace_steps.append(MatchTraceStep(
            tier=2,
            name="上下文辅助匹配",
            matched=False,
            reason=f"AI 未给出高置信度选择 (confidence={confidence:.2f})",
            ai_reason=ai_reason,
        ))
        # 保存 concerns 和 trace 供第三级使用
        self._pending_concerns = concerns
        self._pending_trace = trace_steps
        return None

    def _collect_context(self, video_path: str) -> dict:
        """收集视频文件所在目录的上下文信息。

        当 video_path 只是文件名（无目录部分）时，使用文件名本身作为上下文提示。
        """
        import os as _os
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
            # 非真实路径（仅文件名），用文件名本身作为上下文提示
            context["filename_hint"] = _os.path.basename(video_path)
        return context

    def _tier3_user_confirm(
        self,
        clean_title: str,
        cjk_title: str,
        year: Optional[int],
        season: Optional[int],
        episode: Optional[int],
        providers: list,
    ) -> MatchResult:
        """第三级：用户确认。

        收集 Provider 搜索候选列表，生成疑虑原因，返回 NEEDS_CONFIRM。
        """
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
                    results = provider.search(search_title, year=year)
                    for item in results[:5]:
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
            confidence_reason="；".join(c.message for c in concerns),
        )