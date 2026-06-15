#!/usr/bin/env python3
"""配置校验 validate_config() 的单测。

覆盖 validate_config 的所有关键分支：
- 目录配置（source_dir / temp_dir / recycle_dir / log_dir）
- 目录冲突（源/中转/回收两两不可重复）
- 旧字段弃用 warning（cleanup_mode / delete_source_after_import）
- 新策略字段（cleanup_source_after_done / recycle_retention_days）
- 源目录清理器（enabled / cleanup_mode / merge_strategy / ai_enabled / junk_video_max_size_mb）
- 刮削模式（scrape_mode 合法值 + provider_first 提示）
- AI 辅助 / AI 联网（api_key / base_url / model）
"""

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from media_importer.core.config_validator import validate_config


def _make_config(tmp_path, **overrides):
    """构造一个能在 tmp_path 下通过所有路径校验的最小 config。"""
    source = tmp_path / "source"
    temp = tmp_path / "temp"
    recycle = tmp_path / "recycle"
    log_dir = tmp_path / "logs"
    for p in (source, temp, recycle, log_dir):
        p.mkdir()
    cfg = {
        "source_dir": str(source),
        "temp_dir": str(temp),
        "log_dir": str(log_dir),
        "source_policy": {"recycle_dir": str(recycle)},
        "metadata": {
            "scrape_mode": "provider_first",
            "providers": [{"type": "tmdb", "enabled": True}],
        },
        "ai_assist": {
            "api_key": "real-key",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
        },
        "ai_search": {
            "api_key": "real-key",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
            "enabled": True,
        },
    }
    cfg["source_policy"].update(overrides.pop("source_policy_overrides", {}))
    cfg.update(overrides)
    return cfg


def _by_item(results, item_name):
    for d in results["details"]:
        if d["item"] == item_name:
            return d
    return None


def _status(results, item_name):
    """返回校验项的 status，缺项视为 error。"""
    item = _by_item(results, item_name)
    return item["status"] if item else "error"


class TestValidateConfigDirectories(unittest.TestCase):
    def test_empty_source_dir_is_error(self):
        results = validate_config({"source_dir": "", "temp_dir": "/tmp", "source_policy": {"recycle_dir": "/tmp"}})
        self.assertEqual(_status(results, "source_dir"), "error")
        self.assertEqual(results["overall"], "degraded")

    def test_empty_temp_dir_is_error(self):
        results = validate_config({"source_dir": "/tmp", "temp_dir": "", "source_policy": {"recycle_dir": "/tmp"}})
        self.assertEqual(_status(results, "temp_dir"), "error")

    def test_missing_recycle_dir_is_error(self):
        results = validate_config({"source_dir": "/tmp", "temp_dir": "/tmp", "source_policy": {}})
        self.assertEqual(_status(results, "recycle_dir"), "error")

    def test_recycle_falls_back_to_quarantine_dir(self, tmp_path=None):
        if tmp_path is None:
            import tempfile
            tmp_path = Path(tempfile.mkdtemp())
        q = tmp_path / "q"
        q.mkdir()
        cfg = {
            "source_dir": str(tmp_path / "src"),
            "temp_dir": str(tmp_path / "tmp"),
            "source_policy": {"quarantine_dir": str(q)},
        }
        (tmp_path / "src").mkdir()
        (tmp_path / "tmp").mkdir()
        results = validate_config(cfg)
        self.assertEqual(_status(results, "recycle_dir"), "ok")

    def test_nonexistent_dir_is_error(self):
        results = validate_config(
            {"source_dir": "/this/path/does/not/exist", "temp_dir": "/tmp", "source_policy": {"recycle_dir": "/tmp"}}
        )
        self.assertEqual(_status(results, "source_dir"), "error")

    def test_empty_log_dir_is_warning(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = _make_config(tmp_path)
        cfg["log_dir"] = ""
        results = validate_config(cfg)
        self.assertEqual(_status(results, "log_dir"), "warning")
        self.assertEqual(results["overall"], "ok")


class TestValidateConfigDirConflicts(unittest.TestCase):
    def test_source_equals_temp_is_error(self, tmp_path=None):
        if tmp_path is None:
            import tempfile
            tmp_path = Path(tempfile.mkdtemp())
        same = tmp_path / "same"
        same.mkdir()
        results = validate_config(
            {"source_dir": str(same), "temp_dir": str(same), "source_policy": {"recycle_dir": str(tmp_path / "r")}}
        )
        (tmp_path / "r").mkdir()
        results = validate_config(
            {"source_dir": str(same), "temp_dir": str(same), "source_policy": {"recycle_dir": str(tmp_path / "r")}}
        )
        conflict = _by_item(results, "dir_conflict")
        self.assertIsNotNone(conflict)
        self.assertEqual(conflict["status"], "error")

    def test_source_equals_recycle_is_error(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        same = tmp_path / "same"
        same.mkdir()
        results = validate_config(
            {"source_dir": str(same), "temp_dir": str(tmp_path / "t"), "source_policy": {"recycle_dir": str(same)}}
        )
        conflict = _by_item(results, "dir_conflict")
        self.assertEqual(conflict["status"], "error")

    def test_temp_equals_recycle_is_error(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        same = tmp_path / "same"
        same.mkdir()
        results = validate_config(
            {"source_dir": str(tmp_path / "s"), "temp_dir": str(same), "source_policy": {"recycle_dir": str(same)}}
        )
        conflict = _by_item(results, "dir_conflict")
        self.assertEqual(conflict["status"], "error")


class TestValidateConfigLegacyFields(unittest.TestCase):
    def test_legacy_cleanup_mode_emits_warning(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = _make_config(tmp_path, source_policy_overrides={"cleanup_mode": "media_only"})
        results = validate_config(cfg)
        self.assertEqual(_status(results, "source_policy.cleanup_mode"), "warning")

    def test_legacy_delete_source_after_import_emits_warning(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = _make_config(tmp_path, source_policy_overrides={"delete_source_after_import": True})
        results = validate_config(cfg)
        self.assertEqual(_status(results, "source_policy.delete_source_after_import"), "warning")


class TestValidateConfigNewSourcePolicy(unittest.TestCase):
    def test_cleanup_source_after_done_true_is_ok(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = _make_config(tmp_path, source_policy_overrides={"cleanup_source_after_done": True})
        results = validate_config(cfg)
        self.assertEqual(_status(results, "source_policy.cleanup_source_after_done"), "ok")

    def test_cleanup_source_after_done_false_is_ok(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = _make_config(tmp_path, source_policy_overrides={"cleanup_source_after_done": False})
        results = validate_config(cfg)
        self.assertEqual(_status(results, "source_policy.cleanup_source_after_done"), "ok")

    def test_cleanup_source_after_done_wrong_type_is_error(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = _make_config(tmp_path, source_policy_overrides={"cleanup_source_after_done": "yes"})
        results = validate_config(cfg)
        self.assertEqual(_status(results, "source_policy.cleanup_source_after_done"), "error")

    def test_recycle_retention_days_negative_is_error(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = _make_config(tmp_path, source_policy_overrides={"recycle_retention_days": -1})
        results = validate_config(cfg)
        self.assertEqual(_status(results, "source_policy.recycle_retention_days"), "error")

    def test_recycle_retention_days_string_is_error(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = _make_config(tmp_path, source_policy_overrides={"recycle_retention_days": "30"})
        results = validate_config(cfg)
        self.assertEqual(_status(results, "source_policy.recycle_retention_days"), "error")

    def test_recycle_retention_days_valid_is_ok(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = _make_config(tmp_path, source_policy_overrides={"recycle_retention_days": 30})
        results = validate_config(cfg)
        self.assertEqual(_status(results, "source_policy.recycle_retention_days"), "ok")


class TestValidateConfigSourceCleaner(unittest.TestCase):
    def test_source_cleaner_enabled_true(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = _make_config(tmp_path, source_cleaner={"enabled": True, "cleanup_mode": "media_only", "merge_strategy": "intersection"})
        results = validate_config(cfg)
        self.assertEqual(_status(results, "source_cleaner.enabled"), "ok")
        self.assertEqual(_status(results, "source_cleaner.cleanup_mode"), "ok")
        self.assertEqual(_status(results, "source_cleaner.merge_strategy"), "ok")

    def test_source_cleaner_invalid_cleanup_mode_is_error(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = _make_config(tmp_path, source_cleaner={"enabled": True, "cleanup_mode": "all"})
        results = validate_config(cfg)
        self.assertEqual(_status(results, "source_cleaner.cleanup_mode"), "error")

    def test_source_cleaner_invalid_merge_strategy_is_error(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = _make_config(tmp_path, source_cleaner={"enabled": True, "merge_strategy": "all"})
        results = validate_config(cfg)
        self.assertEqual(_status(results, "source_cleaner.merge_strategy"), "error")

    def test_source_cleaner_ai_enabled_wrong_type(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = _make_config(tmp_path, source_cleaner={"ai_enabled": "yes"})
        results = validate_config(cfg)
        self.assertEqual(_status(results, "source_cleaner.ai_enabled"), "error")

    def test_source_cleaner_junk_size_negative_is_error(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = _make_config(tmp_path, source_cleaner={"junk_video_max_size_mb": -10})
        results = validate_config(cfg)
        self.assertEqual(_status(results, "source_cleaner.junk_video_max_size_mb"), "error")

    def test_source_cleaner_junk_size_valid_is_ok(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = _make_config(tmp_path, source_cleaner={"junk_video_max_size_mb": 50})
        results = validate_config(cfg)
        self.assertEqual(_status(results, "source_cleaner.junk_video_max_size_mb"), "ok")


class TestValidateConfigScrapeMode(unittest.TestCase):
    def test_provider_first_with_tmdb_enabled_is_ok(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = _make_config(tmp_path)
        cfg["metadata"] = {"scrape_mode": "provider_first", "providers": [{"type": "tmdb", "enabled": True}]}
        results = validate_config(cfg)
        self.assertEqual(_status(results, "metadata.scrape_mode"), "ok")

    def test_provider_first_no_provider_is_warning(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = _make_config(tmp_path)
        cfg["metadata"] = {"scrape_mode": "provider_first", "providers": [{"type": "tmdb", "enabled": False}]}
        results = validate_config(cfg)
        scrape_mode_item = _by_item(results, "metadata.scrape_mode_provider")
        self.assertEqual(scrape_mode_item["status"], "warning")

    def test_invalid_scrape_mode_is_error(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = _make_config(tmp_path)
        cfg["metadata"] = {"scrape_mode": "random", "providers": []}
        results = validate_config(cfg)
        self.assertEqual(_status(results, "metadata.scrape_mode"), "error")


class TestValidateConfigAIAssist(unittest.TestCase):
    def _base_cfg(self, tmp_path):
        return _make_config(tmp_path)

    def test_ai_assist_missing_api_key_is_error(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = self._base_cfg(tmp_path)
        cfg["ai_assist"] = {"api_key": "", "base_url": "https://x", "model": "gpt"}
        results = validate_config(cfg)
        self.assertEqual(_status(results, "ai_assist.api_key"), "error")

    def test_ai_assist_masked_api_key_is_warning(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = self._base_cfg(tmp_path)
        cfg["ai_assist"] = {"api_key": "***", "base_url": "https://x", "model": "gpt"}
        results = validate_config(cfg)
        self.assertEqual(_status(results, "ai_assist.api_key"), "warning")

    def test_ai_assist_invalid_base_url_is_error(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = self._base_cfg(tmp_path)
        cfg["ai_assist"] = {"api_key": "k", "base_url": "ftp://x", "model": "gpt"}
        results = validate_config(cfg)
        self.assertEqual(_status(results, "ai_assist.base_url"), "error")

    def test_ai_search_enabled_without_model_is_error(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = self._base_cfg(tmp_path)
        cfg["ai_search"] = {"api_key": "k", "base_url": "https://x", "model": "", "enabled": True}
        results = validate_config(cfg)
        self.assertEqual(_status(results, "ai_search.model"), "error")

    def test_ai_search_valid_is_ok(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = self._base_cfg(tmp_path)
        cfg["ai_search"] = {"api_key": "k", "base_url": "https://x", "model": "gpt-4o", "enabled": True}
        results = validate_config(cfg)
        self.assertEqual(_status(results, "ai_search.api_key"), "ok")
        self.assertEqual(_status(results, "ai_search.model"), "ok")


class TestValidateConfigOverall(unittest.TestCase):
    def test_all_ok_overall_is_ok(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = _make_config(tmp_path)
        results = validate_config(cfg)
        self.assertEqual(results["overall"], "ok")
        self.assertIn("timestamp", results)
        self.assertIsInstance(results["details"], list)

    def test_any_error_makes_overall_degraded(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        cfg = _make_config(tmp_path, source_policy_overrides={"recycle_retention_days": -1})
        results = validate_config(cfg)
        self.assertEqual(results["overall"], "degraded")
