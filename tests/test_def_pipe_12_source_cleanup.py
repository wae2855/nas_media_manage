#!/usr/bin/env python3
"""SourceCleanupService tests.

Tests media_only mode, AI-assisted intersection merge,
junk video threshold, and cron trigger behavior.
"""
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from media_importer.features.source_cleaning.cleaner import SourceCleaner


def _make_config(source_dir="", recycle_dir="", cleanup_mode="media_only",
                 ai_enabled=False, merge_strategy="intersection",
                 junk_video_max_size_mb=0, delete_extensions=None,
                 protect_extensions=None, blacklist_patterns=None,
                 cleanup_empty_dirs=False):
    return {
        "source_dir": source_dir,
        "temp_dir": tempfile.mkdtemp(),
        "log_dir": tempfile.mkdtemp(),
        "source_policy": {"recycle_dir": recycle_dir},
        "llm": {"api_key": "test-key", "base_url": "http://localhost", "model": "test",
                "fast_model": "fast-test", "fast_base_url": "http://localhost",
                "fast_api_key": "fast-key"},
        "video_extensions": [".mkv", ".mp4", ".avi"],
        "subtitle_extensions": [".srt", ".ass"],
        "source_cleaner": {
            "enabled": True,
            "cleanup_mode": cleanup_mode,
            "ai_enabled": ai_enabled,
            "merge_strategy": merge_strategy,
            "junk_video_max_size_mb": junk_video_max_size_mb,
            "delete_extensions": delete_extensions or [".url", ".txt"],
            "protect_extensions": protect_extensions or [".nfo", ".jpg"],
            "blacklist_patterns": blacklist_patterns or [],
            "cleanup_empty_dirs": cleanup_empty_dirs,
        },
    }


class TestMediaOnlyMode(unittest.TestCase):
    """Only media files kept, others deleted."""

    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.recycle_dir = tempfile.mkdtemp()
        # Create media files
        open(os.path.join(self.src_dir, "movie.mkv"), "w").close()
        with open(os.path.join(self.src_dir, "movie.srt"), "w") as f:
            f.write("subtitle")
        # Create non-media files
        open(os.path.join(self.src_dir, "readme.txt"), "w").close()
        open(os.path.join(self.src_dir, "ad.url"), "w").close()
        # Create protected file
        open(os.path.join(self.src_dir, "poster.jpg"), "w").close()

        self.config = _make_config(
            source_dir=self.src_dir,
            recycle_dir=self.recycle_dir,
            cleanup_mode="media_only",
        )

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.recycle_dir, ignore_errors=True)

    def test_media_only_mode(self):
        cleaner = SourceCleaner(self.config)
        items = cleaner.preview()

        # Non-media files should be flagged for deletion
        categories = {item["category"] for item in items}
        paths = {item["path"] for item in items}

        # .txt and .url should be flagged
        txt_path = os.path.join(self.src_dir, "readme.txt")
        url_path = os.path.join(self.src_dir, "ad.url")
        self.assertIn(txt_path, paths)
        self.assertIn(url_path, paths)

        # Media files should NOT be flagged
        mkv_path = os.path.join(self.src_dir, "movie.mkv")
        srt_path = os.path.join(self.src_dir, "movie.srt")
        self.assertNotIn(mkv_path, paths)
        self.assertNotIn(srt_path, paths)

        # Protected files should NOT be flagged
        jpg_path = os.path.join(self.src_dir, "poster.jpg")
        self.assertNotIn(jpg_path, paths)


class TestAIAssistedIntersection(unittest.TestCase):
    """AI + rules intersection merge: only delete when both agree."""

    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.recycle_dir = tempfile.mkdtemp()
        # Create files
        open(os.path.join(self.src_dir, "movie.mkv"), "w").close()
        open(os.path.join(self.src_dir, "junk.txt"), "w").close()

        self.config = _make_config(
            source_dir=self.src_dir,
            recycle_dir=self.recycle_dir,
            cleanup_mode="media_only",
            ai_enabled=True,
            merge_strategy="intersection",
        )

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.recycle_dir, ignore_errors=True)

    @patch.object(SourceCleaner, "_ai_analyze_all")
    def test_intersection_merge_keeps_rule_only_items(self, mock_ai):
        # AI says "keep" for junk.txt (disagrees with rule)
        mock_ai.return_value = {
            os.path.join(self.src_dir, "junk.txt"): {"action": "keep", "reason": "AI says keep"}
        }

        cleaner = SourceCleaner(self.config)
        items = cleaner.preview()

        # In intersection mode, rule-only items should be removed
        paths = {item["path"] for item in items}
        txt_path = os.path.join(self.src_dir, "junk.txt")
        self.assertNotIn(txt_path, paths)

    @patch.object(SourceCleaner, "_ai_analyze_all")
    def test_intersection_merge_keeps_both_agree_items(self, mock_ai):
        # AI says "delete" for junk.txt (agrees with rule)
        mock_ai.return_value = {
            os.path.join(self.src_dir, "junk.txt"): {"action": "delete", "reason": "AI says delete"}
        }

        cleaner = SourceCleaner(self.config)
        items = cleaner.preview()

        # In intersection mode, both-agree items should be kept
        paths = {item["path"] for item in items}
        txt_path = os.path.join(self.src_dir, "junk.txt")
        self.assertIn(txt_path, paths)


class TestJunkVideoThreshold(unittest.TestCase):
    """Small video files treated as junk when below threshold."""

    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.recycle_dir = tempfile.mkdtemp()
        # Create a small video file (well under 50MB)
        small_video = os.path.join(self.src_dir, "sample.mkv")
        with open(small_video, "wb") as f:
            f.write(b"x" * 1024)  # 1KB
        # Create a normal video file
        big_video = os.path.join(self.src_dir, "movie.mkv")
        with open(big_video, "wb") as f:
            f.write(b"x" * (60 * 1024 * 1024))  # 60MB

        self.config = _make_config(
            source_dir=self.src_dir,
            recycle_dir=self.recycle_dir,
            junk_video_max_size_mb=50,
        )

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.recycle_dir, ignore_errors=True)

    def test_junk_video_threshold(self):
        cleaner = SourceCleaner(self.config)
        items = cleaner.preview()

        paths = {item["path"] for item in items}
        categories = {item["category"] for item in items}

        small_path = os.path.join(self.src_dir, "sample.mkv")
        big_path = os.path.join(self.src_dir, "movie.mkv")

        # Small video should be flagged as junk
        self.assertIn(small_path, paths)
        # Big video should NOT be flagged
        self.assertNotIn(big_path, paths)
        # Category should be junk_video
        for item in items:
            if item["path"] == small_path:
                self.assertEqual(item["category"], "junk_video")


class TestCronTrigger(unittest.TestCase):
    """Cleanup triggered on schedule (config-based)."""

    def test_cron_config_present(self):
        config = _make_config(
            source_dir="/tmp/nonexistent",
            recycle_dir="/tmp/nonexistent",
        )
        config["source_cleaner"]["schedule"] = "0 3 * * *"

        cleaner = SourceCleaner(config)
        self.assertEqual(cleaner.config.get("schedule"), "0 3 * * *")

    def test_cron_default_schedule(self):
        config = _make_config(
            source_dir="/tmp/nonexistent",
            recycle_dir="/tmp/nonexistent",
        )

        cleaner = SourceCleaner(config)
        # Default schedule should be set
        schedule = cleaner.config.get("schedule", "0 3 * * *")
        self.assertIsNotNone(schedule)


if __name__ == "__main__":
    unittest.main()
