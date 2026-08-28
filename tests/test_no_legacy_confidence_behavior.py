"""清理旧置信度表面后的行为测试。

刮削结果只表达 match_level / match_concerns / match_trace / confirm_reason / dim_sources。
"""

import unittest

from media_importer.features.import_flow.services.review import ReviewDecisionService


class TestReviewDecisionByMatchLevel(unittest.TestCase):
    """ReviewDecision 只看 match_level，不依赖 confidence 数值。"""

    def setUp(self):
        self.service = ReviewDecisionService()

    def test_needs_confirm_decision_only_uses_match_level(self):
        """NEEDS_CONFIRM 即使无 confidence 数值也返回 confirm"""
        scraped = {
            "title_cn": "A",
            "media_type": "movie",
            "year": 2024,
            "match_level": "NEEDS_CONFIRM",
            "match_concerns": [{"code": "X", "message": "需要确认"}],
        }
        decision = self.service.evaluate(scraped)
        self.assertEqual(decision.action, "confirm")
        messages = [c.get("message", "") for c in decision.concerns]
        self.assertIn("需要确认", messages)

    def test_auto_pass_with_no_confidence_field(self):
        scraped = {
            "title_cn": "A",
            "media_type": "movie",
            "year": 2024,
            "match_level": "AUTO_PASS",
        }
        decision = self.service.evaluate(scraped)
        self.assertEqual(decision.action, "continue")


if __name__ == "__main__":
    unittest.main()
