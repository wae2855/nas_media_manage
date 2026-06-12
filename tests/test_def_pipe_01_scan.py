#!/usr/bin/env python3
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

from media_importer.features.import_flow.scan_service import FileScanner
from tests.test_def_filename_patterns import FILENAME_TEST_CASES


def _make_config(source_dir="", temp_dir=""):
    return {
        "source_dir": source_dir,
        "temp_dir": temp_dir,
        "video_extensions": [".mkv", ".mp4", ".avi", ".ts", ".mov", ".wmv", ".m2ts", ".flv", ".rmvb"],
        "subtitle_extensions": [".srt", ".ass", ".ssa", ".sub"],
        "scan_source": True,
        "skip_existing": True,
        "sort_by": "filename",
        "sort_reverse": False,
        "group_delay_sec": 0,
    }


class TestFileScannerScanEmptyDir(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _make_config(source_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scan_empty_dir(self):
        scanner = FileScanner(self.config)
        groups = scanner.scan_and_filter(self.tmpdir)
        self.assertEqual(len(groups), 0)


class TestFileScannerMixedFiles(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _make_config(source_dir=self.tmpdir)
        # Create video, subtitle, and junk files
        open(os.path.join(self.tmpdir, "movie.mkv"), "w").close()
        open(os.path.join(self.tmpdir, "movie.srt"), "w").close()
        open(os.path.join(self.tmpdir, "readme.txt"), "w").close()
        open(os.path.join(self.tmpdir, "image.jpg"), "w").close()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scan_mixed_files(self):
        scanner = FileScanner(self.config)
        groups = scanner.scan_and_filter(self.tmpdir)
        # Only video groups should appear; junk files are ignored
        self.assertEqual(len(groups), 1)
        self.assertTrue(groups[0]["video_path"].endswith(".mkv"))
        self.assertEqual(len(groups[0]["subtitle_files"]), 1)
        self.assertTrue(groups[0]["subtitle_files"][0].endswith(".srt"))


class TestFileScannerRecursive(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _make_config(source_dir=self.tmpdir)
        # Create nested dirs with video files
        sub1 = os.path.join(self.tmpdir, "Season1")
        sub2 = os.path.join(self.tmpdir, "Season2")
        os.makedirs(sub1)
        os.makedirs(sub2)
        open(os.path.join(sub1, "ep01.mkv"), "w").close()
        open(os.path.join(sub2, "ep02.mkv"), "w").close()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scan_recursive(self):
        scanner = FileScanner(self.config)
        groups = scanner.scan_and_filter(self.tmpdir)
        self.assertEqual(len(groups), 2)
        video_files = {os.path.basename(g["video_path"]) for g in groups}
        self.assertIn("ep01.mkv", video_files)
        self.assertIn("ep02.mkv", video_files)


class TestFileScannerVideoWithSubtitle(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _make_config(source_dir=self.tmpdir)
        # Create video + same-base-name subtitle
        open(os.path.join(self.tmpdir, "Show.S01E01.mkv"), "w").close()
        open(os.path.join(self.tmpdir, "Show.S01E01.srt"), "w").close()
        # Create unrelated subtitle
        open(os.path.join(self.tmpdir, "Other.ass"), "w").close()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scan_video_with_subtitle(self):
        scanner = FileScanner(self.config)
        groups = scanner.scan_and_filter(self.tmpdir)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["subtitle_files"]), 1)
        self.assertTrue(groups[0]["subtitle_files"][0].endswith(".srt"))


class TestFileScannerDedup(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _make_config(source_dir=self.tmpdir)
        open(os.path.join(self.tmpdir, "movie.mkv"), "w").close()
        self.task_manager = MagicMock()
        self.task_manager.check_source_duplicate.return_value = {
            "action": "SKIP",
            "task_id": "existing-1",
        }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scan_dedup(self):
        scanner = FileScanner(self.config, task_manager=self.task_manager)
        groups = scanner.scan_and_filter(self.tmpdir)
        # SKIP action should filter out the file
        self.assertEqual(len(groups), 0)
        self.task_manager.check_source_duplicate.assert_called()


class TestFileScannerAllFilenamePatterns(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _make_config(source_dir=self.tmpdir)
        # Create files from FILENAME_TEST_CASES
        for tc in FILENAME_TEST_CASES:
            filepath = os.path.join(self.tmpdir, tc["filename"])
            parent = os.path.dirname(filepath)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
            with open(filepath, "w") as f:
                f.write("dummy")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scan_all_filename_patterns(self):
        scanner = FileScanner(self.config)
        groups = scanner.scan_and_filter(self.tmpdir)
        # All video files should be found (subtitle and junk categories may not be videos)
        video_exts = self.config["video_extensions"]
        expected_videos = [
            tc["filename"] for tc in FILENAME_TEST_CASES
            if any(tc["filename"].lower().endswith(ext) for ext in video_exts)
        ]
        found_videos = {os.path.basename(g["video_path"]) for g in groups}
        for vf in expected_videos:
            self.assertIn(vf, found_videos, f"Expected video file not found: {vf}")


if __name__ == "__main__":
    unittest.main()
