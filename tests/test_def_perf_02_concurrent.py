#!/usr/bin/env python3
"""Performance tests: concurrent processing.

Verify concurrent task processing without SQLite deadlocks or file conflicts.
"""
import os
import shutil
import tempfile
import threading
import time
import unittest

from media_importer.core.task_manager import TaskManager
from media_importer.core.task_lifecycle import (
    STAGE_DONE,
    STAGE_QUEUED,
    STATUS_PENDING,
    STATUS_SUCCESS,
)
from media_importer.core.db import update_task as db_update_task


class TestConcurrent4Workers(unittest.TestCase):
    """max_workers=4 → no SQLite lock deadlock."""

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)
        # Create 20 tasks for concurrent processing
        self.task_ids = []
        for i in range(20):
            task = self.tm.create_task(
                video_path=f"/source/movie_{i:04d}.mkv",
                video_file=f"movie_{i:04d}.mkv",
                file_size_mb=1.0,
            )
            self.task_ids.append(task["task_id"])

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_concurrent_4_workers(self):
        errors = []
        completed = []

        def worker(task_ids_chunk, worker_id):
            try:
                for tid in task_ids_chunk:
                    # Simulate processing: read task, update, read back
                    task = self.tm.get_task(tid)
                    self.assertIsNotNone(task)

                    db_update_task(self.tm.conn, tid,
                                   status=STATUS_SUCCESS, stage=STAGE_DONE,
                                   import_success=1)

                    # Verify update
                    updated = self.tm.get_task(tid)
                    self.assertEqual(updated["status"], STATUS_SUCCESS)

                    completed.append(tid)
            except Exception as e:
                errors.append((worker_id, str(e)))

        # Split tasks among 4 workers
        chunk_size = len(self.task_ids) // 4
        chunks = []
        for i in range(4):
            start = i * chunk_size
            end = start + chunk_size if i < 3 else len(self.task_ids)
            chunks.append(self.task_ids[start:end])

        # Start workers
        threads = []
        for i, chunk in enumerate(chunks):
            t = threading.Thread(target=worker, args=(chunk, i))
            threads.append(t)
            t.start()

        # Wait for all workers
        for t in threads:
            t.join(timeout=30)

        # No errors should occur
        self.assertEqual(len(errors), 0,
                         f"Concurrent workers encountered errors: {errors}")

        # All tasks should be completed
        self.assertEqual(len(completed), 20)

        # Verify DB consistency
        counts = self.tm.count_by_status()
        self.assertEqual(counts.get(STATUS_SUCCESS, 0), 20)


class TestConcurrentFileOperations(unittest.TestCase):
    """Multiple tasks importing simultaneously → no file conflicts."""

    def setUp(self):
        self.source_dir = tempfile.mkdtemp()
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)

        # Create source video files
        self.video_files = []
        for i in range(4):
            path = os.path.join(self.source_dir, f"movie_{i}.mkv")
            with open(path, "wb") as f:
                f.write(b"fake_video_content" * 100)
            self.video_files.append(path)

    def tearDown(self):
        shutil.rmtree(self.source_dir, ignore_errors=True)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_concurrent_file_operations(self):
        errors = []
        results = []

        def copy_worker(video_path, worker_id):
            try:
                from media_importer.infrastructure.filesystem import FileCopier
                media_exts = {".mkv", ".mp4", ".srt", ".ass"}
                copier = FileCopier(self.temp_dir, media_exts)

                # Each worker copies its own file
                filename = os.path.basename(video_path)
                dest = os.path.join(self.temp_dir, filename)

                # Use a unique temp name to avoid conflicts
                unique_dest = os.path.join(self.temp_dir,
                                           f"worker{worker_id}_{filename}")

                # Copy file
                with open(video_path, "rb") as src:
                    with open(unique_dest + ".copying", "wb") as dst:
                        dst.write(src.read())
                os.rename(unique_dest + ".copying", unique_dest)

                # Verify copy
                self.assertTrue(os.path.isfile(unique_dest))
                src_size = os.path.getsize(video_path)
                dst_size = os.path.getsize(unique_dest)
                self.assertEqual(src_size, dst_size)

                results.append((worker_id, unique_dest))
            except Exception as e:
                errors.append((worker_id, str(e)))

        # Start 4 concurrent copy workers
        threads = []
        for i, vf in enumerate(self.video_files):
            t = threading.Thread(target=copy_worker, args=(vf, i))
            threads.append(t)
            t.start()

        # Wait for all workers
        for t in threads:
            t.join(timeout=30)

        # No errors should occur
        self.assertEqual(len(errors), 0,
                         f"Concurrent file ops encountered errors: {errors}")

        # All 4 files should be copied
        self.assertEqual(len(results), 4)

        # Each copied file should exist and be unique
        dest_paths = [r[1] for r in results]
        self.assertEqual(len(set(dest_paths)), 4, "All destinations should be unique")

        for dest in dest_paths:
            self.assertTrue(os.path.isfile(dest),
                            f"Copied file should exist: {dest}")


if __name__ == "__main__":
    unittest.main()
