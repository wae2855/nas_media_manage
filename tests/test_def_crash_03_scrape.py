#!/usr/bin/env python3
"""Crash recovery tests: scrape stage.

Simulate crash after scrape but before validate, verify recovery.
"""
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from media_importer.core.task_manager import TaskManager
from media_importer.core.task_lifecycle import (
    FILE_LOCATION_TEMP,
    STAGE_QUEUED,
    STAGE_RUNNING,
    STATUS_PENDING,
)
from media_importer.core.db import update_task as db_update_task


def _make_scrape_result(title_cn="测试电影", title_en="Test Movie",
                        year="2024", media_type="movie", confidence=0.9):
    return {
        "title_cn": title_cn,
        "title_en": title_en,
        "year": year,
        "type": media_type,
        "confidence": confidence,
        "dimensions": {"media_type": media_type, "year": year},
    }


class TestCrashAfterScrape(unittest.TestCase):
    """scrape_result written to DB → on restart, task still PENDING/RUNNING."""

    def setUp(self):
        self.source_dir = tempfile.mkdtemp()
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)
        self.video_path = os.path.join(self.source_dir, "movie.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"fake_video" * 100)

    def tearDown(self):
        shutil.rmtree(self.source_dir, ignore_errors=True)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_crash_after_scrape(self):
        # Create task and advance to RUNNING with scrape_result
        task = self.tm.create_task(
            video_path=self.video_path,
            video_file="movie.mkv",
            file_size_mb=0.01,
        )
        scrape_result = _make_scrape_result()

        # Simulate: scrape completed, result persisted, but process crashed
        # before validate could run
        db_update_task(
            self.tm.conn, task["task_id"],
            status=STATUS_PENDING,
            stage=STAGE_RUNNING,
            file_location=FILE_LOCATION_TEMP,
            video_path=os.path.join(self.temp_dir, "movie.mkv"),
            scrape_result=scrape_result,
            scrape_title_cn=scrape_result["title_cn"],
            scrape_title_en=scrape_result["title_en"],
            scrape_year=scrape_result["year"],
            scrape_media_type=scrape_result["type"],
            scrape_confidence=scrape_result["confidence"],
            scrape_dimensions=scrape_result["dimensions"],
        )

        # On restart: task is still PENDING/RUNNING with scrape_result
        recovered = self.tm.get_task(task["task_id"])
        self.assertEqual(recovered["status"], STATUS_PENDING)
        self.assertEqual(recovered["stage"], STAGE_RUNNING)
        self.assertIsNotNone(recovered["scrape_result"])
        self.assertEqual(recovered["scrape_result"]["title_cn"], "测试电影")


class TestCrashScrapeRecovery(unittest.TestCase):
    """Task with scrape_result can be re-processed from copy step."""

    def setUp(self):
        self.source_dir = tempfile.mkdtemp()
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)
        self.video_path = os.path.join(self.source_dir, "movie.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"fake_video" * 100)
        # Also create a temp copy to simulate file was copied before crash
        self.temp_video = os.path.join(self.temp_dir, "movie.mkv")
        with open(self.temp_video, "wb") as f:
            f.write(b"fake_video" * 100)

    def tearDown(self):
        shutil.rmtree(self.source_dir, ignore_errors=True)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_crash_scrape_recovery(self):
        # Create task that was mid-pipeline: copy done, scrape done, crash
        task = self.tm.create_task(
            video_path=self.video_path,
            video_file="movie.mkv",
            file_size_mb=0.01,
        )
        scrape_result = _make_scrape_result()

        db_update_task(
            self.tm.conn, task["task_id"],
            status=STATUS_PENDING,
            stage=STAGE_RUNNING,
            file_location=FILE_LOCATION_TEMP,
            video_path=self.temp_video,
            scrape_result=scrape_result,
            scrape_title_cn=scrape_result["title_cn"],
            scrape_title_en=scrape_result["title_en"],
            scrape_year=scrape_result["year"],
            scrape_media_type=scrape_result["type"],
            scrape_confidence=scrape_result["confidence"],
            scrape_dimensions=scrape_result["dimensions"],
        )

        # On restart: task is recoverable
        recovered = self.tm.get_task(task["task_id"])
        self.assertEqual(recovered["status"], STATUS_PENDING)
        self.assertEqual(recovered["stage"], STAGE_RUNNING)
        self.assertEqual(recovered["file_location"], FILE_LOCATION_TEMP)

        # Temp file still exists, so re-processing from scrape is possible
        self.assertTrue(os.path.isfile(self.temp_video))

        # Scrape result is available, so re-scrape is not strictly needed
        self.assertIn("title_cn", recovered["scrape_result"])

        # Reset task for re-processing (simulate retry logic)
        self.tm.update_task({
            "task_id": task["task_id"],
            "status": STATUS_PENDING,
            "stage": STAGE_QUEUED,
        })
        retried = self.tm.get_task(task["task_id"])
        self.assertEqual(retried["stage"], STAGE_QUEUED)


if __name__ == "__main__":
    unittest.main()
