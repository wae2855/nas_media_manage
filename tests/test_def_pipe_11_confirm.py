#!/usr/bin/env python3
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from media_importer.features.import_flow.confirm import ConfirmMixin
from media_importer.features.import_flow.utils import PipelineError
from media_importer.features.tasks import (
    STAGE_AWAIT_REVIEW,
    STATUS_PENDING,
    STATUS_SUCCESS,
    STATUS_FAILED,
    mark_confirmed,
    mark_imported,
    mark_failed,
)
from media_importer.core.task_manager import TaskManager
from media_importer.core.db import update_task as db_update_task


def _make_config(source_dir=None, temp_dir=None, import_dir=None):
    source = source_dir or tempfile.mkdtemp()
    temp = temp_dir or tempfile.mkdtemp()
    imp = import_dir or tempfile.mkdtemp()
    return {
        "source_dir": source,
        "temp_dir": temp,
        "path_rules": [{"conditions": {}, "template": imp}],
        "video_extensions": [".mkv", ".mp4"],
        "subtitle_extensions": [".srt", ".ass"],
        "filename_templates": {
            "movie": "{title_cn}.{title_en}.{year}.{ext}",
            "tv": "{title_cn}.{title_en}.{year}.S{season}E{episode}.{ext}",
        },
        "source_policy": {
            "recycle_dir": tempfile.mkdtemp(),
            "cleanup_source_after_done": False,
        },
        "duplicate_handling": {"enabled": False, "strategy": "skip"},
        "manual_review": {"enabled": False},
    }


class _FakePipeline(ConfirmMixin):
    """Minimal pipeline-like object with ConfirmMixin for testing."""

    def __init__(self, config, task_manager):
        self.config = config
        self.task_manager = task_manager
        self.hooks = MagicMock()
        self.metrics = MagicMock()
        self._log = MagicMock()

    def _step_import_from_confirm(self, task, original_source_video,
                                   original_source_subs):
        task["import_video_path"] = os.path.join(
            self.config["path_rules"][0]["template"], "imported.mkv"
        )

    def _step_notify(self, task):
        pass

    def _step_record(self, task):
        self.task_manager.update_task(task)

    def _cleanup_temp_on_failure(self, task, temp_video_path):
        pass


class TestConfirmAwaitReview(unittest.TestCase):
    """Task in PENDING/AWAIT_REVIEW -> confirm -> SUCCESS."""

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)
        self.config = _make_config()

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_confirm_await_review(self):
        task = self.tm.create_task(
            video_path="/source/movie.mkv",
            video_file="movie.mkv",
        )
        # Set task to AWAIT_REVIEW stage
        db_update_task(self.tm.conn, task["task_id"],
                       status="PENDING", stage="AWAIT_REVIEW")
        task = self.tm.get_task(task["task_id"])

        pipeline = _FakePipeline(self.config, self.tm)
        with patch("media_importer.features.import_flow.confirm.db_update_task") as mock_db, \
             patch("media_importer.features.import_flow.confirm.db_update_subs"):
            # Let the real confirm flow run, but intercept DB writes
            mock_db.side_effect = lambda *a, **kw: None
            result = pipeline.confirm_task(task["task_id"])

        self.assertTrue(result)


class TestConfirmWrongStage(unittest.TestCase):
    """Task not in AWAIT_REVIEW -> confirm -> PipelineError."""

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)
        self.config = _make_config()

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_confirm_wrong_stage(self):
        task = self.tm.create_task(
            video_path="/source/movie.mkv",
            video_file="movie.mkv",
        )
        # Task is in QUEUED stage by default, not AWAIT_REVIEW
        task = self.tm.get_task(task["task_id"])

        pipeline = _FakePipeline(self.config, self.tm)
        with self.assertRaises(PipelineError) as ctx:
            pipeline.confirm_task(task["task_id"])
        self.assertIn("不可确认", str(ctx.exception))


class TestConfirmFailureCleanup(unittest.TestCase):
    """Confirm fails midway -> temp cleaned, task FAILED."""

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)
        self.config = _make_config()

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_confirm_failure_cleanup(self):
        task = self.tm.create_task(
            video_path="/source/movie.mkv",
            video_file="movie.mkv",
        )
        db_update_task(self.tm.conn, task["task_id"],
                       status="PENDING", stage="AWAIT_REVIEW")
        task = self.tm.get_task(task["task_id"])

        pipeline = _FakePipeline(self.config, self.tm)
        # Make import fail
        pipeline._step_import_from_confirm = MagicMock(
            side_effect=PipelineError("Import failed")
        )
        pipeline._cleanup_temp_on_failure = MagicMock()

        with patch("media_importer.features.import_flow.confirm.db_update_task") as mock_db, \
             patch("media_importer.features.import_flow.confirm.db_update_subs"):
            mock_db.side_effect = lambda *a, **kw: None
            result = pipeline.confirm_task(task["task_id"])

        self.assertFalse(result)
        pipeline._cleanup_temp_on_failure.assert_called_once()


class TestReclassifyTask(unittest.TestCase):
    """Reclassify with new dimensions -> re-classify -> new import_path."""

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.data_dir)
        self.config = _make_config()

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_reclassify_task(self):
        task = self.tm.create_task(
            video_path="/source/movie.mkv",
            video_file="movie.mkv",
        )
        db_update_task(
            self.tm.conn, task["task_id"],
            status="PENDING", stage="AWAIT_REVIEW",
            scrape_result='{"title_cn": "测试", "type": "movie"}',
            scrape_dimensions='{"media_type": "movie"}',
        )
        task = self.tm.get_task(task["task_id"])

        pipeline = _FakePipeline(self.config, self.tm)

        # Mock classification to return a new import path
        mock_classify_result = MagicMock()
        mock_classify_result.import_path = "/media/tv/Test"
        mock_classify_result.classify_result = "reclassified"
        mock_classify_result.used_fallback = False
        mock_classify_result.dimensions_text = "media_type=tv"

        with patch("media_importer.features.import_flow.confirm.ClassificationService") as MockClassSvc, \
             patch("media_importer.features.import_flow.confirm.get_enabled_dimensions",
                   return_value=[{"name": "media_type"}]), \
             patch("media_importer.features.import_flow.confirm.db_update_task") as mock_db, \
             patch("media_importer.features.import_flow.confirm.db_update_subs"):
            MockClassSvc.return_value.classify_task.return_value = mock_classify_result
            mock_db.side_effect = lambda *a, **kw: None

            # Mock the subsequent steps
            pipeline._step_dedup = MagicMock()
            pipeline._step_rename = MagicMock()
            pipeline._step_import = MagicMock()
            pipeline._step_notify = MagicMock()
            pipeline._step_record = MagicMock()

            result = pipeline.reclassify_task(task["task_id"], {"media_type": "tv"})

        # Verify classification was called with updated dimensions
        MockClassSvc.return_value.classify_task.assert_called_once()


if __name__ == "__main__":
    unittest.main()
