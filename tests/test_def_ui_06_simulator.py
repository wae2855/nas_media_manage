#!/usr/bin/env python3
"""Simulator (classify-preview) tests.

Tests that classify-preview returns correct paths for movie and TV filenames.
"""
import os
import shutil
import tempfile
import unittest

from media_importer.features.import_flow.services.classification import ClassificationService


def _make_movie_task(filename="Inception.2010.1080p.BluRay.x264.mkv"):
    return {
        "task_id": "sim-movie-1",
        "source_path": f"/source/{filename}",
        "source_filename": filename,
        "scrape_result": {
            "title_cn": "盗梦空间",
            "title_en": "Inception",
            "year": "2010",
            "dimensions": {"media_type": "movie"},
        },
        "scrape_dimensions": {"media_type": "movie"},
    }


def _make_tv_task(filename="Breaking.Bad.S01E01.1080p.BluRay.x264.mkv"):
    return {
        "task_id": "sim-tv-1",
        "source_path": f"/source/{filename}",
        "source_filename": filename,
        "scrape_result": {
            "title_cn": "绝命毒师",
            "title_en": "Breaking Bad",
            "year": "2008",
            "season": "1",
            "episode": "1",
            "dimensions": {"media_type": "tv"},
        },
        "scrape_dimensions": {"media_type": "tv"},
    }


def _make_config():
    return {
        "base_dir": "/vol1/影视",
        "path_rules": [
            {
                "conditions": {"media_type": "movie"},
                "template": "/vol1/影视/电影/{year}/{title_cn} ({year})/",
            },
            {
                "conditions": {"media_type": "tv"},
                "template": "/vol1/影视/电视剧/{title_cn}/Season {season}/",
            },
        ],
        "fallback_dir": "/vol1/影视/other/",
    }


class TestSimulateMovie(unittest.TestCase):
    """classify-preview with movie filename -> movie path."""

    def test_simulate_movie(self):
        service = ClassificationService(_make_config())
        task = _make_movie_task()
        result = service.preview_classify(task)

        self.assertIn("import_path", result)
        self.assertIn("电影", result["import_path"])
        self.assertIn("盗梦空间", result["import_path"])
        self.assertIn("2010", result["import_path"])
        self.assertEqual(result["final_filename"], "Inception.2010.1080p.BluRay.x264.mkv")

    def test_simulate_movie_full_path(self):
        service = ClassificationService(_make_config())
        task = _make_movie_task()
        result = service.preview_classify(task)

        self.assertTrue(result["full_path"].endswith(".mkv"))
        self.assertIn("电影", result["full_path"])


class TestSimulateTV(unittest.TestCase):
    """classify-preview with TV filename -> tv path with Season."""

    def test_simulate_tv(self):
        service = ClassificationService(_make_config())
        task = _make_tv_task()
        result = service.preview_classify(task)

        self.assertIn("import_path", result)
        self.assertIn("电视剧", result["import_path"])
        self.assertIn("绝命毒师", result["import_path"])
        self.assertIn("Season", result["import_path"])

    def test_simulate_tv_full_path(self):
        service = ClassificationService(_make_config())
        task = _make_tv_task()
        result = service.preview_classify(task)

        self.assertTrue(result["full_path"].endswith(".mkv"))
        self.assertIn("Season", result["full_path"])


class TestSimulateWithOverride(unittest.TestCase):
    """Test classify-preview with override dimensions."""

    def test_override_dimensions_changes_path(self):
        service = ClassificationService(_make_config())
        task = _make_movie_task()

        # Preview as movie
        result_movie = service.preview_classify(task)
        self.assertIn("电影", result_movie["import_path"])

        # Now change the task's dimensions to TV
        task["scrape_result"]["dimensions"] = {"media_type": "tv", "season": "2"}
        result_tv = service.preview_classify(task)
        self.assertIn("电视剧", result_tv["import_path"])
        self.assertIn("Season", result_tv["import_path"])


if __name__ == "__main__":
    unittest.main()
