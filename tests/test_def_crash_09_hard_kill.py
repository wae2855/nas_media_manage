#!/usr/bin/env python3
"""Crash recovery tests: SIGKILL (uncatchable).

Simulate hard kill and verify temp file cleanup and DB consistency.
"""
import os
import shutil
import tempfile
import unittest

from media_importer.core.task_manager import TaskManager
from media_importer.core.task_lifecycle import (
    FILE_LOCATION_SOURCE,
    FILE_LOCATION_TEMP,
    STAGE_DONE,
    STAGE_QUEUED,
    STAGE_RUNNING,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SUCCESS,
)
from media_importer.core.db import update_task as db_update_task
from media_importer.infrastructure.filesystem import FileCopier


MEDIA_EXTS = {".mkv", ".mp4", ".avi", ".ts", ".srt", ".ass"}


class TestHardKillTempResidue(unittest.TestCase):
    """Temp files remain → cleanup on restart."""

    def setUp(self):
        self.source_dir = tempfile.mkdtemp()
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)

    def tearDown(self):
        shutil.rmtree(self.source_dir, ignore_errors=True)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_hard_kill_temp_residue(self):
        # Simulate: process was SIGKILL'd, leaving .copying files in temp
        copying1 = os.path.join(self.temp_dir, "movie1.mkv.copying")
        copying2 = os.path.join(self.temp_dir, "movie2.mkv.copying")
        completed = os.path.join(self.temp_dir, "movie3.mkv")

        with open(copying1, "wb") as f:
            f.write(b"partial1")
        with open(copying2, "wb") as f:
            f.write(b"partial2")
        with open(completed, "wb") as f:
            f.write(b"complete_video")

        # On restart: cleanup residual copies
        copier = FileCopier(self.temp_dir, MEDIA_EXTS)
        copier.cleanup_residual_copies()

        # .copying files should be removed
        self.assertFalse(os.path.exists(copying1))
        self.assertFalse(os.path.exists(copying2))

        # Completed files should remain
        self.assertTrue(os.path.exists(completed))


class TestHardKillDbConsistent(unittest.TestCase):
    """DB state is self-consistent (no orphan records)."""

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_hard_kill_db_consistent(self):
        # Create several tasks in different states
        task1 = self.tm.create_task(
            video_path="/source/movie1.mkv",
            video_file="movie1.mkv",
            file_size_mb=1.0,
        )
        task2 = self.tm.create_task(
            video_path="/source/movie2.mkv",
            video_file="movie2.mkv",
            file_size_mb=2.0,
        )
        task3 = self.tm.create_task(
            video_path="/source/movie3.mkv",
            video_file="movie3.mkv",
            file_size_mb=3.0,
        )

        # Advance task1 to RUNNING
        db_update_task(self.tm.conn, task1["task_id"],
                       status=STATUS_PENDING, stage=STAGE_RUNNING)

        # Advance task2 to SUCCESS
        db_update_task(self.tm.conn, task2["task_id"],
                       status=STATUS_SUCCESS, stage=STAGE_DONE)

        # task3 stays at QUEUED

        # After SIGKILL and restart: verify DB is self-consistent
        all_tasks = self.tm.list_all_tasks(limit=100)
        self.assertEqual(len(all_tasks), 3)

        # Each task has a valid status/stage combination
        for t in all_tasks:
            self.assertIn(t["status"], ["PENDING", "SUCCESS", "FAILED",
                                        "SKIPPED", "CANCELLED"])
            self.assertIn(t["stage"], ["QUEUED", "RUNNING",
                                       "AWAIT_REVIEW", "DONE"])

        # Verify specific states survived
        t1 = self.tm.get_task(task1["task_id"])
        self.assertEqual(t1["status"], STATUS_PENDING)
        self.assertEqual(t1["stage"], STAGE_RUNNING)

        t2 = self.tm.get_task(task2["task_id"])
        self.assertEqual(t2["status"], STATUS_SUCCESS)
        self.assertEqual(t2["stage"], STAGE_DONE)

        t3 = self.tm.get_task(task3["task_id"])
        self.assertEqual(t3["status"], STATUS_PENDING)
        self.assertEqual(t3["stage"], STAGE_QUEUED)

        # Count by status should be consistent
        counts = self.tm.count_by_status()
        total_from_counts = sum(counts.values())
        self.assertEqual(total_from_counts, 3)

        # No orphan records: every task has a task_id
        for t in all_tasks:
            self.assertTrue(t["task_id"], "Task should have a task_id")


if __name__ == "__main__":
    unittest.main()
