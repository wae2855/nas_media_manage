#!/usr/bin/env python3
"""Crash recovery tests: import stage.

Simulate crash during import and verify partial state handling.
"""
import os
import shutil
import tempfile
import unittest

from media_importer.core.task_manager import TaskManager
from media_importer.core.task_lifecycle import (
    FILE_LOCATION_IMPORT,
    FILE_LOCATION_TEMP,
    STAGE_RUNNING,
    STATUS_PENDING,
)
from media_importer.core.db import update_task as db_update_task
from media_importer.infrastructure.filesystem import safe_move


def _make_scrape_result():
    return {
        "title_cn": "测试电影",
        "title_en": "Test Movie",
        "year": "2024",
        "type": "movie",
        "confidence": 0.9,
        "dimensions": {"media_type": "movie", "year": "2024"},
    }


class TestCrashImportPartial(unittest.TestCase):
    """Video moved but subtitle not → inconsistency."""

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
        self.temp_sub = os.path.join(self.temp_dir, "movie.srt")
        with open(self.temp_sub, "wb") as f:
            f.write(b"subtitle content")

    def tearDown(self):
        shutil.rmtree(self.source_dir, ignore_errors=True)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.data_dir, ignore_errors=True)
        shutil.rmtree(self.import_dir, ignore_errors=True)

    def test_crash_import_partial(self):
        # Create task with video + subtitle
        task = self.tm.create_task(
            video_path=self.video_path,
            video_file="movie.mkv",
            subtitle_files=[self.temp_sub],
            file_size_mb=0.01,
        )

        # Simulate: video moved to import dir, but subtitle move not yet done
        # (crash between video move and subtitle move)
        dest_video = os.path.join(self.import_dir, "测试电影.Test Movie.2024.mkv")
        os.makedirs(self.import_dir, exist_ok=True)
        ok, msg = safe_move(self.temp_video, dest_video)
        self.assertTrue(ok, f"Video move should succeed: {msg}")

        # Video is in import dir, subtitle still in temp
        self.assertTrue(os.path.isfile(dest_video))
        self.assertTrue(os.path.isfile(self.temp_sub))

        # Task state: still RUNNING (crash before completion)
        db_update_task(
            self.tm.conn, task["task_id"],
            status=STATUS_PENDING,
            stage=STAGE_RUNNING,
            file_location=FILE_LOCATION_TEMP,
            video_path=self.temp_video,
            import_path=self.import_dir,
            current_step=8,
            step_name="import",
            percentage=85,
        )

        # On restart: detect inconsistency
        recovered = self.tm.get_task(task["task_id"])
        self.assertEqual(recovered["status"], STATUS_PENDING)
        self.assertEqual(recovered["stage"], STAGE_RUNNING)

        # Video is in target but temp video no longer exists
        self.assertFalse(os.path.isfile(self.temp_video))
        self.assertTrue(os.path.isfile(dest_video))

        # Subtitle is still in temp
        self.assertTrue(os.path.isfile(self.temp_sub))


class TestCrashImportVideoOnly(unittest.TestCase):
    """Video in target, subtitle in temp → detect and retry."""

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
        self.temp_sub = os.path.join(self.temp_dir, "movie.srt")
        with open(self.temp_sub, "wb") as f:
            f.write(b"subtitle content")

    def tearDown(self):
        shutil.rmtree(self.source_dir, ignore_errors=True)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.data_dir, ignore_errors=True)
        shutil.rmtree(self.import_dir, ignore_errors=True)

    def test_crash_import_video_only(self):
        # Create task with video + subtitle
        task = self.tm.create_task(
            video_path=self.video_path,
            video_file="movie.mkv",
            subtitle_files=[self.temp_sub],
            file_size_mb=0.01,
        )

        # Simulate: video moved to target, subtitle still in temp
        dest_video = os.path.join(self.import_dir, "测试电影.Test Movie.2024.mkv")
        os.makedirs(self.import_dir, exist_ok=True)
        ok, msg = safe_move(self.temp_video, dest_video)
        self.assertTrue(ok, f"Video move should succeed: {msg}")

        # Task state reflects partial import
        db_update_task(
            self.tm.conn, task["task_id"],
            status=STATUS_PENDING,
            stage=STAGE_RUNNING,
            file_location=FILE_LOCATION_IMPORT,
            video_path=dest_video,
            import_path=self.import_dir,
            import_video_path=dest_video,
            import_success=1,
            current_step=8,
            step_name="import",
            percentage=85,
        )

        # On restart: detect that video is in target but subtitle is in temp
        recovered = self.tm.get_task(task["task_id"])
        self.assertEqual(recovered["status"], STATUS_PENDING)

        # Video is in import dir
        self.assertTrue(os.path.isfile(dest_video))

        # Subtitle is still in temp, needs to be moved
        self.assertTrue(os.path.isfile(self.temp_sub))

        # Recovery: move subtitle to import dir
        dest_sub = os.path.join(self.import_dir, "测试电影.Test Movie.2024.chs.srt")
        ok, msg = safe_move(self.temp_sub, dest_sub)
        self.assertTrue(ok, f"Subtitle move should succeed: {msg}")
        self.assertFalse(os.path.isfile(self.temp_sub))
        self.assertTrue(os.path.isfile(dest_sub))


if __name__ == "__main__":
    unittest.main()
