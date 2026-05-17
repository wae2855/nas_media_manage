#!/usr/bin/env python3
import unittest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'media_importer'))

from classifier import match_conditions, render_template, classify


class TestClassifier(unittest.TestCase):

    def test_match_conditions_all_match(self):
        dimensions = {
            'media_type': 'movie',
            'documentary': 'no',
            'restricted': 'no'
        }
        conditions = {'media_type': 'movie'}
        self.assertTrue(match_conditions(dimensions, conditions))

    def test_match_conditions_multiple_match(self):
        dimensions = {
            'media_type': 'movie',
            'documentary': 'no',
            'restricted': 'no'
        }
        conditions = {'media_type': 'movie', 'documentary': 'no'}
        self.assertTrue(match_conditions(dimensions, conditions))

    def test_match_conditions_no_match(self):
        dimensions = {'media_type': 'movie'}
        conditions = {'media_type': 'tv'}
        self.assertFalse(match_conditions(dimensions, conditions))

    def test_match_conditions_partial_match(self):
        dimensions = {'media_type': 'movie', 'documentary': 'yes'}
        conditions = {'media_type': 'movie', 'documentary': 'no'}
        self.assertFalse(match_conditions(dimensions, conditions))

    def test_match_conditions_empty_conditions(self):
        dimensions = {'media_type': 'movie'}
        conditions = {}
        self.assertTrue(match_conditions(dimensions, conditions))

    def test_render_template_basic_fields(self):
        scraped_info = {
            'title_cn': '盗梦空间',
            'title_en': 'Inception',
            'year': 2010
        }
        template = '/movies/{year}/{title_cn} ({title_en})/'
        result = render_template(template, scraped_info)
        self.assertEqual(result, '/movies/2010/盗梦空间 (Inception)/')

    def test_render_template_tv_show(self):
        scraped_info = {
            'title_cn': '绝命毒师',
            'title_en': 'Breaking Bad',
            'year': 2008,
            'season': 1,
            'episode': 1
        }
        template = '/tv/{title_cn} ({year})/Season {season}/'
        result = render_template(template, scraped_info)
        self.assertEqual(result, '/tv/绝命毒师 (2008)/Season 1/')

    def test_render_template_quality_resolution(self):
        scraped_info = {
            'title_cn': '盗梦空间',
            'year': 2010,
            'resolution': '1080p',
            'quality': 'BluRay'
        }
        template = '/movies/{title_cn} ({year})/{resolution}/{quality}/'
        result = render_template(template, scraped_info)
        self.assertEqual(result, '/movies/盗梦空间 (2010)/1080p/BluRay/')

    def test_render_template_dimension_field(self):
        scraped_info = {
            'title_cn': '地球脉动',
            'year': 2016,
            'dimensions': {
                'documentary': 'yes',
                'media_type': 'movie'
            }
        }
        template = '/documentaries/{dimension.media_type}/{title_cn} ({year})/'
        result = render_template(template, scraped_info)
        self.assertEqual(result, '/documentaries/movie/地球脉动 (2016)/')

    def test_render_template_none_values(self):
        scraped_info = {
            'title_cn': '测试',
            'year': None,
            'season': None
        }
        template = '/test/{title_cn} ({year})/Season {season}/'
        result = render_template(template, scraped_info)
        self.assertEqual(result, '/test/测试 /Season /')

    def test_render_template_multiple_slashes(self):
        scraped_info = {
            'title_cn': '测试',
            'year': 2020,
            'season': None
        }
        template = '/test/{year}//{season}/{title_cn}/'
        result = render_template(template, scraped_info)
        self.assertEqual(result, '/test/2020/测试/')

    def test_classify_match_movie_rule(self):
        scraped_info = {
            'title_cn': '盗梦空间',
            'title_en': 'Inception',
            'year': 2010,
            'dimensions': {
                'media_type': 'movie',
                'documentary': 'no'
            }
        }
        path_rules = [
            {
                'conditions': {'media_type': 'tv'},
                'template': '/tv/{title_cn} ({year})/'
            },
            {
                'conditions': {'media_type': 'movie', 'documentary': 'no'},
                'template': '/movies/{year}/{title_cn} ({year})/'
            },
            {
                'conditions': {},
                'template': '/other/{title_cn}/'
            }
        ]
        result = classify(scraped_info, path_rules)
        self.assertEqual(result, '/movies/2010/盗梦空间 (2010)/')

    def test_classify_match_tv_rule(self):
        scraped_info = {
            'title_cn': '绝命毒师',
            'title_en': 'Breaking Bad',
            'year': 2008,
            'season': 1,
            'dimensions': {
                'media_type': 'tv',
                'documentary': 'no'
            }
        }
        path_rules = [
            {
                'conditions': {'media_type': 'tv'},
                'template': '/tv/{title_cn} ({year})/Season {season}/'
            },
            {
                'conditions': {'media_type': 'movie', 'documentary': 'no'},
                'template': '/movies/{year}/{title_cn}/'
            },
            {
                'conditions': {},
                'template': '/other/{title_cn}/'
            }
        ]
        result = classify(scraped_info, path_rules)
        self.assertEqual(result, '/tv/绝命毒师 (2008)/Season 1/')

    def test_classify_match_documentary_rule(self):
        scraped_info = {
            'title_cn': '地球脉动',
            'year': 2016,
            'dimensions': {
                'media_type': 'movie',
                'documentary': 'yes'
            }
        }
        path_rules = [
            {
                'conditions': {'media_type': 'tv'},
                'template': '/tv/{title_cn}/'
            },
            {
                'conditions': {'media_type': 'movie', 'documentary': 'yes'},
                'template': '/documentaries/{title_cn}/'
            },
            {
                'conditions': {},
                'template': '/other/{title_cn}/'
            }
        ]
        result = classify(scraped_info, path_rules)
        self.assertEqual(result, '/documentaries/地球脉动/')

    def test_classify_fallback_rule(self):
        scraped_info = {
            'title_cn': '未知类型',
            'year': 2020,
            'dimensions': {
                'media_type': 'unknown'
            }
        }
        path_rules = [
            {
                'conditions': {'media_type': 'tv'},
                'template': '/tv/{title_cn}/'
            },
            {
                'conditions': {'media_type': 'movie'},
                'template': '/movies/{title_cn}/'
            },
            {
                'conditions': {},
                'template': '/other/{title_cn}/'
            }
        ]
        result = classify(scraped_info, path_rules)
        self.assertEqual(result, '/other/未知类型/')

    def test_classify_no_matching_rule_no_fallback(self):
        scraped_info = {
            'title_cn': '测试',
            'dimensions': {'media_type': 'unknown'}
        }
        path_rules = [
            {'conditions': {'media_type': 'tv'}, 'template': '/tv/'},
            {'conditions': {'media_type': 'movie'}, 'template': '/movies/'}
        ]
        result = classify(scraped_info, path_rules)
        self.assertEqual(result, '')

    def test_classify_first_match_wins(self):
        scraped_info = {
            'title_cn': '测试',
            'dimensions': {
                'media_type': 'tv',
                'documentary': 'no'
            }
        }
        path_rules = [
            {'conditions': {'media_type': 'tv'}, 'template': '/first/tv/'},
            {'conditions': {'media_type': 'tv', 'documentary': 'no'}, 'template': '/second/tv/'}
        ]
        result = classify(scraped_info, path_rules)
        self.assertEqual(result, '/first/tv/')


if __name__ == '__main__':
    unittest.main()
