#!/usr/bin/env python3
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from media_importer.core.task_manager import TaskManager
from media_importer.core.metrics import Metrics


class TestRecordSuccess(unittest.TestCase):
    """After import -> task status=SUCCESS, stage=DONE."""

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_record_success(self):
        task = self.tm.create_task(
            video_path="/source/movie.mkv",
            video_file="movie.mkv",
        )
        task["status"] = "SUCCESS"
        task["stage"] = "DONE"
        task["import_video_path"] = "/media/movies/movie.mkv"
        task["current_step"] = 10
        task["step_name"] = "record"
        task["percentage"] = 100
        self.tm.update_task(task)

        updated = self.tm.get_task(task["task_id"])
        self.assertEqual(updated["status"], "SUCCESS")
        self.assertEqual(updated["stage"], "DONE")
        self.assertEqual(updated["import_video_path"], "/media/movies/movie.mkv")


class TestRecordPersistence(unittest.TestCase):
    """Record -> update_task called with correct fields."""

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_record_persistence(self):
        task = self.tm.create_task(
            video_path="/source/movie.mkv",
            video_file="movie.mkv",
        )
        task["status"] = "SUCCESS"
        task["stage"] = "DONE"
        task["import_video_path"] = "/media/movies/Test.2024.mkv"
        task["current_step"] = 10
        task["step_name"] = "record"
        task["percentage"] = 100
        task["import_success"] = 1
        self.tm.update_task(task)

        updated = self.tm.get_task(task["task_id"])
        self.assertEqual(updated["status"], "SUCCESS")
        self.assertEqual(updated["stage"], "DONE")
        self.assertEqual(updated["import_video_path"], "/media/movies/Test.2024.mkv")
        self.assertEqual(updated["import_success"], 1)
        self.assertEqual(updated["percentage"], 100)


class TestRecordFileConsistency(unittest.TestCase):
    """SUCCESS task -> target file actually exists on disk."""

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.imp_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)
        # Create a real file at the import path
        self.imported_file = os.path.join(self.imp_dir, "Test.2024.mkv")
        with open(self.imported_file, "wb") as f:
            f.write(b"video_content")

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)
        shutil.rmtree(self.imp_dir, ignore_errors=True)

    def test_record_file_consistency(self):
        task = self.tm.create_task(
            video_path="/source/movie.mkv",
            video_file="movie.mkv",
        )
        task["status"] = "SUCCESS"
        task["stage"] = "DONE"
        task["import_video_path"] = self.imported_file
        self.tm.update_task(task)

        updated = self.tm.get_task(task["task_id"])
        self.assertEqual(updated["status"], "SUCCESS")
        # Verify the file actually exists at the recorded path
        self.assertTrue(
            os.path.isfile(updated["import_video_path"]),
            f"File should exist at {updated['import_video_path']}"
        )


class TestRecordMetricsAccuracy(unittest.TestCase):
    """Metrics count matches DB query result."""

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)
        self.metrics = Metrics()

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_record_metrics_accuracy(self):
        # Create 3 tasks, mark 2 as success, 1 as failed
        for i in range(2):
            task = self.tm.create_task(
                video_path=f"/source/movie{i}.mkv",
                video_file=f"movie{i}.mkv",
            )
            task["status"] = "SUCCESS"
            task["stage"] = "DONE"
            self.tm.update_task(task)
            self.metrics.record_task_start()
            self.metrics.record_task_complete("success")

        task = self.tm.create_task(
            video_path="/source/fail.mkv",
            video_file="fail.mkv",
        )
        task["status"] = "FAILED"
        task["stage"] = "DONE"
        self.tm.update_task(task)
        self.metrics.record_task_start()
        self.metrics.record_task_complete("failed")

        # Verify metrics counters match DB
        counts = self.tm.count_by_status()
        self.assertEqual(counts.get("SUCCESS", 0), 2)
        self.assertEqual(counts.get("FAILED", 0), 1)

        metrics_snapshot = self.metrics.to_dict()
        self.assertEqual(metrics_snapshot["success_tasks"], 2)
        self.assertEqual(metrics_snapshot["failed_tasks"], 1)


if __name__ == "__main__":
    unittest.main()
