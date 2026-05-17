#!/usr/bin/env python3
import unittest
import os
import sys
import tempfile
import json
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'media_importer'))

from logger import Logger, JsonFormatter, TextFormatter, get_logger


class TestLogger(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        logging.shutdown()

    def test_logger_initialization(self):
        logger = Logger(level='INFO', fmt='text', log_dir=self.test_dir)
        self.assertIsNotNone(logger)
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, 'media_importer.log')))

    def test_log_level_debug(self):
        logger = Logger(level='DEBUG', fmt='text', log_dir=self.test_dir)
        logger.debug('test debug message')
        logger.info('test info message')

        log_file = os.path.join(self.test_dir, 'media_importer.log')
        with open(log_file, 'r') as f:
            content = f.read()
        self.assertIn('test debug message', content)
        self.assertIn('test info message', content)

    def test_log_level_info_filters_debug(self):
        logger = Logger(level='INFO', fmt='text', log_dir=self.test_dir)
        logger.debug('test debug message')
        logger.info('test info message')

        log_file = os.path.join(self.test_dir, 'media_importer.log')
        with open(log_file, 'r') as f:
            content = f.read()
        self.assertNotIn('test debug message', content)
        self.assertIn('test info message', content)

    def test_json_formatter(self):
        logger = Logger(level='INFO', fmt='json', log_dir=self.test_dir)
        logger.info('test json message')

        log_file = os.path.join(self.test_dir, 'media_importer.log')
        with open(log_file, 'r') as f:
            lines = f.readlines()

        self.assertTrue(len(lines) > 0)
        for line in lines:
            if 'test json message' in line:
                log_entry = json.loads(line)
                self.assertEqual(log_entry['message'], 'test json message')
                self.assertIn('level', log_entry)
                self.assertIn('time', log_entry)
                break

    def test_text_formatter(self):
        logger = Logger(level='INFO', fmt='text', log_dir=self.test_dir)
        logger.info('test text message')

        log_file = os.path.join(self.test_dir, 'media_importer.log')
        with open(log_file, 'r') as f:
            content = f.read()
        self.assertIn('[INFO]', content)
        self.assertIn('test text message', content)

    def test_step_log(self):
        logger = Logger(level='INFO', fmt='json', log_dir=self.test_dir)
        logger.step_log('task-123', 'scrape', 'INFO', 'Processing file')

        log_file = os.path.join(self.test_dir, 'media_importer.log')
        with open(log_file, 'r') as f:
            lines = f.readlines()

        found = False
        for line in lines:
            if 'Processing file' in line:
                log_entry = json.loads(line)
                self.assertEqual(log_entry['task_id'], 'task-123')
                self.assertEqual(log_entry['step'], 'scrape')
                found = True
                break
        self.assertTrue(found)

    def test_warn_log(self):
        logger = Logger(level='WARN', fmt='text', log_dir=self.test_dir)
        logger.warn('test warn message')
        logger.info('this should not appear')

        log_file = os.path.join(self.test_dir, 'media_importer.log')
        with open(log_file, 'r') as f:
            content = f.read()
        self.assertIn('test warn message', content)
        self.assertNotIn('this should not appear', content)

    def test_error_log(self):
        logger = Logger(level='ERROR', fmt='text', log_dir=self.test_dir)
        logger.error('test error message')
        logger.warn('this should not appear')

        log_file = os.path.join(self.test_dir, 'media_importer.log')
        with open(log_file, 'r') as f:
            content = f.read()
        self.assertIn('test error message', content)
        self.assertNotIn('this should not appear', content)

    def test_get_logger_singleton(self):
        config = {
            'log_dir': self.test_dir,
            'logging': {
                'level': 'INFO',
                'format': 'text',
                'max_size_mb': 100,
                'backup_count': 5
            }
        }

        logger1 = get_logger(config)
        logger2 = get_logger()
        self.assertIs(logger1, logger2)

    def test_step_log_returns_entry(self):
        logger = Logger(level='INFO', fmt='json', log_dir=self.test_dir)
        result = logger.step_log('task-001', 'copy', 'ERROR', 'Copy failed')

        self.assertIsInstance(result, dict)
        self.assertEqual(result['task_id'], 'task-001')
        self.assertEqual(result['step'], 'copy')
        self.assertEqual(result['level'], 'ERROR')
        self.assertEqual(result['message'], 'Copy failed')
        self.assertIn('timestamp', result)


if __name__ == '__main__':
    unittest.main()
