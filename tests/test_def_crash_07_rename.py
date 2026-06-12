#!/usr/bin/env python3
"""Crash recovery tests: rename stage.

Simulate crash after rename and verify final_filename persists.
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


def _make_scrape_result():
    return {
        "title_cn": "测试电影",
        "title_en": "Test Movie",
        "year": "2024",
        "type": "movie",
        "confidence": 0.9,
        "dimensions": {"media_type": "movie", "year": "2024"},
    }


class TestCrashAfterRename(unittest.TestCase):
    """final_filename set in DB → on restart, import uses final_filename."""

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

    def test_crash_after_rename(self):
        # Create task and advance to after rename, crash before import
        task = self.tm.create_task(
            video_path=self.video_path,
            video_file="movie.mkv",
            file_size_mb=0.01,
        )
        scrape_result = _make_scrape_result()
        import_path = self.import_dir
        final_filename = "测试电影.Test Movie.2024.1080p.BluRay.mkv"

        # Simulate: rename completed, final_filename persisted, then crash
        db_update_task(
            self.tm.conn, task["task_id"],
            status=STATUS_PENDING,
            stage=STAGE_RUNNING,
            file_location=FILE_LOCATION_TEMP,
            video_path=self.temp_video,
            scrape_result=scrape_result,
            scrape_title_cn=scrape_result["title_cn"],
            scrape_year=scrape_result["year"],
            scrape_media_type=scrape_result["type"],
            scrape_confidence=scrape_result["confidence"],
            scrape_dimensions=scrape_result["dimensions"],
            import_path=import_path,
            classify_result="media_type=movie",
            final_filename=final_filename,
            current_step=7,
            step_name="rename",
            percentage=75,
        )

        # On restart: task still has final_filename
        recovered = self.tm.get_task(task["task_id"])
        self.assertEqual(recovered["status"], STATUS_PENDING)
        self.assertEqual(recovered["stage"], STAGE_RUNNING)
        self.assertEqual(recovered["final_filename"], final_filename)

        # The import step should use the final_filename
        self.assertIn("测试电影", recovered["final_filename"])
        self.assertTrue(recovered["final_filename"].endswith(".mkv"))

        # Temp video still exists for import
        self.assertTrue(os.path.isfile(self.temp_video))

        # Verify import_path is set
        self.assertEqual(recovered["import_path"], import_path)


if __name__ == "__main__":
    unittest.main()
