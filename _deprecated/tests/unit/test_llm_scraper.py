#!/usr/bin/env python3
import unittest
import os
import sys
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'media_importer'))

from llm_scraper import LLMScraper, LLMScrapeError


class TestLLMScraper(unittest.TestCase):

    def setUp(self):
        self.config = {
            'llm': {
                'api_key': 'test-key',
                'base_url': 'https://api.openai.com/v1',
                'model': 'gpt-3.5-turbo',
                'timeout': 30,
                'max_retries': 2,
                'retry_delay': 0.1,
                'fallback_model': 'gpt-4',
                'confidence_threshold': 0.8
            },
            'dimensions': [
                {
                    'name': 'media_type',
                    'label': '影视类型',
                    'values': ['movie', 'tv']
                },
                {
                    'name': 'documentary',
                    'label': '是否纪录片',
                    'values': ['yes', 'no']
                },
                {
                    'name': 'restricted',
                    'label': '是否限制级',
                    'values': ['yes', 'no']
                }
            ]
        }
        self.scraper = LLMScraper(self.config)

    def test_initialization(self):
        self.assertEqual(self.scraper.api_key, 'test-key')
        self.assertEqual(self.scraper.model, 'gpt-3.5-turbo')
        self.assertEqual(self.scraper.timeout, 30)
        self.assertEqual(self.scraper.max_retries, 2)
        self.assertEqual(self.scraper.fallback_model, 'gpt-4')
        self.assertEqual(self.scraper.confidence_threshold, 0.8)
        self.assertEqual(len(self.scraper.dimensions), 3)

    def test_build_system_prompt_contains_dimensions(self):
        prompt = self.scraper._build_system_prompt()
        self.assertIn('影视类型', prompt)
        self.assertIn('是否纪录片', prompt)
        self.assertIn('是否限制级', prompt)
        self.assertIn('movie|tv', prompt)
        self.assertIn('yes|no', prompt)

    def test_build_json_schema(self):
        schema = self.scraper._build_json_schema()
        self.assertIn('title_cn', schema)
        self.assertIn('title_en', schema)
        self.assertIn('year', schema)
        self.assertIn('type', schema)
        self.assertIn('dimensions', schema)
        self.assertIn('media_type', schema['dimensions'])
        self.assertIn('documentary', schema['dimensions'])

    def test_parse_response_valid_json(self):
        valid_json = json.dumps({
            'title_cn': '盗梦空间',
            'title_en': 'Inception',
            'year': 2010,
            'resolution': '1080p',
            'quality': 'BluRay',
            'language': 'en',
            'type': 'movie',
            'season': None,
            'episode': None,
            'dimensions': {
                'media_type': 'movie',
                'documentary': 'no',
                'restricted': 'no'
            },
            'confidence': 0.95
        })

        result = self.scraper._parse_response(valid_json)
        self.assertEqual(result['title_cn'], '盗梦空间')
        self.assertEqual(result['title_en'], 'Inception')
        self.assertEqual(result['year'], 2010)
        self.assertEqual(result['type'], 'movie')
        self.assertEqual(result['confidence'], 0.95)
        self.assertFalse(result['low_confidence'])
        self.assertIn('raw_info', result)

    def test_parse_response_json_with_markdown(self):
        markdown_json = '```json\n' + json.dumps({
            'title_cn': '盗梦空间',
            'title_en': 'Inception',
            'year': 2010,
            'type': 'movie',
            'confidence': 0.9
        }) + '\n```'

        result = self.scraper._parse_response(markdown_json)
        self.assertEqual(result['title_cn'], '盗梦空间')

    def test_parse_response_missing_fields(self):
        partial_json = json.dumps({
            'title_cn': '盗梦空间',
            'confidence': 0.8
        })

        result = self.scraper._parse_response(partial_json)
        self.assertEqual(result['title_cn'], '盗梦空间')
        self.assertIsNone(result['title_en'])
        self.assertIsNone(result['year'])
        self.assertIsNone(result['season'])
        self.assertIn('dimensions', result)

    def test_parse_response_low_confidence(self):
        low_conf_json = json.dumps({
            'title_cn': '测试',
            'title_en': 'Test',
            'year': 2020,
            'type': 'movie',
            'confidence': 0.5
        })

        result = self.scraper._parse_response(low_conf_json)
        self.assertTrue(result['low_confidence'])

    def test_parse_response_invalid_json(self):
        with self.assertRaises(LLMScrapeError):
            self.scraper._parse_response('not valid json')

    def test_parse_response_invalid_confidence_type(self):
        invalid_conf = json.dumps({
            'title_cn': '测试',
            'confidence': 'high'
        })
        result = self.scraper._parse_response(invalid_conf)
        self.assertEqual(result['confidence'], 0.5)

    @patch('urllib.request.urlopen')
    def test_call_api_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'choices': [{'message': {'content': '{"title_cn": "测试"}'}}]
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = self.scraper._call_api('system prompt', 'user content', 'gpt-3.5-turbo')
        self.assertIn('测试', result)

    @patch('urllib.request.urlopen')
    def test_call_api_network_error(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError('Network error')

        with self.assertRaises(LLMScrapeError):
            self.scraper._call_api('system prompt', 'user content', 'gpt-3.5-turbo')

    @patch('urllib.request.urlopen')
    def test_call_api_invalid_response(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({'invalid': 'structure'}).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        with self.assertRaises(LLMScrapeError):
            self.scraper._call_api('system prompt', 'user content', 'gpt-3.5-turbo')

    @patch.object(LLMScraper, '_call_api')
    def test_retry_with_fallback_success_first_try(self, mock_call):
        mock_call.return_value = json.dumps({
            'title_cn': '盗梦空间',
            'title_en': 'Inception',
            'year': 2010,
            'type': 'movie',
            'confidence': 0.9
        })

        result = self.scraper._retry_with_fallback('system', 'user')
        self.assertEqual(result['title_cn'], '盗梦空间')
        self.assertEqual(mock_call.call_count, 1)

    @patch.object(LLMScraper, '_call_api')
    def test_retry_with_fallback_retries(self, mock_call):
        mock_call.side_effect = [
            LLMScrapeError('First fail'),
            json.dumps({
                'title_cn': '盗梦空间',
                'title_en': 'Inception',
                'year': 2010,
                'type': 'movie',
                'confidence': 0.9
            })
        ]

        result = self.scraper._retry_with_fallback('system', 'user')
        self.assertEqual(result['title_cn'], '盗梦空间')
        self.assertEqual(mock_call.call_count, 2)

    @patch.object(LLMScraper, '_call_api')
    def test_retry_with_fallback_uses_fallback_model(self, mock_call):
        mock_call.side_effect = [
            LLMScrapeError('Fail 1'),
            LLMScrapeError('Fail 2'),
            json.dumps({
                'title_cn': '盗梦空间',
                'title_en': 'Inception',
                'year': 2010,
                'type': 'movie',
                'confidence': 0.9
            })
        ]

        result = self.scraper._retry_with_fallback('system', 'user')
        self.assertEqual(result['title_cn'], '盗梦空间')
        self.assertEqual(mock_call.call_count, 3)

    @patch.object(LLMScraper, '_call_api')
    def test_retry_with_fallback_all_fail(self, mock_call):
        mock_call.side_effect = LLMScrapeError('All failed')

        with self.assertRaises(LLMScrapeError):
            self.scraper._retry_with_fallback('system', 'user')

        self.assertEqual(mock_call.call_count, 4)

    @patch.object(LLMScraper, '_retry_with_fallback')
    def test_scrape_success(self, mock_retry):
        mock_retry.return_value = {
            'title_cn': '绝命毒师',
            'title_en': 'Breaking Bad',
            'year': 2008,
            'type': 'tv',
            'season': 1,
            'episode': 1,
            'confidence': 0.9,
            'dimensions': {
                'media_type': 'tv',
                'documentary': 'no',
                'restricted': 'no'
            }
        }

        result = self.scraper.scrape(
            'Breaking.Bad.S01E01.1080p.BluRay.mkv',
            ['Breaking.Bad.S01E01.zh.srt']
        )

        self.assertEqual(result['title_cn'], '绝命毒师')
        self.assertEqual(result['type'], 'tv')
        self.assertEqual(result['season'], 1)
        self.assertEqual(result['episode'], 1)
        mock_retry.assert_called_once()

    @patch.object(LLMScraper, '_retry_with_fallback')
    def test_scrape_without_subtitles(self, mock_retry):
        mock_retry.return_value = {
            'title_cn': '盗梦空间',
            'title_en': 'Inception',
            'year': 2010,
            'type': 'movie',
            'confidence': 0.9
        }

        self.scraper.scrape('Inception.2010.mkv')
        mock_retry.assert_called_once()

    def test_llm_scrape_error_exception(self):
        error = LLMScrapeError('Test error message')
        self.assertEqual(str(error), 'Test error message')

    def test_no_fallback_model(self):
        config_no_fallback = self.config.copy()
        config_no_fallback['llm']['fallback_model'] = None
        scraper = LLMScraper(config_no_fallback)
        self.assertIsNone(scraper.fallback_model)


if __name__ == '__main__':
    unittest.main()
