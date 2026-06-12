#!/usr/bin/env python3
import os
import tempfile
import unittest

from media_importer.features.import_flow.services.classification import ClassificationService
from media_importer.features.import_flow.utils import PipelineError


def _make_config(path_rules=None, fallback_dir=""):
    return {
        "source_dir": tempfile.mkdtemp(),
        "temp_dir": tempfile.mkdtemp(),
        "path_rules": path_rules or [],
        "fallback_dir": fallback_dir,
        "video_extensions": [".mkv", ".mp4"],
        "subtitle_extensions": [".srt", ".ass"],
        "filename_templates": {
            "movie": "{title_cn}.{title_en}.{year}.{ext}",
            "tv": "{title_cn}.{title_en}.{year}.S{season}E{episode}.{ext}",
        },
    }


class TestClassifyMovie(unittest.TestCase):
    def setUp(self):
        self.config = _make_config(path_rules=[
            {
                "conditions": {"media_type": "movie"},
                "template": "/media/movies/{title_cn}.{year}",
            },
        ])

    def test_classify_movie(self):
        service = ClassificationService(self.config)
        task = {
            "scrape_result": {
                "title_cn": "星际穿越",
                "title_en": "Interstellar",
                "year": "2014",
                "type": "movie",
                "dimensions": {"media_type": "movie"},
            },
            "scrape_dimensions": {"media_type": "movie"},
        }
        result = service.classify_task(task)
        self.assertIn("movies", result.import_path)
        self.assertFalse(result.used_fallback)


class TestClassifyTV(unittest.TestCase):
    def setUp(self):
        self.config = _make_config(path_rules=[
            {
                "conditions": {"media_type": "tv"},
                "template": "/media/tv/{title_cn}/Season {season}",
            },
        ])

    def test_classify_tv(self):
        service = ClassificationService(self.config)
        task = {
            "scrape_result": {
                "title_cn": "绝命毒师",
                "title_en": "Breaking Bad",
                "year": "2008",
                "type": "tv",
                "season": 1,
                "episode": 1,
                "dimensions": {"media_type": "tv", "season": 1},
            },
            "scrape_dimensions": {"media_type": "tv", "season": 1},
        }
        result = service.classify_task(task)
        self.assertIn("tv", result.import_path)
        self.assertFalse(result.used_fallback)


class TestClassifyAnimation(unittest.TestCase):
    def setUp(self):
        self.config = _make_config(path_rules=[
            {
                "conditions": {"media_type": "animation"},
                "template": "/media/anime/{title_cn}",
            },
        ])

    def test_classify_animation(self):
        service = ClassificationService(self.config)
        task = {
            "scrape_result": {
                "title_cn": "进击的巨人",
                "title_en": "Attack on Titan",
                "year": "2013",
                "type": "tv",
                "dimensions": {"media_type": "animation"},
            },
            "scrape_dimensions": {"media_type": "animation"},
        }
        result = service.classify_task(task)
        self.assertIn("anime", result.import_path)
        self.assertFalse(result.used_fallback)


class TestClassifyNoMatchFallback(unittest.TestCase):
    def setUp(self):
        self.config = _make_config(
            path_rules=[
                {
                    "conditions": {"media_type": "movie"},
                    "template": "/media/movies/{title_cn}",
                },
            ],
            fallback_dir="/media/unsorted",
        )

    def test_classify_no_match_fallback(self):
        service = ClassificationService(self.config)
        task = {
            "scrape_result": {
                "title_cn": "未知视频",
                "type": "other",
                "dimensions": {"media_type": "other"},
            },
            "scrape_dimensions": {"media_type": "other"},
        }
        result = service.classify_task(task)
        self.assertTrue(result.used_fallback)
        self.assertIn("unsorted", result.import_path)


class TestClassifyNoMatchNoFallback(unittest.TestCase):
    def setUp(self):
        self.config = _make_config(
            path_rules=[
                {
                    "conditions": {"media_type": "movie"},
                    "template": "/media/movies/{title_cn}",
                },
            ],
            fallback_dir="",
        )

    def test_classify_no_match_no_fallback(self):
        service = ClassificationService(self.config)
        task = {
            "scrape_result": {
                "title_cn": "未知视频",
                "type": "other",
                "dimensions": {"media_type": "other"},
            },
            "scrape_dimensions": {"media_type": "other"},
        }
        result = service.classify_task(task)
        self.assertEqual(result.import_path, "")
        # In the pipeline, empty import_path raises PipelineError
        if not result.import_path:
            error = PipelineError(
                f"分类匹配失败，无匹配规则。维度=[{result.dimensions_text}]"
            )
        self.assertIsInstance(error, PipelineError)


if __name__ == "__main__":
    unittest.main()
