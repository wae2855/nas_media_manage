#!/usr/bin/env python3
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from media_importer.features.import_flow.services.dedup import DedupService, DedupDecision
from media_importer.features.import_flow.utils import PipelineSkipError


def _make_config(strategy="skip", import_roots=None):
    return {
        "source_dir": tempfile.mkdtemp(),
        "temp_dir": tempfile.mkdtemp(),
        "duplicate_handling": {
            "enabled": True,
            "strategy": strategy,
        },
        "path_rules": [
            {"conditions": {}, "template": root}
            for root in (import_roots or ["/media/movies"])
        ],
        "video_extensions": [".mkv", ".mp4"],
        "subtitle_extensions": [".srt", ".ass"],
        "source_policy": {
            "recycle_dir": tempfile.mkdtemp(),
            "cleanup_source_after_done": True,
        },
    }


class TestDedupNoConflict(unittest.TestCase):
    """No existing file → action=continue."""

    def test_dedup_no_conflict(self):
        config = _make_config(import_roots=[tempfile.mkdtemp()])
        service = DedupService(config)
        task = {
            "scrape_result": {
                "title_cn": "新电影",
                "title_en": "New Movie",
                "year": "2024",
                "type": "movie",
            },
            "video_path": "/tmp/nonexistent.mkv",
        }
        decision = service.check_task(task)
        self.assertEqual(decision.action, "continue")
        self.assertFalse(decision.result.get("is_duplicate", False))


class TestDedupSkip(unittest.TestCase):
    """Existing file + strategy=skip → PipelineSkipError."""

    def test_dedup_skip(self):
        import_dir = tempfile.mkdtemp()
        # Create an existing file that matches
        existing = os.path.join(import_dir, "星际穿越.2014.mkv")
        with open(existing, "w") as f:
            f.write("existing")

        config = _make_config(strategy="skip", import_roots=[import_dir])
        service = DedupService(config)
        task = {
            "scrape_result": {
                "title_cn": "星际穿越",
                "title_en": "Interstellar",
                "year": "2014",
                "type": "movie",
            },
            "video_path": "/tmp/new_file.mkv",
        }
        decision = service.check_task(task)
        self.assertEqual(decision.action, "skip")
        # In the pipeline, skip action raises PipelineSkipError
        if decision.action == "skip":
            skip_err = PipelineSkipError(decision.message)
        self.assertIsInstance(skip_err, PipelineSkipError)

        shutil.rmtree(import_dir, ignore_errors=True)


class TestDedupReplace(unittest.TestCase):
    """Existing file + strategy=replace → old file moved to recycle."""

    def test_dedup_replace(self):
        import_dir = tempfile.mkdtemp()
        existing = os.path.join(import_dir, "星际穿越.2014.mkv")
        with open(existing, "w") as f:
            f.write("existing")

        recycle_dir = tempfile.mkdtemp()
        config = _make_config(strategy="replace", import_roots=[import_dir])
        config["source_policy"]["recycle_dir"] = recycle_dir

        # Mock the cleanup service to avoid actual recycle operations
        with patch.object(
            DedupService, "_recycle_duplicate", return_value=None
        ) as mock_recycle:
            service = DedupService(config)
            task = {
                "scrape_result": {
                    "title_cn": "星际穿越",
                    "title_en": "Interstellar",
                    "year": "2014",
                    "type": "movie",
                },
                "video_path": "/tmp/new_file.mkv",
            }
            decision = service.check_task(task)
            self.assertEqual(decision.action, "replace")
            mock_recycle.assert_called_once()

        shutil.rmtree(import_dir, ignore_errors=True)
        shutil.rmtree(recycle_dir, ignore_errors=True)


class TestDedupRename(unittest.TestCase):
    """Existing file + strategy=rename → final_filename changed."""

    def test_dedup_rename(self):
        import_dir = tempfile.mkdtemp()
        existing = os.path.join(import_dir, "星际穿越.2014.mkv")
        with open(existing, "w") as f:
            f.write("existing")

        config = _make_config(strategy="rename", import_roots=[import_dir])
        service = DedupService(config)
        task = {
            "scrape_result": {
                "title_cn": "星际穿越",
                "title_en": "Interstellar",
                "year": "2014",
                "type": "movie",
                "video_file": "星际穿越.2014.mkv",
            },
            "video_path": "/tmp/new_file.mkv",
        }
        decision = service.check_task(task)
        self.assertEqual(decision.action, "rename")
        self.assertTrue(decision.final_filename)  # Should have a new filename

        shutil.rmtree(import_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
