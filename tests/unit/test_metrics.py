#!/usr/bin/env python3
import unittest
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'media_importer'))

from metrics import Metrics, get_metrics


class TestMetrics(unittest.TestCase):

    def setUp(self):
        global _default_metrics
        _default_metrics = None

    def test_metrics_initialization(self):
        metrics = Metrics()
        self.assertEqual(metrics._counters['total'], 0)
        self.assertEqual(metrics._counters['success'], 0)
        self.assertEqual(metrics._counters['failed'], 0)
        self.assertEqual(metrics._counters['skipped'], 0)
        self.assertEqual(metrics._llm_calls, 0)
        self.assertEqual(metrics._llm_failures, 0)

    def test_record_task_start(self):
        metrics = Metrics()
        metrics.set_queue_pending(5)

        metrics.record_task_start()

        self.assertEqual(metrics._counters['total'], 1)
        self.assertEqual(metrics._queue_status['processing'], 1)
        self.assertEqual(metrics._queue_status['pending'], 4)

    def test_record_task_complete_success(self):
        metrics = Metrics()
        metrics.record_task_start()
        metrics.record_task_complete('success', duration=0.5)

        self.assertEqual(metrics._counters['success'], 1)
        self.assertEqual(metrics._queue_status['processing'], 0)

    def test_record_task_complete_failed(self):
        metrics = Metrics()
        metrics.record_task_start()
        metrics.record_task_complete('failed', duration=0.3)

        self.assertEqual(metrics._counters['failed'], 1)
        self.assertEqual(metrics._queue_status['processing'], 0)

    def test_record_task_complete_skipped(self):
        metrics = Metrics()
        metrics.record_task_start()
        metrics.record_task_complete('skipped')

        self.assertEqual(metrics._counters['skipped'], 1)
        self.assertEqual(metrics._queue_status['processing'], 0)

    def test_success_rate(self):
        metrics = Metrics()

        metrics.record_task_start()
        metrics.record_task_complete('success')
        metrics.record_task_start()
        metrics.record_task_complete('success')
        metrics.record_task_start()
        metrics.record_task_complete('failed')

        self.assertEqual(metrics.success_rate, 2/3)

    def test_success_rate_no_tasks(self):
        metrics = Metrics()
        self.assertEqual(metrics.success_rate, 0.0)

    def test_avg_processing_time(self):
        metrics = Metrics()
        metrics.record_task_start()
        metrics.record_task_complete('success', duration=0.2)
        metrics.record_task_start()
        metrics.record_task_complete('success', duration=0.4)

        self.assertAlmostEqual(metrics.avg_processing_time, 0.3, places=10)

    def test_avg_processing_time_no_tasks(self):
        metrics = Metrics()
        self.assertEqual(metrics.avg_processing_time, 0.0)

    def test_record_llm_call_success(self):
        metrics = Metrics()
        metrics.record_llm_call(success=True)
        metrics.record_llm_call(success=True)

        self.assertEqual(metrics._llm_calls, 2)
        self.assertEqual(metrics._llm_failures, 0)

    def test_record_llm_call_failed(self):
        metrics = Metrics()
        metrics.record_llm_call(success=True)
        metrics.record_llm_call(success=False)
        metrics.record_llm_call(success=False)

        self.assertEqual(metrics._llm_calls, 3)
        self.assertEqual(metrics._llm_failures, 2)

    def test_set_queue_pending(self):
        metrics = Metrics()
        metrics.set_queue_pending(10)
        self.assertEqual(metrics._queue_status['pending'], 10)

    def test_set_queue_paused(self):
        metrics = Metrics()
        metrics.set_queue_paused(True)
        self.assertTrue(metrics._queue_status['paused'])
        metrics.set_queue_paused(False)
        self.assertFalse(metrics._queue_status['paused'])

    def test_uptime(self):
        metrics = Metrics()
        time.sleep(0.1)
        uptime = metrics.uptime
        self.assertIsInstance(uptime, str)
        self.assertIn('s', uptime)

    def test_to_dict(self):
        metrics = Metrics()
        metrics.set_queue_pending(3)
        metrics.record_task_start()
        metrics.record_task_complete('success', duration=0.5)
        metrics.record_llm_call(success=True)
        metrics.record_llm_call(success=False)

        result = metrics.to_dict()

        self.assertIsInstance(result, dict)
        self.assertEqual(result['total_tasks'], 1)
        self.assertEqual(result['success_tasks'], 1)
        self.assertEqual(result['failed_tasks'], 0)
        self.assertEqual(result['skipped_tasks'], 0)
        self.assertEqual(result['success_rate'], 1.0)
        self.assertEqual(result['avg_processing_time_seconds'], 0.5)
        self.assertEqual(result['total_llm_calls'], 2)
        self.assertEqual(result['llm_failures'], 1)
        self.assertEqual(result['current_queue_pending'], 2)
        self.assertIn('uptime', result)

    def test_get_metrics_singleton(self):
        m1 = get_metrics()
        m2 = get_metrics()
        self.assertIs(m1, m2)

    def test_full_workflow(self):
        metrics = Metrics()
        metrics.set_queue_pending(3)

        metrics.record_task_start()
        metrics.record_llm_call(success=True)
        metrics.record_task_complete('success', duration=0.3)

        metrics.record_task_start()
        metrics.record_llm_call(success=False)
        metrics.record_llm_call(success=True)
        metrics.record_task_complete('failed', duration=0.5)

        metrics.record_task_start()
        metrics.record_task_complete('skipped')

        result = metrics.to_dict()
        self.assertEqual(result['total_tasks'], 3)
        self.assertEqual(result['success_tasks'], 1)
        self.assertEqual(result['failed_tasks'], 1)
        self.assertEqual(result['skipped_tasks'], 1)
        self.assertEqual(result['total_llm_calls'], 3)
        self.assertEqual(result['llm_failures'], 1)


if __name__ == '__main__':
    unittest.main()
