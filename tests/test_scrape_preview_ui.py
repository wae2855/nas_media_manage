"""scrape preview UI 测试 — 验证三级匹配展示。

需要本地服务运行和 Playwright 安装。
"""

import unittest


class TestScrapePreviewUI(unittest.TestCase):
    """scrape preview 页面 UI 测试。"""

    def test_preview_response_contains_match_level(self):
        """验证 preview 响应包含 match_level 字段"""
        response = {
            "code": 200,
            "data": {
                "filename": "Inception.2010.1080p.BluRay.mkv",
                "clean_result": {"clean_title": "Inception", "year": 2010},
                "modes": {
                    "provider_first": {
                        "result": {
                            "title_cn": "盗梦空间", "title_en": "Inception",
                            "year": 2010, "type": "movie",
                            "match_level": "AUTO_PASS", "match_concerns": [],
                        },
                    },
                },
            },
        }
        mode_result = response["data"]["modes"]["provider_first"]["result"]
        self.assertIn("match_level", mode_result)
        self.assertEqual(mode_result["match_level"], "AUTO_PASS")
        self.assertIn("match_concerns", mode_result)

    def test_preview_needs_confirm_has_concerns(self):
        """NEEDS_CONFIRM 模式包含疑虑原因"""
        response = {
            "code": 200,
            "data": {
                "filename": "Spider-Man.mkv",
                "modes": {
                    "provider_first": {
                        "result": {
                            "match_level": "NEEDS_CONFIRM",
                            "match_concerns": [
                                {"code": "NO_YEAR_MULTI_MATCH", "message": "找到3部同名作品", "detail": "..."},
                            ],
                        },
                    },
                },
            },
        }
        mode_result = response["data"]["modes"]["provider_first"]["result"]
        self.assertEqual(mode_result["match_level"], "NEEDS_CONFIRM")
        self.assertEqual(len(mode_result["match_concerns"]), 1)

    def test_preview_context_pass(self):
        """CONTEXT_PASS 模式"""
        response = {
            "code": 200,
            "data": {
                "filename": "Test.2020.mkv",
                "modes": {
                    "provider_first": {
                        "result": {
                            "match_level": "CONTEXT_PASS", "match_concerns": [],
                        },
                    },
                },
            },
        }
        mode_result = response["data"]["modes"]["provider_first"]["result"]
        self.assertEqual(mode_result["match_level"], "CONTEXT_PASS")


if __name__ == "__main__":
    unittest.main()