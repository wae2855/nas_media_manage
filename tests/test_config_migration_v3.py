"""配置迁移 v2→v3 测试。"""

import unittest
from media_importer.core.config_migrations import _migrate_confidence_v2_to_v3


class TestConfigMigrationV3(unittest.TestCase):

    def test_removes_confidence_block(self):
        """移除 confidence 区块"""
        config = {
            "confidence": {"R_formula": "log", "pass_threshold": 0.8},
            "metadata": {"scrape_mode": "provider_first"},
        }
        result = _migrate_confidence_v2_to_v3(config)
        self.assertNotIn("confidence", result)
        self.assertEqual(result["metadata"]["scrape_mode"], "provider_first")

    def test_removes_confidence_threshold(self):
        """移除 llm.confidence_threshold"""
        config = {
            "llm": {"confidence_threshold": 0.8, "model": "test"},
            "metadata": {"scrape_mode": "provider_first"},
        }
        result = _migrate_confidence_v2_to_v3(config)
        self.assertNotIn("confidence_threshold", result["llm"])
        self.assertEqual(result["llm"]["model"], "test")

    def test_migrates_ai_only_to_provider_first(self):
        """ai_only → provider_first"""
        config = {"metadata": {"scrape_mode": "ai_only"}}
        result = _migrate_confidence_v2_to_v3(config)
        self.assertEqual(result["metadata"]["scrape_mode"], "provider_first")

    def test_migrates_hybrid_to_provider_first(self):
        """hybrid → provider_first"""
        config = {"metadata": {"scrape_mode": "hybrid"}}
        result = _migrate_confidence_v2_to_v3(config)
        self.assertEqual(result["metadata"]["scrape_mode"], "provider_first")

    def test_preserves_provider_first(self):
        """provider_first 不变"""
        config = {"metadata": {"scrape_mode": "provider_first"}}
        result = _migrate_confidence_v2_to_v3(config)
        self.assertEqual(result["metadata"]["scrape_mode"], "provider_first")

    def test_no_confidence_block_no_error(self):
        """无 confidence 区块不报错"""
        config = {"metadata": {"scrape_mode": "provider_first"}}
        result = _migrate_confidence_v2_to_v3(config)
        self.assertEqual(result["metadata"]["scrape_mode"], "provider_first")

    def test_preserves_manual_review(self):
        """manual_review 不受影响"""
        config = {
            "manual_review": {"enabled": True},
            "metadata": {"scrape_mode": "provider_first"},
        }
        result = _migrate_confidence_v2_to_v3(config)
        self.assertEqual(result["manual_review"]["enabled"], True)

    def test_confidence_removed_before_manual_review(self):
        """同时有 confidence 和 manual_review → confidence 移除，manual_review 保留"""
        config = {
            "confidence": {"R_formula": "inverse"},
            "manual_review": {"enabled": False},
            "metadata": {"scrape_mode": "ai_only"},
        }
        result = _migrate_confidence_v2_to_v3(config)
        self.assertNotIn("confidence", result)
        self.assertEqual(result["manual_review"]["enabled"], False)
        self.assertEqual(result["metadata"]["scrape_mode"], "provider_first")


if __name__ == "__main__":
    unittest.main()