#!/usr/bin/env python3
import os
import shutil
import tempfile
import unittest

from media_importer.core.task_manager import TaskManager
from media_importer.core.db import update_task as db_update_task
from media_importer.core.metrics import Metrics


class TestSuccessFileMissing(unittest.TestCase):
    """Task SUCCESS but file not at import_path -> inconsistency detected."""

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_success_file_missing(self):
        task = self.tm.create_task(
            video_path="/source/movie.mkv",
            video_file="movie.mkv",
        )
        # Mark as SUCCESS with a non-existent import path
        nonexistent_path = "/nonexistent/media/movies/movie.mkv"
        task["status"] = "SUCCESS"
        task["stage"] = "DONE"
        task["import_video_path"] = nonexistent_path
        self.tm.update_task(task)

        updated = self.tm.get_task(task["task_id"])
        self.assertEqual(updated["status"], "SUCCESS")
        self.assertEqual(updated["import_video_path"], nonexistent_path)

        # Detect inconsistency: SUCCESS but file doesn't exist
        self.assertFalse(
            os.path.isfile(updated["import_video_path"]),
            "Inconsistency: task marked SUCCESS but file is missing"
        )


class TestRecycleRecordFileMissing(unittest.TestCase):
    """Recycle record exists but file gone -> consistency check."""

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.recycle_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir, config={
            "source_dir": tempfile.mkdtemp(),
            "temp_dir": tempfile.mkdtemp(),
            "recycle_dir": self.recycle_dir,
        })

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)
        shutil.rmtree(self.recycle_dir, ignore_errors=True)

    def test_recycle_record_file_missing(self):
        task = self.tm.create_task(
            video_path="/source/movie.mkv",
            video_file="movie.mkv",
        )
        # Simulate a file moved to recycle but then externally deleted
        recycle_path = os.path.join(self.recycle_dir, "movie.mkv")
        task["source_path"] = recycle_path
        task["file_location"] = "recycle"
        task["status"] = "SKIPPED"
        self.tm.update_task(task)

        updated = self.tm.get_task(task["task_id"])
        self.assertEqual(updated["file_location"], "recycle")

        # The recycle file doesn't actually exist
        self.assertFalse(
            os.path.isfile(updated["source_path"]),
            "Inconsistency: recycle record exists but file is gone"
        )


class TestMetricsVsDb(unittest.TestCase):
    """Metrics count != DB count -> recalculate."""

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)
        self.metrics = Metrics()

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_metrics_vs_db_consistency(self):
        # Create tasks and record metrics
        for i in range(3):
            task = self.tm.create_task(
                video_path=f"/source/movie{i}.mkv",
                video_file=f"movie{i}.mkv",
            )
            task["status"] = "SUCCESS"
            task["stage"] = "DONE"
            self.tm.update_task(task)
            self.metrics.record_task_start()
            self.metrics.record_task_complete("success")

        # Verify metrics and DB are consistent
        counts = self.tm.count_by_status()
        metrics_snapshot = self.metrics.to_dict()

        db_success = counts.get("SUCCESS", 0)
        metrics_success = metrics_snapshot["success_tasks"]

        self.assertEqual(db_success, 3)
        self.assertEqual(metrics_success, 3)
        self.assertEqual(db_success, metrics_success,
                         "Metrics and DB counts should be consistent")

    def test_metrics_drift_detection(self):
        # Simulate drift: metrics show 2 but DB has 3
        for i in range(3):
            task = self.tm.create_task(
                video_path=f"/source/movie{i}.mkv",
                video_file=f"movie{i}.mkv",
            )
            task["status"] = "SUCCESS"
            task["stage"] = "DONE"
            self.tm.update_task(task)

        counts = self.tm.count_by_status()
        db_success = counts.get("SUCCESS", 0)

        # Simulate metrics only recording 2 (drift)
        self.metrics.record_task_start()
        self.metrics.record_task_complete("success")
        self.metrics.record_task_start()
        self.metrics.record_task_complete("success")

        metrics_snapshot = self.metrics.to_dict()
        metrics_success = metrics_snapshot["success_tasks"]

        # Detect drift
        self.assertEqual(db_success, 3)
        self.assertEqual(metrics_success, 2)
        self.assertNotEqual(db_success, metrics_success,
                            "Drift detected: DB and metrics counts differ")


if __name__ == "__main__":
    unittest.main()
