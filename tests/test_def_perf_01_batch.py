#!/usr/bin/env python3
"""Performance tests: batch processing.

Verify batch task processing performance and memory behavior.
"""
import os
import shutil
import tempfile
import time
import tracemalloc
import unittest

from media_importer.core.task_manager import TaskManager
from media_importer.core.task_lifecycle import (
    STAGE_DONE,
    STAGE_QUEUED,
    STATUS_PENDING,
    STATUS_SUCCESS,
)
from media_importer.core.db import update_task as db_update_task


class TestBatch100Tasks(unittest.TestCase):
    """Create 100 tasks → all complete without blocking."""

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_batch_100_tasks(self):
        # Create 100 tasks
        task_ids = []
        start = time.time()
        for i in range(100):
            task = self.tm.create_task(
                video_path=f"/source/movie_{i:04d}.mkv",
                video_file=f"movie_{i:04d}.mkv",
                file_size_mb=1.0,
            )
            task_ids.append(task["task_id"])
        create_elapsed = time.time() - start

        # All 100 tasks should be in DB
        all_tasks = self.tm.list_all_tasks(limit=200)
        self.assertEqual(len(all_tasks), 100)

        # Simulate completing all tasks
        start = time.time()
        for tid in task_ids:
            db_update_task(self.tm.conn, tid,
                           status=STATUS_SUCCESS, stage=STAGE_DONE,
                           import_success=1)
        complete_elapsed = time.time() - start

        # Verify all completed
        counts = self.tm.count_by_status()
        self.assertEqual(counts.get(STATUS_SUCCESS, 0), 100)

        # Performance: creating and completing 100 tasks should be fast
        # (generous limits for CI environments)
        self.assertLess(create_elapsed, 30.0,
                        f"Creating 100 tasks took {create_elapsed:.2f}s")
        self.assertLess(complete_elapsed, 30.0,
                        f"Completing 100 tasks took {complete_elapsed:.2f}s")

        # Listing should also be fast
        start = time.time()
        _ = self.tm.list_tasks(limit=100)
        list_elapsed = time.time() - start
        self.assertLess(list_elapsed, 5.0,
                        f"Listing 100 tasks took {list_elapsed:.2f}s")


class TestBatchMemoryUsage(unittest.TestCase):
    """Process 50 tasks → memory doesn't grow unbounded."""

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_batch_memory_usage(self):
        tracemalloc.start()

        # Create 50 tasks
        task_ids = []
        for i in range(50):
            task = self.tm.create_task(
                video_path=f"/source/movie_{i:04d}.mkv",
                video_file=f"movie_{i:04d}.mkv",
                file_size_mb=1.0,
            )
            task_ids.append(task["task_id"])

        snapshot1 = tracemalloc.take_snapshot()

        # Process all tasks (simulate completion)
        for tid in task_ids:
            db_update_task(self.tm.conn, tid,
                           status=STATUS_SUCCESS, stage=STAGE_DONE,
                           import_success=1)
            # Also read back to simulate real processing
            _ = self.tm.get_task(tid)

        snapshot2 = tracemalloc.take_snapshot()

        # Compare memory growth
        stats = snapshot2.compare_to(snapshot1, "lineno")
        total_growth = sum(s.size_diff for s in stats)

        # Memory growth should be reasonable (less than 50MB for 50 tasks)
        growth_mb = total_growth / (1024 * 1024)
        self.assertLess(growth_mb, 50,
                        f"Memory grew by {growth_mb:.1f}MB for 50 tasks")

        tracemalloc.stop()

        # Verify all tasks completed
        counts = self.tm.count_by_status()
        self.assertEqual(counts.get(STATUS_SUCCESS, 0), 50)


if __name__ == "__main__":
    unittest.main()
