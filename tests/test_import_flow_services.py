#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.features.import_flow.services import (
    ClassificationService,
    DedupService,
    ImportService,
    ReviewDecisionService,
    SourceCleanupService,
)


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

    def test_reports_rules_when_no_rule_and_no_fallback_matches(self):
        config = {
            "path_rules": [
                {
                    "conditions": {"media_type": "tv"},
                    "template": "/library/tv",
                }
            ]
        }
        task = {
            "scrape_dimensions": {"media_type": "movie"},
            "scrape_result": {
                "title_cn": "无匹配电影",
                "dimensions": {"media_type": "movie"},
            },
        }

        result = ClassificationService(config).classify_task(task)

        self.assertEqual(result.import_path, "")
        self.assertEqual(result.classify_result, "")
        self.assertEqual(result.dimensions_text, "media_type=movie")
        self.assertIn("规则1", result.rules_description)


class TestDedupService(unittest.TestCase):
    def test_no_target_directory_returns_clear_when_semantic_scan_disabled(self):
        service = DedupService({"duplicate_handling": {"enabled": False}})

        decision = service.check_task({})

        self.assertEqual(decision.action, "continue")
        self.assertFalse(decision.result["is_duplicate"])

    def test_legacy_replace_strategy_only_returns_review_and_does_not_recycle(self):
        with tempfile.TemporaryDirectory() as root:
            existing_path = os.path.join(root, "Movie.2026.mkv")
            new_path = os.path.join(root, "new.mkv")
            with open(existing_path, "wb") as handle:
                handle.write(b"existing")
            with open(new_path, "wb") as handle:
                handle.write(b"new")
            config = {
                "duplicate_handling": {"strategy": "replace"},
                "path_rules": [{"template": root}],
            }
            duplicate = {
                "is_duplicate": True,
                "existing_file": os.path.basename(existing_path),
                "existing_path": existing_path,
            }
            cleanup = FakeCleanupService()

            with patch(
                "media_importer.features.import_flow.services.dedup.check_duplicate",
                return_value=duplicate,
            ):
                decision = DedupService(config, cleanup).check_task({
                    "task_id": "t1",
                    "import_path": root,
                    "video_path": new_path,
                    "final_filename": "Different.mkv",
                    "scrape_result": {},
                })

            self.assertEqual(decision.action, "review")
            self.assertEqual(decision.result["status"], "awaiting_user")
            self.assertEqual(cleanup.recycled, [])
            self.assertTrue(os.path.exists(existing_path))


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
                    "media_type": "movie",
                },
                "final_filename": "测试电影.2026.mkv",
            }

            result = ImportService(config).import_task(task, "", [])

            self.assertTrue(os.path.exists(result.video_path))
            self.assertEqual(task["import_video_path"], result.video_path)
            self.assertFalse(os.path.exists(temp_video))

    def test_restore_confirm_temp_name_only_when_manual_review_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_video = os.path.join(tmpdir, "Movie.mkv.tmp")
            with open(temp_video, "w") as f:
                f.write("video")
            task = {"video_path": temp_video}

            ImportService({"manual_review": {"enabled": True}}).restore_confirm_temp_name(task)

            restored = os.path.join(tmpdir, "Movie.mkv")
            self.assertEqual(task["video_path"], restored)
            self.assertTrue(os.path.exists(restored))
            self.assertFalse(os.path.exists(temp_video))


class TestReviewDecisionService(unittest.TestCase):
    def test_missing_required_fields_requires_confirm(self):
        decision = ReviewDecisionService().evaluate(
            {"title_cn": "测试电影"},
        )

        self.assertEqual(decision.action, "confirm")
        codes = [c.get("code", "") for c in decision.concerns]
        self.assertIn("MISSING_FIELDS", codes)

    def test_incomplete_mock_data_fails(self):
        decision = ReviewDecisionService().evaluate(
            {
                "title_cn": "测试电影",
                "title_en": "Test",
                "year": "2026",
                "media_type": "movie",
                "match_level": "NEEDS_CONFIRM",
                "match_concerns": [{"code": "NO_YEAR_MULTI_MATCH", "message": "找到多部同名作品"}],
            },
        )

        self.assertEqual(decision.action, "confirm")
        messages = [c.get("message", "") for c in decision.concerns]
        self.assertTrue(any("多部同名作品" in m for m in messages), f"concerns: {decision.concerns}")

    def test_gate_blocked_requires_review(self):
        decision = ReviewDecisionService().evaluate(
            {
                "title_cn": "测试电影",
                "title_en": "Test",
                "year": "2026",
                "media_type": "movie",
                "match_level": "NEEDS_CONFIRM",
                "match_concerns": [{"code": "FUZZY_TITLE", "message": "标题不完全匹配"}],
            },
        )

        self.assertEqual(decision.action, "confirm")
        messages = [c.get("message", "") for c in decision.concerns]
        self.assertIn("标题不完全匹配", messages)

    def test_valid_result_with_optional_warnings_can_continue(self):
        decision = ReviewDecisionService().evaluate(
            {
                "title_cn": "测试电影",
                "media_type": "movie",
                "match_level": "AUTO_PASS",
            },
        )

        self.assertEqual(decision.action, "continue")
        self.assertIn("年份缺失", decision.warnings[0])


class TestSourceCleanupService(unittest.TestCase):
    def test_source_retention_returns_operator_message(self):
        service = SourceCleanupService({
            "source_dir": "/source",
            "source_policy": {"cleanup_source_after_done": False},
        })

        result = service.cleanup_source_after_import({}, "/source/Movie.mkv", [])

        self.assertIn("源文件保留", result.message)

    def test_skip_legacy_recycle_policy_keeps_failed_source_unit(self):
        config = {
            "source_dir": "/source",
            "temp_dir": "/temp",
            "source_policy": {
                "recycle_dir": "/recycle",
                "cleanup_source_after_done": True,
            },
            "path_rules": [{"template": "/import"}],
            "video_extensions": [".mkv"],
            "subtitle_extensions": [".srt"],
        }
        service = SourceCleanupService(config)

        result = service.recycle_source_after_skip(
            {"task_id": "t1"},
            "/source/Movie.mkv",
            [],
        )

        self.assertEqual(result.moved_count, 0)
        self.assertIn("未全部成功", result.message)

    def test_temp_cleanup_only_deletes_files_inside_temp_dir(self):
        service = SourceCleanupService({
            "source_dir": "/source",
            "temp_dir": "/temp",
            "path_rules": [{"template": "/import"}],
        })

        with patch("media_importer.features.source_files.cleanup_service.delete_source_files") as delete_files:
            outside = service.cleanup_temp_file("/outside/Movie.mkv")
            inside = service.cleanup_temp_file("/temp/Movie.mkv")

        self.assertEqual(outside.deleted_count, 0)
        self.assertEqual(inside.deleted_count, 1)
        delete_files.assert_called_once_with(
            ["/temp/Movie.mkv"],
            allowed_base_dirs=["/temp"],
        )


if __name__ == "__main__":
    unittest.main()
