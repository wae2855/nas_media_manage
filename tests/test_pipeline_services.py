#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.pipeline.services import (
    ClassificationService,
    DedupService,
    ImportService,
    ReviewDecisionService,
    SourceCleanupService,
)


class FakeConfidenceEngine:
    def __init__(self, level):
        self.level = level

    def get_confidence_level(self, confidence, gate_blocked=None):
        return self.level


class FakeCleanupService:
    def __init__(self):
        self.recycled = []

    def recycle_existing_import(self, path, *, reason, task_id):
        self.recycled.append((path, reason, task_id))
        return True, path + ".recycle", "ok"


class TestClassificationService(unittest.TestCase):
    def test_classifies_scraped_dimensions_to_import_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            movie_dir = os.path.join(tmpdir, "movies")
            config = {
                "path_rules": [
                    {
                        "conditions": {"media_type": "movie"},
                        "template": movie_dir,
                    }
                ]
            }
            task = {
                "scrape_dimensions": {"media_type": "movie"},
                "scrape_result": {
                    "title_cn": "测试电影",
                    "year": "2026",
                    "dimensions": {"media_type": "movie"},
                },
            }

            result = ClassificationService(config).classify_task(task)

            self.assertEqual(result.import_path, movie_dir + "/")
            self.assertEqual(result.classify_result, movie_dir + "/")
            self.assertFalse(result.used_fallback)

    def test_uses_fallback_dir_when_no_rule_matches(self):
        config = {
            "path_rules": [],
            "fallback_dir": "/library/{title_cn}",
        }
        task = {
            "scrape_dimensions": {},
            "scrape_result": {"title_cn": "兜底电影"},
        }

        result = ClassificationService(config).classify_task(task)

        self.assertEqual(result.import_path, "/library/兜底电影/")
        self.assertTrue(result.used_fallback)


class TestDedupService(unittest.TestCase):
    def test_skips_cross_directory_scan_when_disabled(self):
        service = DedupService({"duplicate_handling": {"enabled": False}})

        decision = service.check_task({})

        self.assertEqual(decision.action, "continue")
        self.assertFalse(decision.result["is_duplicate"])
        self.assertIn("跳过跨目录扫描", decision.message)

    def test_rename_strategy_returns_final_filename(self):
        config = {
            "duplicate_handling": {"strategy": "rename"},
            "path_rules": [{"template": "/library/movies"}],
        }
        duplicate = {
            "is_duplicate": True,
            "existing_file": "Movie.mkv",
            "existing_path": "/library/movies/Movie.mkv",
            "suggested_filename": "/library/movies/Movie_copy1.mkv",
        }

        with patch("media_importer.pipeline.services.dedup.os.path.isdir", return_value=True), \
             patch("media_importer.pipeline.services.dedup.check_duplicate", return_value=duplicate):
            decision = DedupService(config).check_task({"scrape_result": {}})

        self.assertEqual(decision.action, "rename")
        self.assertEqual(decision.final_filename, "Movie_copy1.mkv")

    def test_replace_strategy_delegates_recycle_to_cleanup_service(self):
        with tempfile.NamedTemporaryFile() as existing:
            config = {
                "duplicate_handling": {"strategy": "replace"},
                "path_rules": [{"template": os.path.dirname(existing.name)}],
            }
            duplicate = {
                "is_duplicate": True,
                "existing_file": os.path.basename(existing.name),
                "existing_path": existing.name,
            }
            cleanup = FakeCleanupService()

            with patch("media_importer.pipeline.services.dedup.os.path.isdir", return_value=True), \
                 patch("media_importer.pipeline.services.dedup.check_duplicate", return_value=duplicate):
                decision = DedupService(config, cleanup).check_task({"task_id": "t1"})

            self.assertEqual(decision.action, "replace")
            self.assertEqual(cleanup.recycled, [(existing.name, "dedup_replace", "t1")])


class TestImportService(unittest.TestCase):
    def test_moves_temp_video_to_import_path_and_updates_task(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = os.path.join(tmpdir, "temp")
            import_dir = os.path.join(tmpdir, "import")
            os.makedirs(temp_dir)
            os.makedirs(import_dir)
            temp_video = os.path.join(temp_dir, "Movie.mkv")
            with open(temp_video, "w") as f:
                f.write("video")

            config = {
                "source_dir": os.path.join(tmpdir, "source"),
                "temp_dir": temp_dir,
                "path_rules": [{"template": import_dir}],
                "filename_templates": {"movie": "{title_cn}.{year}.{ext}"},
            }
            task = {
                "task_id": "t1",
                "video_path": temp_video,
                "subtitle_files": [],
                "import_path": import_dir,
                "scrape_result": {
                    "title_cn": "测试电影",
                    "year": "2026",
                    "type": "movie",
                },
            }

            result = ImportService(config).import_task(task, "", [])

            self.assertTrue(os.path.exists(result.video_path))
            self.assertEqual(task["import_video_path"], result.video_path)
            self.assertFalse(os.path.exists(temp_video))


class TestReviewDecisionService(unittest.TestCase):
    def test_missing_required_fields_requires_confirm(self):
        decision = ReviewDecisionService().evaluate(
            {"title_cn": "测试电影", "confidence": 0.9},
            FakeConfidenceEngine("SUCCESS"),
        )

        self.assertEqual(decision.action, "confirm")
        self.assertIn("媒体类型", decision.reason)

    def test_low_confidence_fails(self):
        decision = ReviewDecisionService().evaluate(
            {
                "title_cn": "测试电影",
                "title_en": "Test",
                "year": "2026",
                "type": "movie",
                "confidence": 0.1,
                "confidence_search": 0.2,
            },
            FakeConfidenceEngine("FAILED"),
        )

        self.assertEqual(decision.action, "failed")
        self.assertIn("置信度过低", decision.reason)

    def test_gate_blocked_requires_review(self):
        decision = ReviewDecisionService().evaluate(
            {
                "title_cn": "测试电影",
                "title_en": "Test",
                "year": "2026",
                "type": "movie",
                "confidence": 0.9,
                "confidence_gate_blocked": {
                    "dim_name": "media_type",
                    "source": "unknown",
                },
            },
            FakeConfidenceEngine("NEEDS_REVIEW"),
        )

        self.assertEqual(decision.action, "needs_review")
        self.assertIn("来源不信任", decision.reason)


class TestSourceCleanupService(unittest.TestCase):
    def test_source_retention_returns_operator_message(self):
        service = SourceCleanupService({
            "source_dir": "/source",
            "source_policy": {"cleanup_source_after_done": False},
        })

        result = service.cleanup_source_after_import({}, "/source/Movie.mkv", [])

        self.assertIn("源文件保留", result.message)

    def test_skip_recycle_uses_recycle_policy(self):
        config = {
            "source_dir": "/source",
            "temp_dir": "/temp",
            "source_policy": {"recycle_dir": "/recycle"},
            "path_rules": [{"template": "/import"}],
            "video_extensions": [".mkv"],
            "subtitle_extensions": [".srt"],
        }
        service = SourceCleanupService(config)

        with patch("media_importer.pipeline.services.source_cleanup.move_to_recycle_with_companions", return_value=1), \
             patch("media_importer.pipeline.services.source_cleanup.remove_empty_parent_dir"):
            result = service.recycle_source_after_skip(
                {"task_id": "t1"},
                "/source/Movie.mkv",
                [],
            )

        self.assertEqual(result.moved_count, 1)
        self.assertIn("跳过任务源文件", result.message)


if __name__ == "__main__":
    unittest.main()
