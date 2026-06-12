#!/usr/bin/env python3
"""Crash recovery tests: dedup stage.

Simulate crash during dedup and verify partial state handling.
"""
import os
import shutil
import tempfile
import unittest

from media_importer.core.task_manager import TaskManager
from media_importer.core.task_lifecycle import (
    FILE_LOCATION_TEMP,
    STAGE_RUNNING,
    STATUS_PENDING,
)
from media_importer.core.db import update_task as db_update_task
from media_importer.features.recycle import move_to_recycle


def _make_scrape_result():
    return {
        "title_cn": "测试电影",
        "title_en": "Test Movie",
        "year": "2024",
        "type": "movie",
        "confidence": 0.9,
        "dimensions": {"media_type": "movie", "year": "2024"},
    }


class TestCrashDedupReplace(unittest.TestCase):
    """Old file moved to recycle, new not yet imported → on restart, recycle has old file."""

    def setUp(self):
        self.source_dir = tempfile.mkdtemp()
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = tempfile.mkdtemp()
        self.import_dir = tempfile.mkdtemp()
        self.recycle_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)
        self.video_path = os.path.join(self.source_dir, "movie.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"fake_video" * 100)
        self.temp_video = os.path.join(self.temp_dir, "movie.mkv")
        with open(self.temp_video, "wb") as f:
            f.write(b"fake_video" * 100)
        # Existing file in import dir (the one to be replaced)
        self.existing_file = os.path.join(self.import_dir, "测试电影.Test Movie.2024.mkv")
        with open(self.existing_file, "wb") as f:
            f.write(b"old_video" * 50)

    def tearDown(self):
        shutil.rmtree(self.source_dir, ignore_errors=True)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.data_dir, ignore_errors=True)
        shutil.rmtree(self.import_dir, ignore_errors=True)
        shutil.rmtree(self.recycle_dir, ignore_errors=True)

    def test_crash_dedup_replace(self):
        # Simulate: dedup strategy=replace, old file moved to recycle,
        # but crash before new file imported
        ok, dest, msg = move_to_recycle(
            self.existing_file, self.recycle_dir,
            reason="dedup_replace",
            task_id="test-task-1",
            source_dir=self.source_dir,
            import_roots=[self.import_dir],
        )
        self.assertTrue(ok, f"Move to recycle should succeed: {msg}")

        # Old file is now in recycle
        self.assertFalse(os.path.exists(self.existing_file))

        # Task state: still RUNNING (crash before import)
        task = self.tm.create_task(
            video_path=self.video_path,
            video_file="movie.mkv",
            file_size_mb=0.01,
        )
        scrape_result = _make_scrape_result()
        import_path = self.import_dir

        db_update_task(
            self.tm.conn, task["task_id"],
            status=STATUS_PENDING,
            stage=STAGE_RUNNING,
            file_location=FILE_LOCATION_TEMP,
            video_path=self.temp_video,
            scrape_result=scrape_result,
            import_path=import_path,
            classify_result="media_type=movie",
            dedup_result={"is_duplicate": True, "action": "replace"},
            dedup_existing_file="测试电影.Test Movie.2024.mkv",
            current_step=6,
            step_name="dedup",
            percentage=70,
        )

        # On restart: old file is in recycle, new file still in temp
        recovered = self.tm.get_task(task["task_id"])
        self.assertEqual(recovered["status"], STATUS_PENDING)
        self.assertEqual(recovered["stage"], STAGE_RUNNING)

        # Recycle dir has the old file
        recycle_files = []
        for root, dirs, files in os.walk(self.recycle_dir):
            for f in files:
                if not f.endswith(".meta"):
                    recycle_files.append(f)
        self.assertGreater(len(recycle_files), 0, "Recycle dir should contain the old file")

        # Temp file still exists for re-processing
        self.assertTrue(os.path.isfile(self.temp_video))


class TestCrashDedupInProgress(unittest.TestCase):
    """Dedup started but not completed → task re-processed."""

    def setUp(self):
        self.source_dir = tempfile.mkdtemp()
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = tempfile.mkdtemp()
        self.import_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)
        self.video_path = os.path.join(self.source_dir, "movie.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"fake_video" * 100)
        self.temp_video = os.path.join(self.temp_dir, "movie.mkv")
        with open(self.temp_video, "wb") as f:
            f.write(b"fake_video" * 100)

    def tearDown(self):
        shutil.rmtree(self.source_dir, ignore_errors=True)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.data_dir, ignore_errors=True)
        shutil.rmtree(self.import_dir, ignore_errors=True)

    def test_crash_dedup_in_progress(self):
        # Create task that was mid-dedup when crash happened
        task = self.tm.create_task(
            video_path=self.video_path,
            video_file="movie.mkv",
            file_size_mb=0.01,
        )
        scrape_result = _make_scrape_result()

        # Simulate: classify done, dedup step started but not completed
        db_update_task(
            self.tm.conn, task["task_id"],
            status=STATUS_PENDING,
            stage=STAGE_RUNNING,
            file_location=FILE_LOCATION_TEMP,
            video_path=self.temp_video,
            scrape_result=scrape_result,
            import_path=self.import_dir,
            classify_result="media_type=movie",
            current_step=6,
            step_name="dedup",
            percentage=65,
        )

        # On restart: task is still PENDING/RUNNING
        recovered = self.tm.get_task(task["task_id"])
        self.assertEqual(recovered["status"], STATUS_PENDING)
        self.assertEqual(recovered["stage"], STAGE_RUNNING)
        self.assertEqual(recovered["step_name"], "dedup")

        # Task can be re-processed: all prior state is available
        self.assertIsNotNone(recovered["import_path"])
        self.assertTrue(os.path.isfile(self.temp_video))

        # Re-running dedup should be safe (idempotent check)
        self.assertEqual(recovered["current_step"], 6)


if __name__ == "__main__":
    unittest.main()
