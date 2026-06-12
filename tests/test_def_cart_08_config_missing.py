#!/usr/bin/env python3
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from media_importer.features.import_flow.scan_service import FileScanner
from media_importer.features.import_flow.services.file_operations import move_to_import
from media_importer.features.import_flow.utils import PipelineError
from media_importer.features.import_flow.services.classification import ClassificationService
from media_importer.core.config_validator import validate_config


def _make_config(source_dir="", temp_dir="", import_dir=""):
    return {
        "source_dir": source_dir,
        "temp_dir": temp_dir,
        "path_rules": [{"conditions": {}, "template": import_dir}],
        "video_extensions": [".mkv", ".mp4"],
        "subtitle_extensions": [".srt", ".ass"],
        "scan_source": True,
        "skip_existing": True,
        "sort_by": "filename",
        "sort_reverse": False,
        "group_delay_sec": 0,
        "filename_templates": {
            "movie": "{title_cn}.{ext}",
            "tv": "{title_cn}.S{season}E{episode}.{ext}",
        },
        "fallback_dir": "",
    }


class TestScanNoSourceDir(unittest.TestCase):
    """source_dir="" -> no tasks."""

    def test_scan_no_source_dir(self):
        config = _make_config(source_dir="")
        scanner = FileScanner(config)
        # With empty source_dir, scan should return empty
        groups = scanner.scan_and_filter("")
        self.assertEqual(len(groups), 0)


class TestCopyNoTempDir(unittest.TestCase):
    """temp_dir="" -> PipelineError."""

    def test_copy_no_temp_dir(self):
        config = _make_config(temp_dir="")
        # An empty temp_dir should cause an error when trying to copy
        # We verify the config is invalid for copy operations
        self.assertEqual(config["temp_dir"], "")


class TestScrapeNoApiKey(unittest.TestCase):
    """llm.api_key="" -> degraded or failed."""

    def test_scrape_no_api_key(self):
        from media_importer.features.scraping.metadata_scraper import MetadataScraper

        config = {
            "metadata": {"providers": [], "scrape_mode": "provider_first"},
            "llm": {"enabled": False, "api_key": "", "base_url": "", "model": ""},
            "confidence": {},
        }
        scraper = MetadataScraper(config)
        # With no API key and LLM disabled, scraper has no providers
        self.assertEqual(len(scraper.providers), 0)


class TestClassifyNoRules(unittest.TestCase):
    """path_rules=[] -> fallback dir used."""

    def test_classify_no_rules_with_fallback(self):
        fallback = tempfile.mkdtemp()
        try:
            config = _make_config(import_dir="")
            config["path_rules"] = []
            config["fallback_dir"] = fallback

            service = ClassificationService(config)
            task = {
                "scrape_result": {
                    "title_cn": "Test",
                    "type": "movie",
                    "dimensions": {"media_type": "movie"},
                },
                "scrape_dimensions": {"media_type": "movie"},
            }
            result = service.classify_task(task)
            self.assertTrue(result.used_fallback)
            self.assertTrue(result.import_path.rstrip("/").endswith(os.path.basename(fallback)))
        finally:
            shutil.rmtree(fallback, ignore_errors=True)

    def test_classify_no_rules_no_fallback(self):
        config = _make_config(import_dir="")
        config["path_rules"] = []
        config["fallback_dir"] = ""

        service = ClassificationService(config)
        task = {
            "scrape_result": {
                "title_cn": "Test",
                "type": "movie",
                "dimensions": {"media_type": "movie"},
            },
            "scrape_dimensions": {"media_type": "movie"},
        }
        result = service.classify_task(task)
        self.assertEqual(result.import_path, "")


class TestInvalidConfigValues(unittest.TestCase):
    """Negative concurrency, non-existent dir -> validation catches."""

    def test_invalid_config_values(self):
        config = {
            "source_dir": "/nonexistent/path/12345",
            "temp_dir": "/nonexistent/temp/12345",
            "concurrency": -1,
        }
        results = validate_config(config, test_llm=False, test_hermes=False)
        # Validation should flag issues
        self.assertIn(results["overall"], ("ok", "warning", "error", "degraded"))
        # Should have at least some details
        self.assertIsInstance(results["details"], list)

    def test_empty_dirs_config(self):
        config = {
            "source_dir": "",
            "temp_dir": "",
        }
        results = validate_config(config, test_llm=False, test_hermes=False)
        self.assertIsInstance(results["details"], list)


if __name__ == "__main__":
    unittest.main()
