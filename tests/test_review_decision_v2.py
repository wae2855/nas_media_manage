"""ReviewDecisionService 基于 match_level 的测试。"""

import unittest
from media_importer.features.import_flow.services.review import ReviewDecisionService


class TestReviewDecisionV2(unittest.TestCase):

    def setUp(self):
        self.service = ReviewDecisionService()

    def test_auto_pass_continues(self):
        """AUTO_PASS → continue"""
        decision = self.service.evaluate({"match_level": "AUTO_PASS", "title_cn": "测试", "media_type": "movie", "year": 2020})
        self.assertEqual(decision.action, "continue")

    def test_context_pass_continues(self):
        """CONTEXT_PASS → continue"""
        decision = self.service.evaluate({"match_level": "CONTEXT_PASS", "title_cn": "测试", "media_type": "movie", "year": 2020})
        self.assertEqual(decision.action, "continue")

    def test_needs_confirm_with_concerns(self):
        """NEEDS_CONFIRM 有疑虑 → confirm + 疑虑文案"""
        decision = self.service.evaluate({
            "match_level": "NEEDS_CONFIRM",
            "title_cn": "测试",
            "media_type": "movie",
            "year": 2020,
            "match_concerns": [{"code": "NO_YEAR_MULTI_MATCH", "message": "找到3部同名作品", "detail": "..."}],
        })
        self.assertEqual(decision.action, "confirm")
        messages = [c.get("message", "") for c in decision.concerns]
        self.assertTrue(any("3部同名" in m for m in messages), f"concerns: {decision.concerns}")

    def test_needs_confirm_no_concerns(self):
        """NEEDS_CONFIRM 无疑虑 → confirm + 默认文案"""
        decision = self.service.evaluate({
            "match_level": "NEEDS_CONFIRM",
            "title_cn": "测试",
            "media_type": "movie",
            "year": 2020,
            "match_concerns": [],
        })
        self.assertEqual(decision.action, "confirm")

    def test_empty_scraped(self):
        """空结果 → failed"""
        decision = self.service.evaluate({})
        self.assertEqual(decision.action, "failed")

    def test_missing_title_and_type(self):
        """标题+类型缺失 → confirm + 缺失提示"""
        decision = self.service.evaluate({"year": 2020})
        self.assertEqual(decision.action, "confirm")
        codes = [c.get("code", "") for c in decision.concerns]
        self.assertIn("MISSING_FIELDS", codes)

    def test_year_warning_only(self):
        """有标题有类型但无年份 → 不缺失，只警告"""
        decision = self.service.evaluate({
            "match_level": "AUTO_PASS",
            "title_cn": "测试",
            "media_type": "movie",
        })
        self.assertEqual(decision.action, "continue")
        self.assertTrue(len(decision.warnings) > 0)


if __name__ == "__main__":
    unittest.main()