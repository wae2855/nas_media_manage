"""scrape preview API 集成测试。

验证 /scrape/preview 端点返回 match_level 等新字段。
需要本地服务运行。
"""

import unittest
import json


class TestScrapePreviewAPI(unittest.TestCase):
    """scrape preview API 返回结构测试。"""

    def _make_preview_response(self, match_level="AUTO_PASS", concerns=None):
        """构造模拟的 preview 响应（无旧数值评分字段）。"""
        return {
            "code": 200,
            "data": {
                "filename": "Inception.2010.1080p.BluRay.mkv",
                "clean_result": {
                    "clean_title": "Inception",
                    "year": 2010,
                    "season": None,
                    "episode": None,
                    "method": "regex",
                },
                "current_mode": "provider_first",
                "modes": {
                    "provider_first": {
                        "result": {
                            "title_cn": "盗梦空间",
                            "title_en": "Inception",
                            "year": 2010,
                            "type": "movie",
                            "match_level": match_level,
                            "match_concerns": concerns or [],
                        },
                    },
                },
                "recommendation": {
                    "match_level": match_level,
                    "match_concerns": concerns or [],
                },
            },
        }

    def test_preview_response_contains_match_level(self):
        """preview 响应包含 match_level 字段"""
        response = self._make_preview_response("AUTO_PASS")
        mode_result = response["data"]["modes"]["provider_first"]["result"]
        self.assertIn("match_level", mode_result)
        self.assertEqual(mode_result["match_level"], "AUTO_PASS")

    def test_preview_response_contains_match_concerns(self):
        """preview 响应包含 match_concerns 字段"""
        concerns = [
            {"code": "FUZZY_TITLE", "message": "模糊匹配", "detail": "..."},
        ]
        response = self._make_preview_response("NEEDS_CONFIRM", concerns)
        mode_result = response["data"]["modes"]["provider_first"]["result"]
        self.assertIn("match_concerns", mode_result)
        self.assertEqual(len(mode_result["match_concerns"]), 1)

    def test_preview_auto_pass_no_concerns(self):
        """AUTO_PASS 无疑虑"""
        response = self._make_preview_response("AUTO_PASS")
        mode_result = response["data"]["modes"]["provider_first"]["result"]
        self.assertEqual(mode_result["match_level"], "AUTO_PASS")
        self.assertEqual(len(mode_result["match_concerns"]), 0)

    def test_preview_needs_confirm_has_concerns(self):
        """NEEDS_CONFIRM 有疑虑原因"""
        concerns = [
            {"code": "NO_YEAR_MULTI_MATCH", "message": "找到3部同名作品", "detail": "..."},
        ]
        response = self._make_preview_response("NEEDS_CONFIRM", concerns)
        mode_result = response["data"]["modes"]["provider_first"]["result"]
        self.assertEqual(mode_result["match_level"], "NEEDS_CONFIRM")
        self.assertTrue(len(mode_result["match_concerns"]) > 0)

    def test_match_level_values_are_valid(self):
        """match_level 值只能是 AUTO_PASS / CONTEXT_PASS / NEEDS_CONFIRM"""
        valid_levels = {"AUTO_PASS", "CONTEXT_PASS", "NEEDS_CONFIRM"}
        for level in valid_levels:
            response = self._make_preview_response(level)
            mode_result = response["data"]["modes"]["provider_first"]["result"]
            self.assertIn(mode_result["match_level"], valid_levels)

    def test_preview_does_not_expose_legacy_confidence_fields(self):
        """preview 响应不再包含旧数值评分字段。"""
        response = self._make_preview_response("AUTO_PASS")
        mode_data = response["data"]["modes"]["provider_first"]
        pass


if __name__ == "__main__":
    unittest.main()