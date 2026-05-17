#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'media_importer'))

from task_manager import Task, TaskManager
from pipeline import PipelineRunner, PipelineError, PipelineSkipError
from metrics import Metrics


class TestCopyFailure(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "tasks.json")
        self.config = {
            "source_dir": os.path.join(self.temp_dir, "source"),
            "temp_dir": os.path.join(self.temp_dir, "temp"),
            "log_dir": os.path.join(self.temp_dir, "logs"),
            "path_rules": [{"conditions": {}, "template": os.path.join(self.temp_dir, "import/{title_cn}/")}],
            "filename_templates": {"movie": "{title_cn}.{ext}", "tv": "{title_cn}.S{season:02d}E{episode:02d}.{ext}"},
            "duplicate_handling": {"strategy": "skip"},
            "hooks": {},
            "llm": {"api_key": "test", "base_url": "http://localhost", "model": "test", "timeout": 5, "max_retries": 0},
            "dimensions": [],
            "logging": {"level": "DEBUG", "format": "text"},
        }
        os.makedirs(self.config["source_dir"], exist_ok=True)
        os.makedirs(self.config["temp_dir"], exist_ok=True)
        os.makedirs(self.config["log_dir"], exist_ok=True)
        self.task_manager = TaskManager(self.db_path, self.config)
        self.metrics = Metrics()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("pipeline.FileCopier")
    @patch("pipeline.LLMScraper")
    def test_copy_ioerror_marks_task_failed(self, MockScraper, MockCopier):
        MockCopier.return_value.copy_to_temp.side_effect = IOError("No space left on device")

        runner = PipelineRunner(
            config=self.config,
            task_manager=self.task_manager,
            metrics=self.metrics
        )

        task = self.task_manager.create_task(
            video_path="/fake/test.mkv",
            video_file="test.mkv"
        )

        result = runner.process_one(task)
        self.assertFalse(result)

        updated = self.task_manager.get_task(task.task_id)
        self.assertEqual(updated.status, "FAILED")
        self.assertIn("复制失败", updated.error_message)

    @patch("pipeline.FileCopier")
    @patch("pipeline.LLMScraper")
    def test_llm_failure_marks_task_failed(self, MockScraper, MockCopier):
        from llm_scraper import LLMScrapeError
        MockCopier.return_value.copy_to_temp.return_value = ["/fake/temp/test.mkv"]
        MockScraper.return_value.scrape.side_effect = LLMScrapeError("API timeout")

        runner = PipelineRunner(
            config=self.config,
            task_manager=self.task_manager,
            metrics=self.metrics
        )

        task = self.task_manager.create_task(
            video_path="/fake/test.mkv",
            video_file="test.mkv"
        )

        result = runner.process_one(task)
        self.assertFalse(result)

        updated = self.task_manager.get_task(task.task_id)
        self.assertEqual(updated.status, "FAILED")
        self.assertIn("刮削失败", updated.error_message)

    @patch("pipeline.FileCopier")
    @patch("pipeline.LLMScraper")
    @patch("pipeline.check_duplicate")
    @patch("pipeline.classify")
    def test_duplicate_skip_marks_task_skipped(self, MockClassify, MockDedup, MockScraper, MockCopier):
        MockCopier.return_value.copy_to_temp.return_value = ["/fake/temp/test.mkv"]
        MockScraper.return_value.scrape.return_value = {"type": "movie", "title_cn": "测试"}
        MockClassify.return_value = "/fake/import/"
        MockDedup.return_value = {"is_duplicate": True, "existing_file": "/fake/existing.mkv"}

        runner = PipelineRunner(
            config=self.config,
            task_manager=self.task_manager,
            metrics=self.metrics
        )

        task = self.task_manager.create_task(
            video_path="/fake/test.mkv",
            video_file="test.mkv"
        )

        result = runner.process_one(task)
        self.assertTrue(result)

        updated = self.task_manager.get_task(task.task_id)
        self.assertEqual(updated.status, "SKIPPED")
        self.assertIn("同名文件", updated.error_message)

    @patch("pipeline.FileCopier")
    @patch("pipeline.LLMScraper")
    @patch("pipeline.classify")
    def test_classify_no_match_marks_task_failed(self, MockClassify, MockScraper, MockCopier):
        MockCopier.return_value.copy_to_temp.return_value = ["/fake/temp/test.mkv"]
        MockScraper.return_value.scrape.return_value = {"type": "movie", "title_cn": "测试"}
        MockClassify.return_value = ""

        runner = PipelineRunner(
            config=self.config,
            task_manager=self.task_manager,
            metrics=self.metrics
        )

        task = self.task_manager.create_task(
            video_path="/fake/test.mkv",
            video_file="test.mkv"
        )

        result = runner.process_one(task)
        self.assertFalse(result)

        updated = self.task_manager.get_task(task.task_id)
        self.assertEqual(updated.status, "FAILED")
        self.assertIn("分类匹配失败", updated.error_message)

    def test_task_retry_from_failed(self):
        task = self.task_manager.create_task(
            video_path="/fake/test.mkv",
            video_file="test.mkv"
        )
        task.transition_to("PROCESSING")
        task.transition_to("FAILED")
        task.error_message = "some error"
        self.task_manager.update_task(task)

        retried = self.task_manager.retry_task(task.task_id)
        self.assertEqual(retried.status, "PENDING")
        self.assertEqual(retried.retry_count, 1)
        self.assertEqual(retried.error_message, "")

    def test_task_cannot_transition_invalid(self):
        task = self.task_manager.create_task(
            video_path="/fake/test.mkv",
            video_file="test.mkv"
        )
        with self.assertRaises(ValueError):
            task.transition_to("SUCCESS")


class TestConfigCompatibility(unittest.TestCase):
    def test_minimal_config(self):
        config = {
            "source_dir": "/tmp",
            "temp_dir": "/tmp",
            "log_dir": "/tmp",
            "llm": {"api_key": "test"},
        }
        tm = TaskManager(os.path.join(tempfile.mkdtemp(), "tasks.json"), config)
        self.assertIsNotNone(tm)

    def test_missing_optional_sections(self):
        config = {
            "source_dir": "/tmp",
            "temp_dir": "/tmp",
            "log_dir": "/tmp",
            "llm": {"api_key": "test"},
        }
        from hooks import HookRunner
        runner = HookRunner(config)
        self.assertEqual(runner.before_process, "")

    def test_empty_config(self):
        config = {}
        from hooks import HookRunner
        runner = HookRunner(config)
        self.assertTrue(runner.run_before_process({}))


if __name__ == "__main__":
    unittest.main()
