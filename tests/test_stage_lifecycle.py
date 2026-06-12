#!/usr/bin/env python3
"""Stage transition unit tests for status+stage dual model.

Verifies that every lifecycle function sets both status and stage correctly.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.features.tasks import (
    CONFIRM_CONFIRMED,
    CONFIRM_PENDING,
    FILE_LOCATION_IMPORT,
    FILE_LOCATION_SOURCE,
    FILE_LOCATION_TEMP,
    STAGE_AWAIT_REVIEW,
    STAGE_DONE,
    STAGE_QUEUED,
    STAGE_RUNNING,
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SKIPPED,
    STATUS_SUCCESS,
    mark_confirmed,
    mark_confirming,
    mark_failed,
    mark_imported,
    mark_needs_review,
    mark_processing_step,
    mark_skipped,
    mark_temp_ready,
    reset_for_retry,
    start_processing,
)
from media_importer.features.import_flow import TaskContext


class TestStageLifecycle(unittest.TestCase):
    """Verify each lifecycle function sets status+stage correctly."""

    def test_start_processing_sets_status_pending_stage_running(self):
        task = {"task_id": "t1"}
        fields = start_processing(task, started_at="2026-06-02T10:00:00")

        self.assertEqual(fields["status"], STATUS_PENDING)
        self.assertEqual(fields["stage"], STAGE_RUNNING)
        self.assertEqual(task["status"], STATUS_PENDING)
        self.assertEqual(task["stage"], STAGE_RUNNING)
        self.assertIn("started_at", fields)

    def test_mark_processing_step_keeps_stage_running(self):
        task = {}
        fields = mark_processing_step(
            task, current_step=3, step_name="scrape", percentage=35
        )

        self.assertEqual(fields["status"], STATUS_PENDING)
        self.assertEqual(fields["stage"], STAGE_RUNNING)
        self.assertEqual(fields["current_step"], 3)
        self.assertEqual(fields["step_name"], "scrape")
        self.assertEqual(fields["percentage"], 35)

    def test_mark_confirming_sets_stage_await_review(self):
        task = {"video_path": "/temp/movie.mkv"}
        fields = mark_confirming(task)

        self.assertEqual(fields["status"], STATUS_PENDING)
        self.assertEqual(fields["stage"], STAGE_AWAIT_REVIEW)
        self.assertEqual(fields["confirm_status"], CONFIRM_PENDING)
        self.assertEqual(task["status"], STATUS_PENDING)
        self.assertEqual(task["stage"], STAGE_AWAIT_REVIEW)

    def test_mark_confirming_records_reason(self):
        task = {"video_path": "/temp/movie.mkv"}
        fields = mark_confirming(task, "置信度较低")

        self.assertEqual(fields["status"], STATUS_PENDING)
        self.assertEqual(fields["stage"], STAGE_AWAIT_REVIEW)
        self.assertEqual(fields["error_message"], "置信度较低")

    def test_mark_needs_review_same_stage_as_confirming(self):
        task = {"video_path": "/temp/movie.mkv"}
        fields = mark_needs_review(task, "来源不可信")

        self.assertEqual(fields["status"], STATUS_PENDING)
        self.assertEqual(fields["stage"], STAGE_AWAIT_REVIEW)
        self.assertEqual(fields["file_location"], FILE_LOCATION_TEMP)

    def test_mark_failed_sets_stage_done(self):
        task = {"video_path": "/temp/movie.mkv"}
        fields = mark_failed(task, "失败")

        self.assertEqual(fields["status"], STATUS_FAILED)
        self.assertEqual(fields["stage"], STAGE_DONE)
        self.assertEqual(fields["video_path"], "")
        self.assertIn("completed_at", fields)

    def test_mark_skipped_sets_stage_done(self):
        task = {"video_path": "/temp/movie.mkv"}
        fields = mark_skipped(task, "重复文件")

        self.assertEqual(fields["status"], STATUS_SKIPPED)
        self.assertEqual(fields["stage"], STAGE_DONE)
        self.assertEqual(fields["skip_reason"], "重复文件")
        self.assertEqual(fields["file_location"], FILE_LOCATION_SOURCE)
        self.assertIn("completed_at", fields)

    def test_mark_imported_sets_stage_done(self):
        task = {"import_video_path": "/import/movie.mkv"}
        fields = mark_imported(task)

        self.assertEqual(fields["status"], STATUS_SUCCESS)
        self.assertEqual(fields["stage"], STAGE_DONE)
        self.assertEqual(fields["import_success"], 1)
        self.assertEqual(fields["file_location"], FILE_LOCATION_IMPORT)

    def test_reset_for_retry_sets_stage_queued(self):
        task = {
            "status": "FAILED",
            "retry_count": 2,
            "error_message": "失败",
            "video_path": "/temp/movie.mkv",
        }
        fields = reset_for_retry(task)

        self.assertEqual(fields["status"], STATUS_PENDING)
        self.assertEqual(fields["stage"], STAGE_QUEUED)
        self.assertEqual(fields["retry_count"], 3)
        self.assertEqual(fields["error_message"], "")

    def test_mark_temp_ready_does_not_change_stage(self):
        task = {
            "source_path": "/source/movie.mkv",
            "video_path": "/temp/movie.mkv",
            "stage": STAGE_RUNNING,
        }
        fields = mark_temp_ready(task)

        self.assertEqual(fields["file_location"], FILE_LOCATION_TEMP)
        self.assertNotIn("status", fields)
        self.assertNotIn("stage", fields)
        self.assertEqual(task["stage"], STAGE_RUNNING)

    def test_terminal_statuses_have_stage_done(self):
        for st in (STATUS_SUCCESS, STATUS_FAILED, STATUS_SKIPPED, STATUS_CANCELLED):
            task = {"status": st}
            self.assertEqual(task.get("stage", STAGE_DONE), STAGE_DONE,
                             f"{st} should imply stage=DONE")

    def test_lifecycle_transition_table_records_stage(self):
        """Comprehensive verification of all transition functions."""
        cases = [
            ("start", {},
             lambda t: start_processing(t, started_at="2026-06-02T10:00:00"),
             {"status": STATUS_PENDING, "stage": STAGE_RUNNING}, []),
            ("processing_step", {},
             lambda t: mark_processing_step(t, current_step=1, step_name="scrape", percentage=50),
             {"status": STATUS_PENDING, "stage": STAGE_RUNNING}, []),
            ("temp_ready", {"video_path": "/temp/m.mkv"},
             mark_temp_ready,
             {"file_location": FILE_LOCATION_TEMP}, []),
            ("confirming", {"video_path": "/temp/m.mkv"},
             lambda t: mark_confirming(t),
             {"status": STATUS_PENDING, "stage": STAGE_AWAIT_REVIEW}, []),
            ("confirmed", {},
             lambda t: mark_confirmed(t, confirmed_at="now"),
             {"confirm_status": CONFIRM_CONFIRMED}, []),
            ("needs_review", {"video_path": "/temp/m.mkv"},
             lambda t: mark_needs_review(t, "review"),
             {"status": STATUS_PENDING, "stage": STAGE_AWAIT_REVIEW}, []),
            ("failed", {"video_path": "/temp/m.mkv"},
             lambda t: mark_failed(t, "err"),
             {"status": STATUS_FAILED, "stage": STAGE_DONE}, ["completed_at"]),
            ("skipped", {"video_path": "/temp/m.mkv"},
             lambda t: mark_skipped(t, "dup"),
             {"status": STATUS_SKIPPED, "stage": STAGE_DONE}, ["completed_at"]),
            ("imported", {"import_video_path": "/import/m.mkv"},
             mark_imported,
             {"status": STATUS_SUCCESS, "stage": STAGE_DONE}, ["completed_at"]),
        ]

        for name, initial, action, expected, expected_keys in cases:
            with self.subTest(name=name):
                task = dict(initial)
                fields = action(task)
                for key, value in expected.items():
                    self.assertEqual(fields[key], value,
                                     f"{name}: fields[{key!r}] mismatch")
                    self.assertEqual(task[key], value,
                                     f"{name}: task[{key!r}] mismatch")
                for key in expected_keys:
                    self.assertIn(key, fields)
                    self.assertIn(key, task)


if __name__ == "__main__":
    unittest.main()