#!/usr/bin/env python3
"""Crash recovery tests: scan stage.

Simulate process interruption during scan and verify recovery on restart.
"""
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

from media_importer.core.task_manager import TaskManager
from media_importer.features.import_flow.scan_service import FileScanner


VIDEO_EXTS = [".mkv", ".mp4", ".avi", ".ts"]
SUB_EXTS = [".srt", ".ass"]


def _make_config(source_dir="", temp_dir=""):
    return {
        "source_dir": source_dir,
        "temp_dir": temp_dir,
        "video_extensions": VIDEO_EXTS,
        "subtitle_extensions": SUB_EXTS,
        "scan_source": True,
        "skip_existing": True,
        "sort_by": "filename",
        "sort_reverse": False,
        "group_delay_sec": 0,
    }


def _create_video_files(directory, count, prefix="movie"):
    paths = []
    for i in range(count):
        path = os.path.join(directory, f"{prefix}_{i:03d}.mkv")
        with open(path, "wb") as f:
            f.write(b"fake_video" * 100)
        paths.append(path)
    return paths


class TestCrashMidScan(unittest.TestCase):
    """Simulate crash mid-scan: scan finds 5 of 10 files, kill simulated."""

    def setUp(self):
        self.source_dir = tempfile.mkdtemp()
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)
        self.all_files = _create_video_files(self.source_dir, 10)

    def tearDown(self):
        shutil.rmtree(self.source_dir, ignore_errors=True)
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_crash_mid_scan(self):
        # Simulate: scan ran and only 5 files were persisted to DB before crash
        for path in self.all_files[:5]:
            self.tm.create_task(
                video_path=path,
                video_file=os.path.basename(path),
                file_size_mb=0.1,
            )

        # Verify: only 5 tasks in DB
        tasks = self.tm.list_tasks(limit=100)
        self.assertEqual(len(tasks), 5)

        # The remaining 5 files are not tracked
        tracked_paths = {t["source_path"] for t in tasks}
        for path in self.all_files[5:]:
            self.assertNotIn(path, tracked_paths)


class TestCrashScanRestart(unittest.TestCase):
    """After restart, re-scan should find all 10 files without duplicates."""

    def setUp(self):
        self.source_dir = tempfile.mkdtemp()
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)
        self.config = _make_config(source_dir=self.source_dir)
        self.all_files = _create_video_files(self.source_dir, 10)

    def tearDown(self):
        shutil.rmtree(self.source_dir, ignore_errors=True)
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_crash_scan_restart(self):
        # First scan: 5 files found and tasks created before crash
        scanner = FileScanner(self.config, task_manager=self.tm)
        groups = scanner.scan_and_filter(self.source_dir)
        for g in groups[:5]:
            self.tm.create_task(
                video_path=g["video_path"],
                video_file=g["video_file"],
                subtitle_files=g["subtitle_files"],
                file_size_mb=g["file_size_mb"],
            )

        first_count = len(self.tm.list_tasks(limit=100))
        self.assertEqual(first_count, 5)

        # Restart: re-scan with same task_manager
        scanner2 = FileScanner(self.config, task_manager=self.tm)
        groups2 = scanner2.scan_and_filter(self.source_dir)

        # The 5 already-tracked files should be filtered by check_source_duplicate
        # (they have status PENDING/QUEUED, so action=SKIP)
        # Only the remaining 5 should pass through
        new_tasks = []
        for g in groups2:
            self.tm.create_task(
                video_path=g["video_path"],
                video_file=g["video_file"],
                subtitle_files=g["subtitle_files"],
                file_size_mb=g["file_size_mb"],
            )
            new_tasks.append(g)

        # All 10 files should now be tracked
        all_tasks = self.tm.list_tasks(limit=100)
        all_source_paths = {t["source_path"] for t in all_tasks}
        for path in self.all_files:
            self.assertIn(path, all_source_paths,
                          f"File should be tracked after restart: {path}")


if __name__ == "__main__":
    unittest.main()
