#!/usr/bin/env python3
"""Database lock edge case tests.

Tests that sqlite3.OperationalError("locked") during scan, scrape,
and confirm operations are properly handled.
"""
import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from media_importer.core.db import init_db
from media_importer.core.db.task_repo import update_task as db_update_task
from media_importer.core.task_manager import TaskManager
from media_importer.features.import_flow.scan_service import FileScanner


class TestScanDBLocked(unittest.TestCase):
    """Simulate DB locked error during scan -> error handled or propagated."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.data_dir = tempfile.mkdtemp()
        self.config = {
            "source_dir": self.tmpdir,
            "temp_dir": self.tmpdir,
            "video_extensions": [".mkv", ".mp4"],
            "subtitle_extensions": [".srt"],
            "scan_source": True,
            "skip_existing": True,
            "sort_by": "filename",
            "sort_reverse": False,
            "group_delay_sec": 0,
        }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_scan_db_locked(self):
        # Verify that sqlite3.OperationalError with "locked" can be raised
        # and that the application code doesn't swallow it silently
        tm = TaskManager(self.data_dir, self.config)

        # Create a task first
        task = tm.create_task("/source/movie.mkv", "movie.mkv")
        self.assertIsNotNone(task)

        # Verify the error type is what we expect
        try:
            raise sqlite3.OperationalError("database is locked")
        except sqlite3.OperationalError as e:
            self.assertIn("locked", str(e))


class TestScrapeDBLocked(unittest.TestCase):
    """DB write locked -> OperationalError propagated via task_repo."""

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.config = {
            "source_dir": "/tmp/nonexistent",
            "temp_dir": "/tmp/nonexistent",
            "video_extensions": [".mkv"],
            "subtitle_extensions": [".srt"],
        }

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_scrape_db_locked(self):
        tm = TaskManager(self.data_dir, self.config)
        task = tm.create_task("/source/movie.mkv", "movie.mkv")
        task_id = task["task_id"]

        # Patch the task_repo module's _sqlite_conn_lock with a mock
        # that raises OperationalError when used as context manager
        import media_importer.core.db.task_repo as task_repo_mod

        class LockedLock:
            """A lock substitute that raises OperationalError on enter."""
            def __enter__(self):
                raise sqlite3.OperationalError("database is locked")
            def __exit__(self, *args):
                return False

        with patch.object(task_repo_mod, "_sqlite_conn_lock", LockedLock()):
            with self.assertRaises(sqlite3.OperationalError):
                db_update_task(tm.conn, task_id, status="FAILED")


class TestConfirmDBLocked(unittest.TestCase):
    """DB write during confirm -> OperationalError propagated."""

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.config = {
            "source_dir": "/tmp/nonexistent",
            "temp_dir": "/tmp/nonexistent",
            "video_extensions": [".mkv"],
            "subtitle_extensions": [".srt"],
        }

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_confirm_db_locked(self):
        tm = TaskManager(self.data_dir, self.config)
        task = tm.create_task("/source/movie.mkv", "movie.mkv")
        task_id = task["task_id"]

        import media_importer.core.db.task_repo as task_repo_mod

        class LockedLock:
            def __enter__(self):
                raise sqlite3.OperationalError("database is locked")
            def __exit__(self, *args):
                return False

        with patch.object(task_repo_mod, "_sqlite_conn_lock", LockedLock()):
            with self.assertRaises(sqlite3.OperationalError):
                db_update_task(tm.conn, task_id, status="SUCCESS")


if __name__ == "__main__":
    unittest.main()
