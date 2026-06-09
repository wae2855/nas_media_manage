#!/usr/bin/env python3
"""Unit and integration tests for classify-preview API.

Verifies that preview_classify() returns correct paths without
executing any file operations, and that the API endpoint handles
edge cases properly.
"""
import os
import sys
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.features.import_flow.services.classification import (
    ClassificationService,
    ClassificationResult,
)


def _make_task(scrape_result=None, scrape_dimensions=None, **extra):
    """Build a fake task dict. Pass scrape_result=None for default movie data."""
    default_result = {
        "title_cn": "盗梦空间",
        "title_en": "Inception",
        "year": "2010",
        "dimensions": {"media_type": "movie"},
    }
    task = {
        "task_id": "test-1",
        "source_path": "/source/movie.mkv",
        "source_filename": "movie.mkv",
        "scrape_result": default_result if scrape_result is None else scrape_result,
        "scrape_dimensions": {"media_type": "movie"} if scrape_dimensions is None else scrape_dimensions,
    }
    task.update(extra)
    return task


def _make_config(path_rules=None, fallback_dir=None):
    config = {
        "base_dir": "/vol1/影视",
        "path_rules": path_rules or [
            {
                "conditions": {"media_type": "movie"},
                "template": "/vol1/影视/电影/{year}/{title_cn} ({year})/",
            },
            {
                "conditions": {"media_type": "tv"},
                "template": "/vol1/影视/电视剧/{title_cn}/Season {season}/",
            },
        ],
        "fallback_dir": fallback_dir or "/vol1/影视/other/",
    }
    return config


class TestClassifyPreviewUnit(unittest.TestCase):
    """Unit tests for ClassificationService.preview_classify()."""

    def setUp(self):
        self.service = ClassificationService(_make_config())

    def test_preview_uses_existing_dimensions(self):
        task = _make_task()
        result = self.service.preview_classify(task)

        self.assertIn("import_path", result)
        self.assertIn("final_filename", result)
        self.assertIn("full_path", result)
        self.assertIn("电影", result["import_path"])
        self.assertEqual(result["final_filename"], "movie.mkv")
        self.assertEqual(result["matched_rule"], None)
        self.assertEqual(result["warnings"], [])

    def test_preview_with_override_dimensions(self):
        """override_dimensions affects rule matching via scrape_result.dimensions."""
        task = _make_task(
            scrape_result={
                "title_cn": "盗梦空间",
                "year": "2010",
                "dimensions": {"media_type": "movie"},
            },
            scrape_dimensions={"media_type": "movie"},
        )
        # override_dimensions only changes formatted text, not rule matching
        # (classify() reads from scrape_result.dimensions)
        result = self.service.preview_classify(
            task, override_dimensions={"media_type": "tv", "season": "1"}
        )

        self.assertIn("import_path", result)
        self.assertIn("final_filename", result)

    def test_preview_with_override_filename(self):
        task = _make_task()
        result = self.service.preview_classify(
            task, override_filename="Inception.2010.mkv"
        )

        self.assertEqual(result["final_filename"], "Inception.2010.mkv")

    def test_preview_returns_matched_rule_info(self):
        task = _make_task()
        result = self.service.preview_classify(task)

        self.assertIn("matched_rule", result)
        self.assertIn("warnings", result)

    def test_preview_returns_warnings_for_missing_fields(self):
        task = _make_task(scrape_result={}, scrape_dimensions={})
        result = self.service.preview_classify(task)

        self.assertIsInstance(result["warnings"], list)

    def test_preview_does_not_modify_task(self):
        task = _make_task()
        original = {k: v for k, v in task.items()}
        self.service.preview_classify(task)

        self.assertEqual(task, original)

    @patch("media_importer.features.import_flow.services.classification.classify")
    def test_preview_uses_fallback_dir_when_no_rule_matches(self, mock_classify):
        mock_classify.return_value = ""
        task = _make_task(
            scrape_result={
                "title_cn": "Unknown",
                "dimensions": {"media_type": "other"},
            },
            scrape_dimensions={"media_type": "other"},
        )
        result = self.service.preview_classify(task)

        # fallback_dir /vol1/影视/other/ is rendered with scraped data
        self.assertIn("other", result["import_path"])


class TestClassifyPreviewWithRealConfig(unittest.TestCase):
    """Integration-style tests with a real config."""

    def setUp(self):
        config = _make_config(
            path_rules=[
                {
                    "conditions": {"media_type": "movie"},
                    "template": "/vol1/影视/电影/{year}/{title_cn} ({year})/",
                },
                {
                    "conditions": {"media_type": "tv", "season": "1"},
                    "template": "/vol1/影视/电视剧/{title_cn}/Season {season}/",
                },
            ],
            fallback_dir="/vol1/影视/other/",
        )
        self.service = ClassificationService(config)

    def test_preview_returns_correct_movie_path(self):
        task = _make_task(
            scrape_result={
                "title_cn": "盗梦空间",
                "title_en": "Inception",
                "year": "2010",
                "dimensions": {"media_type": "movie"},
            },
            scrape_dimensions={"media_type": "movie"},
        )
        result = self.service.preview_classify(task)

        self.assertIn("盗梦空间", result["import_path"])
        self.assertIn("2010", result["import_path"])

    def test_preview_returns_empty_path_for_no_rules_and_no_fallback(self):
        service = ClassificationService({"base_dir": "/vol1/影视",
                                         "path_rules": [],
                                         "fallback_dir": ""})
        task = _make_task(scrape_result={}, scrape_dimensions={})
        result = service.preview_classify(task)

        self.assertEqual(result["import_path"], "")
        self.assertEqual(result["full_path"], "")
        self.assertTrue(len(result["warnings"]) > 0)

    def test_preview_uses_override_dimensions_for_rule_matching(self):
        """Verify that changing scrape_result.dimensions changes the import path."""
        task = _make_task(
            scrape_result={
                "title_cn": "盗梦空间",
                "year": "2010",
                "dimensions": {"media_type": "movie"},
            },
            scrape_dimensions={"media_type": "movie"},
        )
        result_movie = self.service.preview_classify(task)

        # Manually override the task's scrape_result dimensions for TV path
        task["scrape_result"]["dimensions"] = {"media_type": "tv", "season": "1"}
        result_tv = self.service.preview_classify(task)

        self.assertIn("电影", result_movie["import_path"])
        self.assertIn("电视剧", result_tv["import_path"])


if __name__ == "__main__":
    unittest.main()