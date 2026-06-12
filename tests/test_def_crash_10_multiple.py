#!/usr/bin/env python3
"""Crash recovery tests: multiple restarts.

Simulate multiple restarts at different stages and verify eventual completion.
"""
import os
import shutil
import tempfile
import unittest

from media_importer.core.task_manager import TaskManager
from media_importer.core.task_lifecycle import (
    FILE_LOCATION_SOURCE,
    FILE_LOCATION_TEMP,
    STAGE_AWAIT_REVIEW,
    STAGE_DONE,
    STAGE_QUEUED,
    STAGE_RUNNING,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SKIPPED,
    STATUS_SUCCESS,
    reset_for_retry,
)
from media_importer.core.db import update_task as db_update_task


def _make_scrape_result(title="测试电影"):
    return {
        "title_cn": title,
        "title_en": "Test Movie",
        "year": "2024",
        "type": "movie",
        "confidence": 0.9,
        "dimensions": {"media_type": "movie", "year": "2024"},
    }


class TestThreeRestarts(unittest.TestCase):
    """Kill at 3 different stages → task eventually completes."""

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_three_restarts(self):
        # Create a task
        task = self.tm.create_task(
            video_path="/source/movie.mkv",
            video_file="movie.mkv",
            file_size_mb=1.0,
        )
        tid = task["task_id"]

        # --- Restart 1: crash after copy ---
        db_update_task(self.tm.conn, tid,
                       status=STATUS_PENDING, stage=STAGE_RUNNING,
                       file_location=FILE_LOCATION_TEMP,
                       video_path="/temp/movie.mkv",
                       current_step=2, step_name="copy", percentage=30)

        # Simulate restart: reset task for re-processing
        recovered = self.tm.get_task(tid)
        db_update_task(self.tm.conn, tid, **reset_for_retry(recovered))
        t = self.tm.get_task(tid)
        self.assertEqual(t["stage"], STAGE_QUEUED)

        # --- Restart 2: crash after scrape ---
        db_update_task(self.tm.conn, tid,
                       status=STATUS_PENDING, stage=STAGE_RUNNING,
                       file_location=FILE_LOCATION_TEMP,
                       video_path="/temp/movie.mkv",
                       scrape_result=_make_scrape_result(),
                       current_step=3, step_name="scrape", percentage=50)

        # Simulate restart: reset task for re-processing
        recovered = self.tm.get_task(tid)
        db_update_task(self.tm.conn, tid, **reset_for_retry(recovered))
        t = self.tm.get_task(tid)
        self.assertEqual(t["stage"], STAGE_QUEUED)

        # --- Restart 3: crash after classify ---
        db_update_task(self.tm.conn, tid,
                       status=STATUS_PENDING, stage=STAGE_RUNNING,
                       file_location=FILE_LOCATION_TEMP,
                       video_path="/temp/movie.mkv",
                       scrape_result=_make_scrape_result(),
                       import_path="/import/movies/2024",
                       classify_result="media_type=movie",
                       current_step=5, step_name="classify", percentage=60)

        # Simulate restart: reset task for re-processing
        recovered = self.tm.get_task(tid)
        db_update_task(self.tm.conn, tid, **reset_for_retry(recovered))
        t = self.tm.get_task(tid)
        self.assertEqual(t["stage"], STAGE_QUEUED)

        # --- Final run: task completes successfully ---
        db_update_task(self.tm.conn, tid,
                       status=STATUS_SUCCESS, stage=STAGE_DONE,
                       file_location="import",
                       import_video_path="/import/movies/2024/movie.mkv",
                       import_success=1,
                       completed_at="2024-01-01T00:00:00")

        final = self.tm.get_task(tid)
        self.assertEqual(final["status"], STATUS_SUCCESS)
        self.assertEqual(final["stage"], STAGE_DONE)


class TestAllTasksReachTerminal(unittest.TestCase):
    """After multiple restarts, all tasks reach SUCCESS/FAILED/SKIPPED."""

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_all_tasks_reach_terminal(self):
        terminal_statuses = {STATUS_SUCCESS, STATUS_FAILED, STATUS_SKIPPED}

        # Create 5 tasks
        tasks = []
        for i in range(5):
            t = self.tm.create_task(
                video_path=f"/source/movie_{i}.mkv",
                video_file=f"movie_{i}.mkv",
                file_size_mb=1.0,
            )
            tasks.append(t)

        # Simulate various crash points and eventual terminal states
        # Task 0: succeeds on first try
        db_update_task(self.tm.conn, tasks[0]["task_id"],
                       status=STATUS_SUCCESS, stage=STAGE_DONE,
                       import_success=1)

        # Task 1: crashes once, then succeeds
        db_update_task(self.tm.conn, tasks[1]["task_id"],
                       status=STATUS_PENDING, stage=STAGE_RUNNING)
        recovered = self.tm.get_task(tasks[1]["task_id"])
        db_update_task(self.tm.conn, tasks[1]["task_id"],
                       **reset_for_retry(recovered))
        db_update_task(self.tm.conn, tasks[1]["task_id"],
                       status=STATUS_SUCCESS, stage=STAGE_DONE,
                       import_success=1)

        # Task 2: fails permanently
        db_update_task(self.tm.conn, tasks[2]["task_id"],
                       status=STATUS_FAILED, stage=STAGE_DONE,
                       error_message="刮削失败")

        # Task 3: skipped (duplicate)
        db_update_task(self.tm.conn, tasks[3]["task_id"],
                       status=STATUS_SKIPPED, stage=STAGE_DONE,
                       skip_reason="同名文件已存在")

        # Task 4: crashes twice, then fails
        db_update_task(self.tm.conn, tasks[4]["task_id"],
                       status=STATUS_PENDING, stage=STAGE_RUNNING)
        recovered = self.tm.get_task(tasks[4]["task_id"])
        db_update_task(self.tm.conn, tasks[4]["task_id"],
                       **reset_for_retry(recovered))
        db_update_task(self.tm.conn, tasks[4]["task_id"],
                       status=STATUS_PENDING, stage=STAGE_RUNNING)
        recovered = self.tm.get_task(tasks[4]["task_id"])
        db_update_task(self.tm.conn, tasks[4]["task_id"],
                       **reset_for_retry(recovered))
        db_update_task(self.tm.conn, tasks[4]["task_id"],
                       status=STATUS_FAILED, stage=STAGE_DONE,
                       error_message="重试次数过多")

        # Verify all tasks reached terminal state
        all_tasks = self.tm.list_all_tasks(limit=100)
        for t in all_tasks:
            self.assertIn(t["status"], terminal_statuses,
                          f"Task {t['task_id']} should be in terminal state, "
                          f"got {t['status']}/{t['stage']}")
            self.assertEqual(t["stage"], STAGE_DONE)

        # Count statuses
        counts = self.tm.count_by_status()
        self.assertEqual(counts.get(STATUS_SUCCESS, 0), 2)
        self.assertEqual(counts.get(STATUS_FAILED, 0), 2)
        self.assertEqual(counts.get(STATUS_SKIPPED, 0), 1)


if __name__ == "__main__":
    unittest.main()
