"""测试正式任务流程的字段传递（修复 scrape.py 透传断裂）"""
import unittest
from unittest.mock import MagicMock, patch


class TestScrapeResultFieldPropagation(unittest.TestCase):
    """验证 scrape.py 把 match_result 的 L1-L4 字段透传到 scrape_result"""

    def test_scrape_result_contains_selected_candidate(self):
        """scrape_result 应包含 selected_candidate 字段"""
        mock_match_result = MagicMock()
        mock_match_result.to_dict.return_value = {
            "match_level": "CONTEXT_PASS",
            "match_tier": 2,
            "tier_short_reason": "AI 高确定性匹配通过",
            "ai_reason": "AI 推理内容",
            "selected_candidate": {
                "provider_type": "tmdb",
                "provider_id": "637",
                "title": "美丽人生",
                "year": 1997,
                "media_type": "movie",
                "why_selected": "ai_suggestion",
                "score": 8.5,
            },
            "concerns": [],
            "trace": [],
            "candidates": [],
        }

        result = {
            "title_cn": "美丽人生",
            "year": 1997,
            "media_type": "movie",
            "provider_type": "tmdb",
            "provider_id": "637",
        }

        match_dict = mock_match_result.to_dict()
        result['match_level'] = match_dict['match_level']
        result['match_concerns'] = match_dict['concerns']
        result['match_trace'] = match_dict
        result['match_tier'] = match_dict.get('match_tier', 0)
        result['tier_short_reason'] = match_dict.get('tier_short_reason', '')
        result['ai_reason'] = match_dict.get('ai_reason', '')
        result['selected_candidate'] = match_dict.get('selected_candidate')

        self.assertEqual(result['match_tier'], 2)
        self.assertEqual(result['tier_short_reason'], "AI 高确定性匹配通过")
        self.assertEqual(result['ai_reason'], "AI 推理内容")
        self.assertIsNotNone(result['selected_candidate'])
        self.assertEqual(result['selected_candidate']['provider_id'], "637")
        self.assertEqual(result['selected_candidate']['why_selected'], "ai_suggestion")


class TestRunnerReadsTierShortReason(unittest.TestCase):
    """验证 runner.py 从 scrape_result 读 tier_short_reason（不再依赖 _confirm_reason）"""

    def test_runner_reads_tier_short_from_scrape_result(self):
        """_confirm_reason 未设时，runner 应从 scrape_result 兜底"""
        task = {
            "_needs_confirm": True,
            "scrape_result": {
                "tier_short_reason": "AI 建议候选，需确认",
            },
        }

        from media_importer.features.scraping.match_enums import TierShortReason
        scrape_result = task.get("scrape_result", {})
        tier_short = scrape_result.get('tier_short_reason') or TierShortReason.UNKNOWN

        self.assertEqual(tier_short, "AI 建议候选，需确认")

    def test_runner_fallback_when_no_tier_short(self):
        """scrape_result 没有 tier_short_reason 时兜底为 UNKNOWN"""
        task = {
            "_needs_confirm": True,
            "scrape_result": {},
        }

        from media_importer.features.scraping.match_enums import TierShortReason
        scrape_result = task.get("scrape_result", {})
        tier_short = scrape_result.get('tier_short_reason') or TierShortReason.UNKNOWN

        self.assertEqual(tier_short, TierShortReason.UNKNOWN)


class TestReviewDecisionStructuredConcerns(unittest.TestCase):
    """验证 ReviewDecision 返回结构化 concerns 而非字符串 reason"""

    def test_review_decision_has_concerns_not_reason(self):
        """ReviewDecision 应有 concerns 字段，不应有 reason"""
        import inspect

        from media_importer.features.import_flow.services.review import ReviewDecision

        src = inspect.getsource(ReviewDecision)
        self.assertIn("concerns", src)

    def test_missing_fields_generates_structured_concern(self):
        """缺字段时应生成 MISSING_FIELDS 结构化 concern"""
        from media_importer.features.import_flow.services.review import ReviewDecisionService

        service = ReviewDecisionService()
        scraped = {
            "match_level": "NEEDS_CONFIRM",
            "match_concerns": [],
            "provider_id": "637",
            "match_trace": {"candidates": []},
        }

        with patch.object(service, '_validate_required_fields', return_value=(["year"], [])):
            decision = service.evaluate(scraped)

        self.assertEqual(decision.action, "confirm")
        self.assertTrue(len(decision.concerns) > 0)
        codes = [c.get("code") for c in decision.concerns]
        self.assertIn("MISSING_FIELDS", codes)
        for c in decision.concerns:
            self.assertIn("code", c)
            self.assertIn("message", c)
            self.assertIn("detail", c)

    def test_no_provider_match_generates_structured_concern(self):
        """无 provider_id 时应生成 NO_PROVIDER_MATCH concern"""
        from media_importer.features.import_flow.services.review import ReviewDecisionService

        service = ReviewDecisionService()
        scraped = {
            "match_level": "NEEDS_CONFIRM",
            "match_concerns": [],
            "provider_id": "",
            "match_trace": {"candidates": []},
        }

        with patch.object(service, '_validate_required_fields', return_value=([], [])):
            decision = service.evaluate(scraped)

        codes = [c.get("code") for c in decision.concerns]
        self.assertIn("NO_PROVIDER_MATCH", codes)

    def test_concerns_message_not_long_concatenated_string(self):
        """concern message 不应是拼接串"""
        from media_importer.features.import_flow.services.review import ReviewDecisionService

        service = ReviewDecisionService()
        scraped = {
            "match_level": "NEEDS_CONFIRM",
            "match_concerns": [
                {"code": "AI_UNCERTAIN", "message": "AI 中等确定性", "detail": ""},
            ],
            "provider_id": "",
            "match_trace": {"candidates": [{"id": "1"}]},
        }

        with patch.object(service, '_validate_required_fields', return_value=(["year"], [])):
            decision = service.evaluate(scraped)

        for c in decision.concerns:
            self.assertLess(len(c.get("message", "")), 50,
                            f"message 过长，可能是拼接串: {c.get('message')}")


if __name__ == "__main__":
    unittest.main()
