"""FilenameCleaner 单元测试（从 test_confidence_engine.py 迁移）。"""

import unittest
from media_importer.scraper.filename_cleaner import FilenameCleaner


class TestFilenameCleaner(unittest.TestCase):
    def setUp(self):
        self.cleaner = FilenameCleaner()

    def test_basic_clean(self):
        result = self.cleaner.clean("Joker.2019.1080p.BluRay.x264.mkv")
        self.assertEqual(result.clean_title, "Joker")
        self.assertEqual(result.year, 2019)

    def test_tv_show(self):
        result = self.cleaner.clean("[YYeTs].Gintama.S01E01.720p.mkv")
        self.assertEqual(result.season, 1)
        self.assertEqual(result.episode, 1)

    def test_chinese_bare_episode(self):
        result = self.cleaner.clean("大汉王朝01.mkv")
        self.assertEqual(result.clean_title, "大汉王朝")
        self.assertEqual(result.season, 1)
        self.assertEqual(result.episode, 1)

    def test_chinese_episode_does_not_match_plain_title(self):
        result = self.cleaner.clean("美丽人生.mkv")
        self.assertEqual(result.season, None)
        self.assertEqual(result.episode, None)


if __name__ == "__main__":
    unittest.main()