"""TitleMatcher 单元测试（从 test_confidence_engine.py 迁移）。"""

import unittest
from media_importer.scraper.title_matcher import TitleMatcher


class TestTitleMatcher(unittest.TestCase):
    def setUp(self):
        self.matcher = TitleMatcher()

    def test_exact_with_year(self):
        result = self.matcher.match(
            "Joker",
            {"title": "Joker", "release_date": "2019-10-04"},
            year=2019,
        )
        self.assertEqual(result.level, "L1")
        self.assertAlmostEqual(result.T, 1.0)

    def test_year_mismatch(self):
        result = self.matcher.match(
            "Joker",
            {"title": "Joker", "release_date": "2016-01-01"},
            year=2019,
        )
        self.assertEqual(result.level, "L4")


if __name__ == "__main__":
    unittest.main()