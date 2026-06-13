"""三级匹配流程集成测试。

测试 match_engine → review_decision → scrape 的完整流程。
"""

import unittest
from unittest.mock import MagicMock, patch

from media_importer.features.scraping.match_engine import MatchEngine
from media_importer.features.scraping.match_models import MatchResult, MatchConcern
from media_importer.features.import_flow.services.review import ReviewDecisionService


class TestMatchToReviewIntegration(unittest.TestCase):
    """MatchEngine 结果 → ReviewDecisionService 判断的集成测试。"""

    def setUp(self):
        self.review_service = ReviewDecisionService()

    def test_auto_pass_to_review_continue(self):
        """AUTO_PASS → ReviewDecision continue"""
        scraped = {
            "match_level": "AUTO_PASS",
            "title_cn": "盗梦空间",
            "title_en": "Inception",
            "year": 2010,
            "type": "movie",
        }
        decision = self.review_service.evaluate(scraped)
        self.assertEqual(decision.action, "continue")

    def test_context_pass_to_review_continue(self):
        """CONTEXT_PASS → ReviewDecision continue"""
        scraped = {
            "match_level": "CONTEXT_PASS",
            "title_cn": "盗梦空间",
            "title_en": "Inception",
            "year": 2010,
            "type": "movie",
            "match_concerns": [],
        }
        decision = self.review_service.evaluate(scraped)
        self.assertEqual(decision.action, "continue")

    def test_needs_confirm_to_review_confirm(self):
        """NEEDS_CONFIRM → ReviewDecision confirm"""
        scraped = {
            "match_level": "NEEDS_CONFIRM",
            "title_cn": "蜘蛛侠",
            "title_en": "Spider-Man",
            "year": 2002,
            "type": "movie",
            "match_concerns": [
                {"code": "NO_YEAR_MULTI_MATCH", "message": "找到3部同名作品", "detail": "..."},
            ],
        }
        decision = self.review_service.evaluate(scraped)
        self.assertEqual(decision.action, "confirm")
        self.assertIn("3部同名", decision.reason)

    def test_match_result_to_dict_serializable(self):
        """MatchResult.to_dict() 输出可被 ReviewDecisionService 使用"""
        result = MatchResult(
            match_level="NEEDS_CONFIRM",
            provider_id=1,
            provider_title="Test",
            match_tier=3,
            concerns=[MatchConcern(code="FUZZY_TITLE", message="模糊匹配", detail="...")],
        )
        d = result.to_dict()
        scraped = {
            "match_level": d["match_level"],
            "title_cn": "Test",
            "type": "movie",
            "year": 2020,
            "match_concerns": d["concerns"],
        }
        decision = self.review_service.evaluate(scraped)
        self.assertEqual(decision.action, "confirm")


class TestTier2JudgeIntegration(unittest.TestCase):
    """tier2_judge 方法与 MatchEngine 的集成测试。"""

    def test_tier2_judge_returns_valid_structure(self):
        """tier2_judge 返回合法结构（mock AI 调用）"""
        from media_importer.scraper.llm_scraper import LLMScraper
        config = {
            "llm": {
                "api_key": "test",
                "base_url": "https://api.test.com/v1",
                "model": "test-model",
                "fast_model": "test-fast",
                "fast_base_url": "https://api.test.com/v1",
                "fast_api_key": "test",
            }
        }
        scraper = LLMScraper(config)
        mock_response = '{"selected_index": 0, "confidence": 0.85, "reason": "标题精确匹配"}'
        with patch.object(scraper, '_do_call', return_value=mock_response):
            result = scraper.tier2_judge(
                original_filename="Inception.2010.mkv",
                clean_title="Inception",
                year=2010,
                candidates=[{"id": 27205, "title": "Inception", "year": 2010}],
            )
        self.assertEqual(result["selected_index"], 0)
        self.assertAlmostEqual(result["confidence"], 0.85)
        self.assertIn("精确匹配", result["reason"])

    def test_tier2_judge_handles_malformed_response(self):
        """tier2_judge 处理 AI 返回格式错误"""
        from media_importer.scraper.llm_scraper import LLMScraper
        config = {
            "llm": {
                "api_key": "test",
                "base_url": "https://api.test.com/v1",
                "model": "test-model",
                "fast_model": "test-fast",
                "fast_base_url": "https://api.test.com/v1",
                "fast_api_key": "test",
            }
        }
        scraper = LLMScraper(config)
        with patch.object(scraper, '_do_call', return_value="这不是JSON"):
            result = scraper.tier2_judge(
                original_filename="Test.mkv",
                clean_title="Test",
                candidates=[],
            )
        self.assertEqual(result["selected_index"], -1)
        self.assertEqual(result["confidence"], 0.0)


if __name__ == "__main__":
    unittest.main()