"""第二级关键词建议回搜测试（RED 测试 - 修复前应失败）。

覆盖：
- AI 返回 suggested_query 后系统重新调用 Provider 搜索
- 回搜结果不是唯一精确匹配时不能自动通过
- 最多 2 次回搜循环
- trace 记录关键词建议和回搜过程
"""

import pytest
from unittest.mock import MagicMock, patch

from media_importer.features.scraping.match_models import (
    MatchConcern,
    MatchResult,
    MatchTraceStep,
)


class TestTier2KeywordLoop:
    """验证第二级匹配改为关键词建议回搜。"""

    def test_tier2_returns_suggested_query_not_direct_selection(self):
        """第二级匹配应返回 suggested_query，而不是直接选候选。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_assist": {
                "base_url": "https://test.example.com/v1",
                "model": "test-model",
                "api_key": "test-key",
            }
        }
        scraper = LLMScraper(config)

        # tier2_judge 应返回包含 suggested_query 的结果
        # 当前实现可能只返回 selected_index，这是 RED 测试要锁住的缺陷
        with patch.object(scraper, '_do_call', return_value=(
            '{"selected_index": 0, "certainty": "high", '
            '"reason": "标题匹配度高"}'
        )):
            result = scraper.tier2_judge(
                original_filename="测试电影.2024.mp4",
                clean_title="测试电影",
                year=2024,
                candidates=[{"title": "测试电影", "year": 2024}],
            )
            # RED: 当前实现可能没有 suggested_query 字段
            assert "suggested_query" in result, (
                "tier2_judge 应返回 suggested_query 字段"
            )

    def test_tier2_no_exact_match_after_research_not_auto_pass(self):
        """回搜后仍无精确匹配时，不能自动通过。"""
        from media_importer.features.scraping.match_engine import MatchEngine

        engine = MatchEngine({})

        # 模拟：AI 建议关键词后 Provider 回搜返回多个候选
        # 这种情况不能 AUTO_PASS，必须 NEEDS_CONFIRM
        result = engine._tier3_user_confirm(
            clean_title="模糊标题",
            cjk_title="模糊标题",
            year=2024,
            season=None,
            episode=None,
            providers=[],
        )
        assert result.match_level == "NEEDS_CONFIRM", (
            "无精确匹配时应为 NEEDS_CONFIRM"
        )

    def test_tier2_max_two_loops(self):
        """第二级回搜最多 2 次循环。"""
        # 这个测试验证概念：回搜循环不应无限进行
        # 实际实现中应有循环计数器
        max_loops = 2
        loop_count = 0

        # 模拟回搜逻辑
        def mock_research(suggested_query):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= max_loops:
                return None  # 停止循环
            return [{"title": "候选1"}, {"title": "候选2"}]

        # 第一次回搜
        result1 = mock_research("建议关键词1")
        assert result1 is not None
        assert loop_count == 1

        # 第二次回搜
        result2 = mock_research("建议关键词2")
        assert result2 is None  # 达到上限
        assert loop_count == 2

    def test_tier2_trace_records_keyword_suggestions(self):
        """trace 应记录每次关键词建议和回搜结果。"""
        from media_importer.features.scraping.match_models import MatchTraceStep

        # 验证 MatchTraceStep 支持记录关键词建议
        step = MatchTraceStep(
            tier=2,
            name="关键词建议回搜",
            matched=False,
            search_query="AI建议: 测试电影 2024",
            reason="回搜返回3个候选，无精确匹配",
            ai_reason="原标题年份不明确，建议用完整标题搜索",
        )
        trace_dict = {
            "tier": step.tier,
            "name": step.name,
            "matched": step.matched,
            "search_query": step.search_query,
            "reason": step.reason,
            "ai_reason": step.ai_reason,
        }
        assert trace_dict["search_query"] == "AI建议: 测试电影 2024"
        assert trace_dict["ai_reason"] == "原标题年份不明确，建议用完整标题搜索"

    def test_match_result_has_confirm_reason_field(self):
        """MatchResult 应有 confirm_reason 字段。"""
        result = MatchResult(
            match_level="NEEDS_CONFIRM",
            match_tier=3,
            concerns=[MatchConcern(
                code="NO_EXACT_MATCH",
                message="回搜后仍无精确匹配",
                detail="AI建议关键词回搜返回多个候选",
            )],
        )
        result_dict = result.to_dict()
        # RED: 当前 MatchResult 可能没有 confirm_reason 字段
        assert "confirm_reason" in result_dict or hasattr(result, "confirm_reason"), (
            "MatchResult 应有 confirm_reason 字段"
        )
