#!/usr/bin/env python3
import os
import sys
import unittest
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.features.configuration import ConfigView
from media_importer.features.scraping import LLMScraper
from media_importer.storage.file_scanner import FileScanner
from media_importer.storage.source_cleaner import SourceCleaner


class TestConfigViewDefaults(unittest.TestCase):
    def test_defaults_match_loader_runtime_defaults(self):
        view = ConfigView.from_dict({})

        self.assertEqual(view.paths.log_dir, "logs")
        self.assertEqual(view.source_policy.cleanup_source_after_done, True)
        self.assertEqual(view.source_policy.recycle_retention_days, 30)
        self.assertEqual(view.source_policy.scan_recursive, True)
        self.assertEqual(view.source_policy.scan_max_depth, 5)
        self.assertEqual(view.dedup.strategy, "skip")
        self.assertEqual(view.dedup.enabled, True)
        self.assertEqual(view.manual_review.enabled, False)
        self.assertEqual(view.llm.base_url, "https://api.openai.com/v1")
        self.assertEqual(view.llm.model, "gpt-3.5-turbo")
        self.assertEqual(view.source_cleaner.cleanup_mode, "media_only")
        self.assertEqual(view.source_cleaner.delete_extensions, (".url", ".log", ".txt"))

    def test_normalizes_extensions(self):
        view = ConfigView.from_dict({
            "video_extensions": ["mkv", ".MP4"],
            "subtitle_extensions": ["srt", ".ASS"],
            "source_cleaner": {
                "delete_extensions": ["url", ".LOG"],
                "protect_extensions": ["nfo", ".JPG"],
            },
        })

        self.assertEqual(view.paths.video_extensions, (".mkv", ".mp4"))
        self.assertEqual(view.paths.subtitle_extensions, (".srt", ".ass"))
        self.assertEqual(view.source_cleaner.delete_extensions, (".url", ".log"))
        self.assertEqual(view.source_cleaner.protect_extensions, (".nfo", ".jpg"))

    def test_keeps_raw_config_available(self):
        config = {"source_dir": "/source"}

        view = ConfigView.from_dict(config)

        self.assertIs(view.raw, config)
        self.assertEqual(view.paths.source_dir, "/source")

    def test_filename_template_dict_preserves_custom_values(self):
        view = ConfigView.from_dict({
            "filename_templates": {"movie": "{title_cn}.{ext}"},
        })

        templates = view.filename_template_dict()

        self.assertEqual(templates["movie"], "{title_cn}.{ext}")
        self.assertIn("tv", templates)
        self.assertIn("subtitle", templates)

    def test_llm_fast_values_fallback_to_primary(self):
        view = ConfigView.from_dict({
            "llm": {
                "api_key": "secret",
                "base_url": "https://llm.example/v1",
                "model": "main-model",
            }
        })

        self.assertEqual(view.llm.effective_fast_api_key, "secret")
        self.assertEqual(view.llm.effective_fast_base_url, "https://llm.example/v1")
        self.assertEqual(view.llm.effective_fast_model, "main-model")

    def test_source_cleaner_model_preserves_historical_default(self):
        view = ConfigView.from_dict({"llm": {"api_key": "secret"}})

        self.assertEqual(view.llm.source_cleaner_model, "gpt-4o-mini")

    def test_repository_config_example_loads_into_config_view(self):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config.yaml.example",
        )
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        view = ConfigView.from_dict(config)

        self.assertEqual(view.paths.source_dir, "/vol1/网盘下载")
        self.assertGreater(len(view.paths.path_rules), 0)
        self.assertIn(".mkv", view.paths.video_extensions)
        self.assertIn(".srt", view.paths.subtitle_extensions)
        self.assertEqual(view.dedup.strategy, "quality")
        self.assertEqual(
            view.source_policy.recycle_dir,
            "/vol1/@appdata/nas-media-importer/data/recycle",
        )


class TestConfigViewConsumers(unittest.TestCase):
    def test_file_scanner_uses_config_view_extensions(self):
        scanner = FileScanner({
            "video_extensions": ["mkv"],
            "subtitle_extensions": ["srt"],
            "sort_by": "size",
            "sort_reverse": True,
        })

        self.assertEqual(scanner.video_extensions, (".mkv",))
        self.assertEqual(scanner.subtitle_extensions, (".srt",))
        self.assertEqual(scanner.sort_by, "size")
        self.assertEqual(scanner.sort_reverse, True)

    def test_source_cleaner_uses_config_view_defaults_and_overrides(self):
        cleaner = SourceCleaner({
            "source_dir": "/source",
            "source_policy": {"recycle_dir": "/recycle"},
            "video_extensions": ["mkv"],
            "subtitle_extensions": ["srt"],
            "source_cleaner": {
                "cleanup_mode": "media_only",
                "delete_extensions": ["url"],
            },
        })

        self.assertEqual(cleaner.source_dir, "/source")
        self.assertEqual(cleaner.recycle_dir, "/recycle")
        self.assertEqual(cleaner.delete_extensions, {".url"})
        self.assertEqual(cleaner.media_extensions, {".mkv", ".srt"})

    def test_llm_scraper_uses_config_view_llm_values(self):
        scraper = LLMScraper({
            "llm": {
                "api_key": "secret",
                "base_url": "https://llm.example/v1",
                "model": "main-model",
                "fast_model": "fast-model",
                "fast_api_key": "fast-secret",
                "fast_base_url": "https://fast.example/v1",
            }
        })

        self.assertEqual(scraper.api_key, "secret")
        self.assertEqual(scraper.base_url, "https://llm.example/v1")
        self.assertEqual(scraper.fast_model, "fast-model")
        self.assertEqual(scraper.fast_api_key, "fast-secret")
        self.assertEqual(scraper.fast_base_url, "https://fast.example/v1")


class TestLLMConfigIsEffective(unittest.TestCase):
    """Verify that LLMConfig.is_effective() depends only on field completeness.

    As of 2026-06, the legacy `enabled` field is ignored. AI is available iff
    api_key + base_url + model are all non-empty.
    """

    def test_effective_when_all_filled_enabled_true(self):
        from media_importer.core.config_view import LLMConfig
        cfg = LLMConfig(
            enabled=True, api_key="sk-xxx",
            base_url="http://x", model="gpt-4",
        )
        self.assertTrue(cfg.is_effective)

    def test_effective_when_all_filled_enabled_false(self):
        """Core behavior change: enabled=False + fields filled -> still effective."""
        from media_importer.core.config_view import LLMConfig
        cfg = LLMConfig(
            enabled=False, api_key="sk-xxx",
            base_url="http://x", model="gpt-4",
        )
        self.assertTrue(cfg.is_effective)

    def test_not_effective_when_api_key_missing(self):
        from media_importer.core.config_view import LLMConfig
        cfg = LLMConfig(
            enabled=True, api_key="",
            base_url="http://x", model="gpt-4",
        )
        self.assertFalse(cfg.is_effective)

    def test_not_effective_when_base_url_missing(self):
        from media_importer.core.config_view import LLMConfig
        cfg = LLMConfig(
            enabled=True, api_key="sk-xxx",
            base_url="", model="gpt-4",
        )
        self.assertFalse(cfg.is_effective)

    def test_not_effective_when_model_missing(self):
        from media_importer.core.config_view import LLMConfig
        cfg = LLMConfig(
            enabled=True, api_key="sk-xxx",
            base_url="http://x", model="",
        )
        self.assertFalse(cfg.is_effective)

    def test_not_effective_when_all_fields_empty(self):
        from media_importer.core.config_view import LLMConfig
        cfg = LLMConfig()
        self.assertFalse(cfg.is_effective)


if __name__ == "__main__":
    unittest.main()
