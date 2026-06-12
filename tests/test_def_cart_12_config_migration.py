#!/usr/bin/env python3
"""Config migration and hot-update tests.

Tests config hot update, version migration, and validation.
"""
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from media_importer.core.config_migrations import (
    _normalize_bool_strings,
    _migrate_source_policy,
    _migrate_confidence_v1_to_v2,
    BOOL_TRUE_STRINGS,
    BOOL_FALSE_STRINGS,
)
from media_importer.core.config_loader import validate_config, mask_sensitive


class TestConfigHotUpdate(unittest.TestCase):
    """Change path_rules -> new tasks use new rules."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_config_hot_update_path_rules(self):
        from media_importer.features.import_flow.services.classification import ClassificationService

        config_v1 = {
            "base_dir": "/vol1/影视",
            "path_rules": [
                {
                    "conditions": {"media_type": "movie"},
                    "template": "/vol1/影视/电影/{year}/{title_cn} ({year})/",
                },
            ],
            "fallback_dir": "/vol1/影视/other/",
        }

        service = ClassificationService(config_v1)
        task = {
            "task_id": "t1",
            "source_filename": "test.mkv",
            "scrape_result": {
                "title_cn": "测试电影",
                "year": "2024",
                "dimensions": {"media_type": "movie"},
            },
            "scrape_dimensions": {"media_type": "movie"},
        }
        result_v1 = service.preview_classify(task)
        self.assertIn("电影", result_v1["import_path"])

        # Hot update: change path_rules
        config_v2 = {
            "base_dir": "/vol2/media",
            "path_rules": [
                {
                    "conditions": {"media_type": "movie"},
                    "template": "/vol2/media/Movies/{title_en} ({year})/",
                },
            ],
            "fallback_dir": "/vol2/media/other/",
        }

        service_v2 = ClassificationService(config_v2)
        result_v2 = service_v2.preview_classify(task)
        self.assertIn("Movies", result_v2["import_path"])


class TestConfigVersionMigration(unittest.TestCase):
    """Old config format -> auto-migrated."""

    def test_bool_string_normalization(self):
        config = {
            "enabled": "true",
            "verify_ssl": "false",
            "recursive": "yes",
            "other_field": "maybe",
        }
        result = _normalize_bool_strings(config)
        self.assertTrue(result["enabled"])
        self.assertFalse(result["verify_ssl"])
        self.assertTrue(result["recursive"])
        # Non-bool fields should be unchanged
        self.assertEqual(result["other_field"], "maybe")

    def test_source_policy_migration(self):
        config = {
            "source_policy": {
                "delete_source_after_import": True,
                "cleanup_mode": "",
            },
        }
        _migrate_source_policy(config["source_policy"], config)
        # After migration, cleanup_mode should be set
        self.assertIn("cleanup_mode", config["source_policy"])

    def test_confidence_v1_to_v2_migration(self):
        confidence = {
            "aggregation_method": "weighted_avg",
            "dimensions": {
                "media_type": {
                    "weight": 1.0,
                    "veto_threshold": 0.3,
                    "trusted_sources": ["tmdb", "ai"],
                },
            },
        }
        _migrate_confidence_v1_to_v2(confidence)
        # v1 keys should be removed
        self.assertNotIn("aggregation_method", confidence)
        # dimension should have sources, not trusted_sources
        dim = confidence["dimensions"]["media_type"]
        self.assertNotIn("weight", dim)
        self.assertNotIn("trusted_sources", dim)
        self.assertIn("sources", dim)


class TestConfigValidation(unittest.TestCase):
    """Invalid values -> validation error."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_config_validation_missing_llm_key(self):
        config = {
            "llm": {"api_key": "your-api-key-here"},
            "source_dir": self.tmpdir,
            "temp_dir": self.tmpdir,
            "log_dir": self.tmpdir,
            "source_policy": {"recycle_dir": self.tmpdir},
        }
        errors = validate_config(config)
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any("api_key" in e for e in errors))

    def test_config_validation_missing_dirs(self):
        config = {
            "llm": {"api_key": "valid-key"},
            "source_dir": "/nonexistent/path",
            "temp_dir": "/nonexistent/path",
            "log_dir": "/nonexistent/path",
            "source_policy": {"recycle_dir": "/nonexistent/path"},
        }
        errors = validate_config(config)
        self.assertTrue(len(errors) > 0)

    def test_config_validation_valid(self):
        config = {
            "llm": {"api_key": "valid-key"},
            "source_dir": self.tmpdir,
            "temp_dir": self.tmpdir,
            "log_dir": self.tmpdir,
            "source_policy": {"recycle_dir": self.tmpdir},
        }
        errors = validate_config(config)
        self.assertEqual(len(errors), 0)

    def test_mask_sensitive(self):
        config = {
            "server": {"api_key": "my-server-key"},
            "llm": {"api_key": "sk-1234567890abcdef"},
            "hermes": {"webhook": {"secret": "my-secret"}},
            "metadata": {"providers": [{"type": "tmdb", "api_key": "tmdb-key"}]},
        }
        masked = mask_sensitive(config)
        self.assertEqual(masked["server"]["api_key"], "***")
        self.assertIn("***", masked["llm"]["api_key"])
        self.assertEqual(masked["hermes"]["webhook"]["secret"], "***")
        self.assertEqual(masked["metadata"]["providers"][0]["api_key"], "***")


if __name__ == "__main__":
    unittest.main()
