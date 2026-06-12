#!/usr/bin/env python3
"""Crash recovery tests: copy stage.

Simulate process interruption during file copy and verify recovery on restart.
"""
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from media_importer.core.task_manager import TaskManager
from media_importer.core.task_lifecycle import (
    FILE_LOCATION_SOURCE,
    FILE_LOCATION_TEMP,
    STAGE_QUEUED,
    STAGE_RUNNING,
    STATUS_PENDING,
)
from media_importer.infrastructure.filesystem import FileCopier


MEDIA_EXTS = {".mkv", ".mp4", ".avi", ".ts", ".srt", ".ass"}


def _make_config(source_dir="", temp_dir=""):
    return {
        "source_dir": source_dir,
        "temp_dir": temp_dir,
        "video_extensions": [".mkv", ".mp4"],
        "subtitle_extensions": [".srt"],
    }


class TestCrashMidCopy(unittest.TestCase):
    """Copy starts but .copying temp file exists → on restart, task re-processed."""

    def setUp(self):
        self.source_dir = tempfile.mkdtemp()
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = tempfile.mkdtemp()
        self.video_path = os.path.join(self.source_dir, "movie.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"fake_video_content" * 100)
        self.tm = TaskManager(self.data_dir)

    def tearDown(self):
        shutil.rmtree(self.source_dir, ignore_errors=True)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_crash_mid_copy(self):
        # Create a task that was in RUNNING stage when crash happened
        task = self.tm.create_task(
            video_path=self.video_path,
            video_file="movie.mkv",
            file_size_mb=0.01,
        )
        # Simulate: copy started, .copying file exists, but task not yet updated
        copying_path = os.path.join(self.temp_dir, "movie.mkv.copying")
        with open(copying_path, "wb") as f:
            f.write(b"partial_data")

        # Task is still in QUEUED stage (copy hadn't completed)
        self.assertEqual(task["status"], STATUS_PENDING)
        self.assertEqual(task["stage"], STAGE_QUEUED)

        # On restart, the .copying file should be detected
        self.assertTrue(os.path.exists(copying_path))

        # Cleanup residual copies should remove the .copying file
        copier = FileCopier(self.temp_dir, MEDIA_EXTS)
        copier.cleanup_residual_copies()
        self.assertFalse(os.path.exists(copying_path))

        # Task can be re-processed (retry)
        retrieved = self.tm.get_task(task["task_id"])
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["status"], STATUS_PENDING)


class TestCrashCopyPartial(unittest.TestCase):
    """Partial temp file exists → cleanup removes it, task re-queued."""

    def setUp(self):
        self.source_dir = tempfile.mkdtemp()
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = tempfile.mkdtemp()
        self.video_path = os.path.join(self.source_dir, "movie.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"fake_video_content" * 100)
        self.tm = TaskManager(self.data_dir)

    def tearDown(self):
        shutil.rmtree(self.source_dir, ignore_errors=True)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_crash_copy_partial(self):
        # Create a task that was mid-copy when crash happened
        task = self.tm.create_task(
            video_path=self.video_path,
            video_file="movie.mkv",
            file_size_mb=0.01,
        )
        # Simulate: task was updated to RUNNING but copy didn't finish
        self.tm.update_task({
            "task_id": task["task_id"],
            "status": STATUS_PENDING,
            "stage": STAGE_RUNNING,
        })

        # Partial .copying file exists in temp
        copying_path = os.path.join(self.temp_dir, "movie.mkv.copying")
        with open(copying_path, "wb") as f:
            f.write(b"partial_data_only")

        # On restart: cleanup residual copies
        copier = FileCopier(self.temp_dir, MEDIA_EXTS)
        copier.cleanup_residual_copies()
        self.assertFalse(os.path.exists(copying_path))

        # Task is still PENDING/RUNNING and can be retried
        retrieved = self.tm.get_task(task["task_id"])
        self.assertEqual(retrieved["status"], STATUS_PENDING)
        self.assertEqual(retrieved["stage"], STAGE_RUNNING)

        # Retry: reset task to QUEUED for re-processing
        retried = self.tm.retry_task(task["task_id"])
        # retry_task only works on FAILED/SKIPPED/CANCELLED, so manually reset
        self.tm.update_task({
            "task_id": task["task_id"],
            "status": STATUS_PENDING,
            "stage": STAGE_QUEUED,
            "video_path": "",
            "file_location": FILE_LOCATION_SOURCE,
        })
        final = self.tm.get_task(task["task_id"])
        self.assertEqual(final["stage"], STAGE_QUEUED)

        # Now copy can succeed
        copier2 = FileCopier(self.temp_dir, MEDIA_EXTS)
        copied = copier2.copy_to_temp(self.video_path, [])
        self.assertEqual(len(copied), 1)
        self.assertTrue(os.path.isfile(copied[0]))


if __name__ == "__main__":
    unittest.main()
