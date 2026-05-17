#!/usr/bin/env python3
import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'media_importer'))

from unit.test_config_loader import TestConfigLoader
from unit.test_logger import TestLogger
from unit.test_metrics import TestMetrics
from unit.test_file_scanner import TestFileScanner
from unit.test_llm_scraper import TestLLMScraper
from unit.test_classifier import TestClassifier
from unit.test_dedup_checker import TestDedupChecker
from unit.test_file_operations import TestFileCopier, TestFileMover
from unit.test_task_pipeline import TestTask, TestTaskManager, TestPipelineRunner


def run_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestConfigLoader))
    suite.addTests(loader.loadTestsFromTestCase(TestLogger))
    suite.addTests(loader.loadTestsFromTestCase(TestMetrics))
    suite.addTests(loader.loadTestsFromTestCase(TestFileScanner))
    suite.addTests(loader.loadTestsFromTestCase(TestLLMScraper))
    suite.addTests(loader.loadTestsFromTestCase(TestClassifier))
    suite.addTests(loader.loadTestsFromTestCase(TestDedupChecker))
    suite.addTests(loader.loadTestsFromTestCase(TestFileCopier))
    suite.addTests(loader.loadTestsFromTestCase(TestFileMover))
    suite.addTests(loader.loadTestsFromTestCase(TestTask))
    suite.addTests(loader.loadTestsFromTestCase(TestTaskManager))
    suite.addTests(loader.loadTestsFromTestCase(TestPipelineRunner))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
