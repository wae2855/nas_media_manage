#!/usr/bin/env python3
import unittest
import os
import sys
import tempfile
import shutil
import json
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'media_importer'))

from task_manager import Task, TaskManager, VALID_STATUSES, STATUS_TRANSITIONS
from pipeline import PipelineRunner, PipelineError, PipelineSkipError, PIPELINE_STEPS


class TestTask(unittest.TestCase):

    def test_task_default_values(self):
        task = Task()
        self.assertTrue(len(task.task_id) > 0)
        self.assertEqual(task.status, "PENDING")
        self.assertTrue(task.created_at)
        self.assertEqual(task.current_step, 0)
        self.assertEqual(task.total_steps, 9)

    def test_task_auto_generate_id(self):
        task1 = Task()
        task2 = Task()
        self.assertNotEqual(task1.task_id, task2.task_id)

    def test_task_custom_id(self):
        task = Task(task_id="custom-id")
        self.assertEqual(task.task_id, "custom-id")

    def test_task_to_dict(self):
        task = Task(task_id="test-123", video_file="movie.mkv")
        d = task.to_dict()
        self.assertEqual(d['task_id'], "test-123")
        self.assertEqual(d['video_file'], "movie.mkv")
        self.assertEqual(d['status'], "PENDING")

    def test_task_from_dict(self):
        data = {
            'task_id': 'test-456',
            'video_file': 'test.mkv',
            'video_path': '/path/to/test.mkv',
            'file_size_mb': 100.0,
            'subtitle_files': [],
            'scraped_info': {},
            'import_path': '',
            'final_filename': '',
            'status': 'PENDING',
            'created_at': '2024-01-01T00:00:00',
            'started_at': '',
            'completed_at': '',
            'error_code': 0,
            'error_message': '',
            'retry_count': 0,
            'logs': [],
            'current_step': 0,
            'total_steps': 9,
            'step_name': '',
            'percentage': 0,
            'bytes_copied': 0,
            'total_bytes': 0
        }
        task = Task.from_dict(data)
        self.assertEqual(task.task_id, 'test-456')
        self.assertEqual(task.video_file, 'test.mkv')

    def test_task_roundtrip(self):
        task = Task(task_id="roundtrip", video_file="test.mkv", file_size_mb=50.0)
        d = task.to_dict()
        restored = Task.from_dict(d)
        self.assertEqual(restored.task_id, task.task_id)
        self.assertEqual(restored.video_file, task.video_file)
        self.assertEqual(restored.file_size_mb, task.file_size_mb)

    def test_can_transition_pending_to_processing(self):
        task = Task()
        self.assertTrue(task.can_transition_to("PROCESSING"))

    def test_can_transition_pending_to_skipped(self):
        task = Task()
        self.assertTrue(task.can_transition_to("SKIPPED"))

    def test_cannot_transition_pending_to_success(self):
        task = Task()
        self.assertFalse(task.can_transition_to("SUCCESS"))

    def test_can_transition_processing_to_success(self):
        task = Task()
        task.status = "PROCESSING"
        self.assertTrue(task.can_transition_to("SUCCESS"))

    def test_can_transition_processing_to_failed(self):
        task = Task()
        task.status = "PROCESSING"
        self.assertTrue(task.can_transition_to("FAILED"))

    def test_cannot_transition_success_to_anything(self):
        task = Task()
        task.status = "SUCCESS"
        self.assertFalse(task.can_transition_to("PROCESSING"))
        self.assertFalse(task.can_transition_to("FAILED"))

    def test_can_transition_failed_to_pending(self):
        task = Task()
        task.status = "FAILED"
        self.assertTrue(task.can_transition_to("PENDING"))

    def test_transition_to_sets_started_at(self):
        task = Task()
        task.transition_to("PROCESSING")
        self.assertTrue(task.started_at)
        self.assertEqual(task.status, "PROCESSING")

    def test_transition_to_sets_completed_at(self):
        task = Task()
        task.status = "PROCESSING"
        task.transition_to("SUCCESS")
        self.assertTrue(task.completed_at)
        self.assertEqual(task.status, "SUCCESS")

    def test_invalid_transition_raises(self):
        task = Task()
        with self.assertRaises(ValueError):
            task.transition_to("SUCCESS")

    def test_add_log(self):
        task = Task()
        task.add_log("scrape", "INFO", "开始刮削")
        self.assertEqual(len(task.logs), 1)
        self.assertEqual(task.logs[0]['step'], "scrape")
        self.assertEqual(task.logs[0]['level'], "INFO")
        self.assertEqual(task.logs[0]['message'], "开始刮削")


class TestTaskManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'tasks.json')
        self.manager = TaskManager(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_task(self):
        task = self.manager.create_task("/path/to/video.mkv", "video.mkv")
        self.assertIsNotNone(task)
        self.assertEqual(task.video_file, "video.mkv")
        self.assertEqual(task.status, "PENDING")

    def test_get_task(self):
        task = self.manager.create_task("/path/to/video.mkv", "video.mkv")
        retrieved = self.manager.get_task(task.task_id)
        self.assertEqual(retrieved.task_id, task.task_id)

    def test_get_task_not_found(self):
        result = self.manager.get_task("nonexistent")
        self.assertIsNone(result)

    def test_get_next_pending(self):
        task1 = self.manager.create_task("/path/a.mkv", "a.mkv")
        task2 = self.manager.create_task("/path/b.mkv", "b.mkv")
        next_task = self.manager.get_next_pending()
        self.assertEqual(next_task.task_id, task1.task_id)

    def test_get_next_pending_none(self):
        task = self.manager.create_task("/path/a.mkv", "a.mkv")
        task.status = "PROCESSING"
        self.manager.update_task(task)
        self.assertIsNone(self.manager.get_next_pending())

    def test_update_task(self):
        task = self.manager.create_task("/path/video.mkv", "video.mkv")
        task.status = "PROCESSING"
        self.manager.update_task(task)
        retrieved = self.manager.get_task(task.task_id)
        self.assertEqual(retrieved.status, "PROCESSING")

    def test_update_progress(self):
        task = self.manager.create_task("/path/video.mkv", "video.mkv")
        self.manager.update_progress(task, 3, "scrape", 50)
        retrieved = self.manager.get_task(task.task_id)
        self.assertEqual(retrieved.current_step, 3)
        self.assertEqual(retrieved.step_name, "scrape")
        self.assertEqual(retrieved.percentage, 50)

    def test_list_tasks(self):
        self.manager.create_task("/path/a.mkv", "a.mkv")
        self.manager.create_task("/path/b.mkv", "b.mkv")
        tasks = self.manager.list_tasks()
        self.assertEqual(len(tasks), 2)

    def test_list_tasks_by_status(self):
        task1 = self.manager.create_task("/path/a.mkv", "a.mkv")
        task2 = self.manager.create_task("/path/b.mkv", "b.mkv")
        task1.status = "PROCESSING"
        self.manager.update_task(task1)
        pending = self.manager.list_tasks(status="PENDING")
        self.assertEqual(len(pending), 1)

    def test_list_tasks_limit(self):
        for i in range(5):
            self.manager.create_task(f"/path/{i}.mkv", f"{i}.mkv")
        tasks = self.manager.list_tasks(limit=3)
        self.assertEqual(len(tasks), 3)

    def test_retry_task(self):
        task = self.manager.create_task("/path/video.mkv", "video.mkv")
        task.status = "FAILED"
        self.manager.update_task(task)
        retried = self.manager.retry_task(task.task_id)
        self.assertEqual(retried.status, "PENDING")
        self.assertEqual(retried.retry_count, 1)

    def test_retry_task_not_failed(self):
        task = self.manager.create_task("/path/video.mkv", "video.mkv")
        retried = self.manager.retry_task(task.task_id)
        self.assertEqual(retried.status, "PENDING")
        self.assertEqual(retried.retry_count, 0)

    def test_retry_all_failed(self):
        task1 = self.manager.create_task("/path/a.mkv", "a.mkv")
        task2 = self.manager.create_task("/path/b.mkv", "b.mkv")
        task1.status = "FAILED"
        task2.status = "FAILED"
        self.manager.update_task(task1)
        self.manager.update_task(task2)
        retried = self.manager.retry_all_failed()
        self.assertEqual(len(retried), 2)

    def test_clear_tasks_by_status(self):
        task1 = self.manager.create_task("/path/a.mkv", "a.mkv")
        task2 = self.manager.create_task("/path/b.mkv", "b.mkv")
        task1.status = "SUCCESS"
        self.manager.update_task(task1)
        self.manager.clear_tasks("SUCCESS")
        tasks = self.manager.list_tasks()
        self.assertEqual(len(tasks), 1)

    def test_clear_all_tasks(self):
        self.manager.create_task("/path/a.mkv", "a.mkv")
        self.manager.create_task("/path/b.mkv", "b.mkv")
        self.manager.clear_tasks()
        tasks = self.manager.list_tasks()
        self.assertEqual(len(tasks), 0)

    def test_persistence(self):
        task = self.manager.create_task("/path/video.mkv", "video.mkv")
        task.status = "PROCESSING"
        self.manager.update_task(task)

        manager2 = TaskManager(self.db_path)
        retrieved = manager2.get_task(task.task_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.status, "PROCESSING")

    def test_count_by_status(self):
        task1 = self.manager.create_task("/path/a.mkv", "a.mkv")
        task2 = self.manager.create_task("/path/b.mkv", "b.mkv")
        task1.status = "PROCESSING"
        self.manager.update_task(task1)
        counts = self.manager.count_by_status()
        self.assertEqual(counts["PENDING"], 1)
        self.assertEqual(counts["PROCESSING"], 1)


class TestPipelineRunner(unittest.TestCase):

    def test_pipeline_steps_count(self):
        self.assertEqual(len(PIPELINE_STEPS), 9)

    def test_pipeline_steps_order(self):
        step_names = [s[1] for s in PIPELINE_STEPS]
        self.assertEqual(step_names, [
            "scan", "copy", "scrape", "classify", "dedup",
            "rename", "import", "notify", "record"
        ])

    def test_pipeline_error_exception(self):
        error = PipelineError("test error")
        self.assertEqual(str(error), "test error")

    def test_pipeline_skip_error_exception(self):
        error = PipelineSkipError("skip reason")
        self.assertEqual(str(error), "skip reason")

    def test_pause_resume(self):
        config = {
            'source_dir': '/tmp',
            'temp_dir': '/tmp',
            'llm': {'api_key': 'test', 'base_url': '', 'model': 'test',
                     'timeout': 30, 'max_retries': 1, 'retry_delay': 0,
                     'fallback_model': None, 'confidence_threshold': 0.8},
            'dimensions': []
        }
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, 'tasks.json')
        tm = TaskManager(db_path)
        runner = PipelineRunner(config, tm)

        self.assertFalse(runner.is_paused())
        runner.pause()
        self.assertTrue(runner.is_paused())
        runner.resume()
        self.assertFalse(runner.is_paused())

        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
