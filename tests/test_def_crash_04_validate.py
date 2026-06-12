#!/usr/bin/env python3
"""Crash recovery tests: validate stage.

Simulate crash after validate marks AWAIT_REVIEW or after validate proceeds.
"""
import os
import shutil
import tempfile
import unittest

from media_importer.core.task_manager import TaskManager
from media_importer.core.task_lifecycle import (
    CONFIRM_PENDING,
    FILE_LOCATION_TEMP,
    STAGE_AWAIT_REVIEW,
    STAGE_RUNNING,
    STATUS_PENDING,
)
from media_importer.core.db import update_task as db_update_task


def _make_scrape_result(title_cn="测试电影", confidence=0.9):
    return {
        "title_cn": title_cn,
        "title_en": "Test Movie",
        "year": "2024",
        "type": "movie",
        "confidence": confidence,
        "dimensions": {"media_type": "movie", "year": "2024"},
    }


class TestCrashAfterValidateConfirm(unittest.TestCase):
    """Task marked PENDING/AWAIT_REVIEW → survives restart."""

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

    def test_crash_after_validate_confirm(self):
        # Create task and advance to AWAIT_REVIEW (validate said "confirm")
        task = self.tm.create_task(
            video_path=self.video_path,
            video_file="movie.mkv",
            file_size_mb=0.01,
        )
        scrape_result = _make_scrape_result(confidence=0.3)

        # Simulate: validate marked task as AWAIT_REVIEW, then crash
        db_update_task(
            self.tm.conn, task["task_id"],
            status=STATUS_PENDING,
            stage=STAGE_AWAIT_REVIEW,
            confirm_status=CONFIRM_PENDING,
            file_location=FILE_LOCATION_TEMP,
            video_path=os.path.join(self.temp_dir, "movie.mkv"),
            scrape_result=scrape_result,
            scrape_title_cn=scrape_result["title_cn"],
            scrape_year=scrape_result["year"],
            scrape_media_type=scrape_result["type"],
            scrape_confidence=scrape_result["confidence"],
            error_message="刮削信息不足",
        )

        # On restart: task should still be PENDING/AWAIT_REVIEW
        recovered = self.tm.get_task(task["task_id"])
        self.assertEqual(recovered["status"], STATUS_PENDING)
        self.assertEqual(recovered["stage"], STAGE_AWAIT_REVIEW)
        self.assertEqual(recovered["confirm_status"], CONFIRM_PENDING)

        # The task is waiting for human confirmation, not lost
        self.assertIn("刮削信息不足", recovered.get("error_message", ""))


class TestCrashAfterValidateProceed(unittest.TestCase):
    """Task proceeding to classify → on restart, continues."""

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

    def test_crash_after_validate_proceed(self):
        # Create task where validate said "proceed" but crash before classify
        task = self.tm.create_task(
            video_path=self.video_path,
            video_file="movie.mkv",
            file_size_mb=0.01,
        )
        scrape_result = _make_scrape_result(confidence=0.9)

        # Simulate: validate passed, task still RUNNING, crash before classify
        db_update_task(
            self.tm.conn, task["task_id"],
            status=STATUS_PENDING,
            stage=STAGE_RUNNING,
            file_location=FILE_LOCATION_TEMP,
            video_path=os.path.join(self.temp_dir, "movie.mkv"),
            scrape_result=scrape_result,
            scrape_title_cn=scrape_result["title_cn"],
            scrape_year=scrape_result["year"],
            scrape_media_type=scrape_result["type"],
            scrape_confidence=scrape_result["confidence"],
            scrape_dimensions=scrape_result["dimensions"],
            current_step=4,
            step_name="validate",
            percentage=55,
        )

        # On restart: task is still PENDING/RUNNING
        recovered = self.tm.get_task(task["task_id"])
        self.assertEqual(recovered["status"], STATUS_PENDING)
        self.assertEqual(recovered["stage"], STAGE_RUNNING)
        self.assertEqual(recovered["current_step"], 4)
        self.assertEqual(recovered["step_name"], "validate")

        # The task can be re-processed: scrape_result is available
        self.assertIsNotNone(recovered["scrape_result"])
        self.assertEqual(recovered["scrape_result"]["confidence"], 0.9)

        # Reset for re-processing
        self.tm.update_task({
            "task_id": task["task_id"],
            "stage": STAGE_RUNNING,
        })
        final = self.tm.get_task(task["task_id"])
        self.assertEqual(final["stage"], STAGE_RUNNING)


if __name__ == "__main__":
    unittest.main()
