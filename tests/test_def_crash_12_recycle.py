#!/usr/bin/env python3
"""Crash recovery tests: recycle operations.

Simulate crash during recycle and verify partial state handling.
"""
import json
import os
import shutil
import tempfile
import unittest

from media_importer.core.task_manager import TaskManager
from media_importer.features.recycle import move_to_recycle


class TestCrashMidRecycle(unittest.TestCase):
    """Some files in recycle, some not → partial state preserved."""

    def setUp(self):
        self.source_dir = tempfile.mkdtemp()
        self.import_dir = tempfile.mkdtemp()
        self.recycle_dir = tempfile.mkdtemp()
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)

    def tearDown(self):
        shutil.rmtree(self.source_dir, ignore_errors=True)
        shutil.rmtree(self.import_dir, ignore_errors=True)
        shutil.rmtree(self.recycle_dir, ignore_errors=True)
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_crash_mid_recycle(self):
        # Create files to be recycled
        file1 = os.path.join(self.source_dir, "movie1.mkv")
        file2 = os.path.join(self.source_dir, "movie2.mkv")
        with open(file1, "wb") as f:
            f.write(b"video1")
        with open(file2, "wb") as f:
            f.write(b"video2")

        # Simulate: file1 moved to recycle, but process crashed before file2
        ok, dest1, msg = move_to_recycle(
            file1, self.recycle_dir,
            reason="dedup_replace",
            task_id="task-1",
            source_dir=self.source_dir,
            import_roots=[self.import_dir],
        )
        self.assertTrue(ok, f"First recycle should succeed: {msg}")

        # file1 is now in recycle
        self.assertFalse(os.path.exists(file1))

        # file2 is still in source (crash happened before it was recycled)
        self.assertTrue(os.path.exists(file2))

        # On restart: partial state is preserved
        # Recycle dir has file1
        recycle_files = []
        for root, dirs, files in os.walk(self.recycle_dir):
            for f in files:
                if not f.endswith(".meta"):
                    recycle_files.append(os.path.join(root, f))
        self.assertGreater(len(recycle_files), 0, "Recycle should contain file1")

        # file2 can still be recycled
        ok, dest2, msg = move_to_recycle(
            file2, self.recycle_dir,
            reason="dedup_replace",
            task_id="task-2",
            source_dir=self.source_dir,
            import_roots=[self.import_dir],
        )
        self.assertTrue(ok, f"Second recycle should succeed: {msg}")
        self.assertFalse(os.path.exists(file2))


class TestCrashRecycleRecord(unittest.TestCase):
    """Recycle record exists but file missing → handled gracefully."""

    def setUp(self):
        self.source_dir = tempfile.mkdtemp()
        self.import_dir = tempfile.mkdtemp()
        self.recycle_dir = tempfile.mkdtemp()
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)

    def tearDown(self):
        shutil.rmtree(self.source_dir, ignore_errors=True)
        shutil.rmtree(self.import_dir, ignore_errors=True)
        shutil.rmtree(self.recycle_dir, ignore_errors=True)
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_crash_recycle_record(self):
        # Create a file and move it to recycle
        src_file = os.path.join(self.source_dir, "movie.mkv")
        with open(src_file, "wb") as f:
            f.write(b"video_content")

        ok, dest, msg = move_to_recycle(
            src_file, self.recycle_dir,
            reason="source_cleanup",
            task_id="task-1",
            source_dir=self.source_dir,
            import_roots=[self.import_dir],
        )
        self.assertTrue(ok, f"Recycle should succeed: {msg}")

        # Find the meta file
        meta_files = []
        for root, dirs, files in os.walk(self.recycle_dir):
            for f in files:
                if f.endswith(".meta"):
                    meta_files.append(os.path.join(root, f))

        self.assertGreater(len(meta_files), 0, "Meta file should exist")

        # Read and verify meta content
        with open(meta_files[0], "r", encoding="utf-8") as f:
            meta = json.load(f)
        self.assertIn("original_path", meta)
        self.assertEqual(meta["reason"], "source_cleanup")
        self.assertEqual(meta["task_id"], "task-1")

        # Simulate: crash caused the recycled file to be lost
        # (e.g., external cleanup or disk error)
        recycled_file = dest
        if os.path.exists(recycled_file):
            os.remove(recycled_file)

        # Meta file still exists but actual file is gone
        self.assertTrue(os.path.exists(meta_files[0]))
        self.assertFalse(os.path.exists(recycled_file))

        # The system should handle this gracefully:
        # move_to_recycle on a non-existent source returns success (idempotent)
        ok2, _, msg2 = move_to_recycle(
            src_file, self.recycle_dir,
            reason="source_cleanup",
            task_id="task-1",
            source_dir=self.source_dir,
            import_roots=[self.import_dir],
        )
        # Source file no longer exists, so move_to_recycle returns True
        # (file already gone, nothing to do)
        self.assertTrue(ok2, f"Re-recycling non-existent file should be ok: {msg2}")


if __name__ == "__main__":
    unittest.main()
