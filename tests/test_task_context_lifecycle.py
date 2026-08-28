#!/usr/bin/env python3
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.features.import_flow import TaskContext
from media_importer.features.tasks import (
    CONFIRM_CONFIRMED,
    CONFIRM_PENDING,
    FILE_LOCATION_IMPORT,
    FILE_LOCATION_SOURCE,
    FILE_LOCATION_TEMP,
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


class TestTaskContext(unittest.TestCase):
    def test_context_reads_current_paths_from_existing_dict(self):
        task = {
            "task_id": "t1",
            "source_path": "/source/movie.mkv",
            "video_path": "",
            "subtitle_files": ["/source/movie.srt"],
            "file_location": "source",
        }
        ctx = TaskContext(task)

        self.assertEqual(ctx.task_id, "t1")
        self.assertEqual(ctx.source_path, "/source/movie.mkv")
        self.assertEqual(ctx.current_video_path, "/source/movie.mkv")
        self.assertEqual(ctx.subtitle_files, ["/source/movie.srt"])
        self.assertEqual(ctx.file_location, "source")

    def test_mark_temp_updates_raw_task_dict(self):
        task = {"task_id": "t1", "source_path": "/source/movie.mkv"}
        ctx = TaskContext(task)

        ctx.mark_temp("/temp/movie.mkv", ["/temp/movie.srt"])

        self.assertEqual(task["video_path"], "/temp/movie.mkv")
        self.assertEqual(task["subtitle_files"], ["/temp/movie.srt"])
        self.assertEqual(ctx.current_video_path, "/temp/movie.mkv")

    def test_mark_scraped_sets_common_scrape_fields(self):
        task = {"task_id": "t1"}
        ctx = TaskContext(task)

        ctx.mark_scraped({
            "title_cn": "盗梦空间",
            "title_en": "Inception",
            "year": "2010",
            "media_type": "movie",
            "season": None,
            "episode": None,
            "dimensions": {"media_type": "movie"},
        })

        self.assertEqual(task["scrape_title_cn"], "盗梦空间")
        self.assertEqual(task["scrape_title_en"], "Inception")
        self.assertEqual(task["scrape_year"], "2010")
        self.assertEqual(task["scrape_media_type"], "movie")
        self.assertEqual(task["scrape_dimensions"], {"media_type": "movie"})

    def test_to_update_fields_returns_selected_fields_only(self):
        task = {"task_id": "t1", "status": "PENDING", "unknown": "x"}
        ctx = TaskContext(task)

        fields = ctx.to_update_fields("status", "missing")

        self.assertEqual(fields, {"status": "PENDING"})


class TestTaskLifecycle(unittest.TestCase):
    def test_lifecycle_transition_table_records_core_contract(self):
        cases = [
            (
                "start",
                {"status": "PENDING", "stage": "QUEUED"},
                lambda task: start_processing(task, started_at="2026-06-02T10:00:00"),
                {"status": STATUS_PENDING, "started_at": "2026-06-02T10:00:00"},
                [],
            ),
            (
                "processing_step",
                {"status": "PENDING", "stage": "RUNNING"},
                lambda task: mark_processing_step(
                    task, current_step=3, step_name="scrape", percentage=35
                ),
                {
                    "status": STATUS_PENDING,
                    "current_step": 3,
                    "step_name": "scrape",
                    "percentage": 35,
                },
                [],
            ),
            (
                "temp_ready",
                {"video_path": "/temp/movie.mkv", "status": "PENDING", "stage": "RUNNING"},
                mark_temp_ready,
                {"file_location": FILE_LOCATION_TEMP, "video_path": "/temp/movie.mkv"},
                [],
            ),
            (
                "confirming",
                {"video_path": "/temp/movie.mkv", "status": "PENDING", "stage": "RUNNING"},
                lambda task: mark_confirming(task, "needs confirm"),
                {
                    "status": STATUS_PENDING,
                    "confirm_status": CONFIRM_PENDING,
                    "file_location": FILE_LOCATION_TEMP,
                    "video_path": "/temp/movie.mkv",
                    "error_message": "needs confirm",
                },
                [],
            ),
            (
                "confirmed",
                {"status": "PENDING", "stage": "AWAIT_REVIEW"},
                lambda task: mark_confirmed(task, confirmed_at="2026-06-02T10:01:00"),
                {
                    "confirm_status": CONFIRM_CONFIRMED,
                    "confirmed_at": "2026-06-02T10:01:00",
                },
                [],
            ),
            (
                "needs_review",
                {"video_path": "/temp/movie.mkv", "status": "PENDING", "stage": "RUNNING"},
                lambda task: mark_needs_review(task, "manual review"),
                {
                    "status": STATUS_PENDING,
                    "file_location": FILE_LOCATION_TEMP,
                    "video_path": "/temp/movie.mkv",
                    "error_message": "manual review",
                },
                [],
            ),
            (
                "failed",
                {"video_path": "/temp/movie.mkv", "status": "PENDING", "stage": "RUNNING"},
                lambda task: mark_failed(task, "failed", video_path=""),
                {
                    "status": STATUS_FAILED,
                    "file_location": FILE_LOCATION_SOURCE,
                    "video_path": "",
                    "error_message": "failed",
                },
                ["completed_at"],
            ),
            (
                "skipped",
                {"video_path": "/temp/movie.mkv", "status": "PENDING", "stage": "RUNNING"},
                lambda task: mark_skipped(task, "duplicate"),
                {
                    "status": STATUS_SKIPPED,
                    "file_location": FILE_LOCATION_SOURCE,
                    "video_path": "",
                    "skip_reason": "duplicate",
                },
                ["completed_at"],
            ),
            (
                "imported",
                {"import_video_path": "/import/movie.mkv", "status": "PENDING", "stage": "RUNNING"},
                mark_imported,
                {
                    "status": STATUS_SUCCESS,
                    "file_location": FILE_LOCATION_IMPORT,
                    "import_success": 1,
                    "import_video_path": "/import/movie.mkv",
                },
                ["completed_at"],
            ),
        ]

        for name, initial, action, expected, expected_keys in cases:
            with self.subTest(name=name):
                task = dict(initial)
                fields = action(task)

                for key, value in expected.items():
                    self.assertEqual(fields[key], value)
                    self.assertEqual(task[key], value)
                for key in expected_keys:
                    self.assertIn(key, fields)
                    self.assertIn(key, task)

    def test_start_processing_sets_status_and_started_at(self):
        task = {"task_id": "t1", "status": "PENDING", "stage": "QUEUED"}

        fields = start_processing(task, started_at="2026-05-31T10:00:00")

        self.assertEqual(fields["status"], STATUS_PENDING)
        self.assertEqual(fields["started_at"], "2026-05-31T10:00:00")
        self.assertEqual(task["status"], STATUS_PENDING)

    def test_mark_temp_ready_tracks_current_temp_video(self):
        task = {"source_path": "/source/movie.mkv", "video_path": "/temp/movie.mkv", "status": "PENDING", "stage": "RUNNING"}

        fields = mark_temp_ready(task)

        self.assertEqual(fields["file_location"], FILE_LOCATION_TEMP)
        self.assertEqual(fields["video_path"], "/temp/movie.mkv")
        self.assertEqual(task["file_location"], FILE_LOCATION_TEMP)

    def test_mark_confirming_can_preserve_error_message_when_no_reason(self):
        task = {"video_path": "/temp/movie.mkv", "error_message": "old", "status": "PENDING", "stage": "RUNNING"}

        fields = mark_confirming(task)

        self.assertEqual(fields["status"], STATUS_PENDING)
        self.assertEqual(fields["confirm_status"], "PENDING")
        self.assertNotIn("error_message", fields)
        self.assertEqual(task["error_message"], "old")

    def test_mark_confirming_records_reason_when_provided(self):
        task = {"video_path": "/temp/movie.mkv", "status": "PENDING", "stage": "RUNNING"}

        fields = mark_confirming(task, "需要人工确认")

        self.assertEqual(fields["status"], STATUS_PENDING)
        self.assertEqual(fields["error_message"], "需要人工确认")

    def test_mark_needs_review_records_temp_location(self):
        task = {"video_path": "/temp/movie.mkv", "status": "PENDING", "stage": "RUNNING"}

        fields = mark_needs_review(task, "来源不可信")

        self.assertEqual(fields["status"], "PENDING")
        self.assertEqual(fields["file_location"], FILE_LOCATION_TEMP)
        self.assertEqual(fields["video_path"], "/temp/movie.mkv")

    def test_mark_failed_video_path_semantics(self):
        """S1 语义：缺省=保留不动（供失败清理读取）；显式 ""=清空。"""
        keep_task = {"video_path": "/temp/movie.mkv", "status": "PENDING", "stage": "RUNNING"}
        clear_task = {"video_path": "/temp/movie.mkv", "status": "PENDING", "stage": "RUNNING"}

        keep_fields = mark_failed(keep_task, "失败")
        clear_fields = mark_failed(clear_task, "失败", video_path="")

        self.assertEqual(keep_fields["status"], STATUS_FAILED)
        self.assertNotIn("video_path", keep_fields)          # 缺省保留：不写该字段
        self.assertEqual(keep_task["video_path"], "/temp/movie.mkv")
        self.assertEqual(clear_fields["video_path"], "")     # 显式清空

    def test_mark_skipped_records_completion_and_location(self):
        task = {"video_path": "/temp/movie.mkv", "status": "PENDING", "stage": "RUNNING"}

        fields = mark_skipped(task, "重复文件")

        self.assertEqual(fields["status"], STATUS_SKIPPED)
        self.assertEqual(fields["skip_reason"], "重复文件")
        self.assertEqual(fields["file_location"], FILE_LOCATION_SOURCE)
        self.assertEqual(fields["video_path"], "")
        self.assertIn("completed_at", fields)

    def test_mark_imported_records_success_fields(self):
        task = {"import_video_path": "/import/movie.mkv", "status": "PENDING", "stage": "RUNNING"}

        fields = mark_imported(task)

        self.assertEqual(fields["status"], STATUS_SUCCESS)
        self.assertEqual(fields["import_success"], 1)
        self.assertEqual(fields["file_location"], FILE_LOCATION_IMPORT)
        self.assertEqual(fields["import_video_path"], "/import/movie.mkv")

    def test_reset_for_retry_resets_runtime_fields(self):
        task = {
            "status": "FAILED",
            "stage": "DONE",
            "retry_count": 2,
            "error_message": "失败",
            "video_path": "/temp/movie.mkv",
            "import_path": "/import",
            "file_location": "temp",
        }

        fields = reset_for_retry(task)

        self.assertEqual(fields["status"], STATUS_PENDING)
        self.assertEqual(fields["retry_count"], 3)
        self.assertEqual(fields["error_message"], "")
        self.assertEqual(fields["video_path"], "")
        self.assertEqual(fields["import_path"], "")
        self.assertEqual(fields["file_location"], FILE_LOCATION_SOURCE)


if __name__ == "__main__":
    unittest.main()
