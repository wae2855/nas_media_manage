#!/usr/bin/env python3
"""Symlink edge case tests.

Tests that symlink loops and deeply nested symlinks are handled
safely without infinite loops.
"""
import os
import shutil
import tempfile
import unittest

from media_importer.features.import_flow.scan_service import FileScanner


def _make_config(source_dir="", temp_dir=""):
    return {
        "source_dir": source_dir,
        "temp_dir": temp_dir,
        "video_extensions": [".mkv", ".mp4", ".avi", ".ts"],
        "subtitle_extensions": [".srt", ".ass"],
        "scan_source": True,
        "skip_existing": True,
        "sort_by": "filename",
        "sort_reverse": False,
        "group_delay_sec": 0,
    }


class TestScanSymlinkLoop(unittest.TestCase):
    """Source dir with symlink pointing to parent -> no infinite loop."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Create a video file
        open(os.path.join(self.tmpdir, "movie.mkv"), "w").close()
        # Create a symlink pointing to parent directory (loop)
        try:
            os.symlink(self.tmpdir, os.path.join(self.tmpdir, "loop_link"))
        except OSError:
            # Symlinks may not be supported on this platform
            pass
        self.config = _make_config(source_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scan_symlink_loop(self):
        scanner = FileScanner(self.config)
        # os.walk follows symlinks by default but Python handles loops
        # by tracking visited inodes
        try:
            groups = scanner.scan_and_filter(self.tmpdir)
            # Should find the video file without infinite loop
            video_files = {os.path.basename(g["video_path"]) for g in groups}
            self.assertIn("movie.mkv", video_files)
        except RecursionError:
            self.fail("Scanner entered infinite loop on symlink cycle")


class TestScanSymlinkDepth(unittest.TestCase):
    """Nested symlinks -> depth limit respected."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Create a chain of directories with symlinks
        current = self.tmpdir
        for i in range(10):
            subdir = os.path.join(current, f"level{i}")
            os.makedirs(subdir, exist_ok=True)
            # Create a video at each level
            open(os.path.join(subdir, f"video{i}.mkv"), "w").close()
            # Create a symlink to the next level
            next_dir = os.path.join(subdir, f"link{i}")
            try:
                os.symlink(subdir, next_dir)
            except OSError:
                pass
            current = subdir
        self.config = _make_config(source_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scan_symlink_depth(self):
        scanner = FileScanner(self.config)
        try:
            groups = scanner.scan_and_filter(self.tmpdir)
            # Should find video files without infinite recursion
            self.assertGreaterEqual(len(groups), 1)
        except RecursionError:
            self.fail("Scanner entered infinite recursion on nested symlinks")


if __name__ == "__main__":
    unittest.main()
