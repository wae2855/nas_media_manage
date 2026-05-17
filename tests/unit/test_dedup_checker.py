#!/usr/bin/env python3
import unittest
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'media_importer'))

from dedup_checker import (
    normalize_title,
    is_title_match,
    parse_filename_info,
    find_existing_file,
    check_duplicate
)


class TestDedupChecker(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_normalize_title_lowercase(self):
        self.assertEqual(normalize_title('Inception'), 'inception')
        self.assertEqual(normalize_title('Inception'), 'inception')

    def test_normalize_title_remove_punctuation(self):
        self.assertEqual(normalize_title('Inception.2010'), 'inception2010')
        self.assertEqual(normalize_title('Breaking-Bad'), 'breakingbad')
        self.assertEqual(normalize_title('The_Matrix'), 'thematrix')
        self.assertEqual(normalize_title('盗梦空间。'), '盗梦空间')
        self.assertEqual(normalize_title('绝命，毒师'), '绝命毒师')

    def test_normalize_title_remove_spaces(self):
        self.assertEqual(normalize_title('The Matrix'), 'thematrix')
        self.assertEqual(normalize_title('盗梦 空间'), '盗梦空间')

    def test_normalize_title_empty_or_none(self):
        self.assertEqual(normalize_title(''), '')
        self.assertEqual(normalize_title(None), '')

    def test_is_title_match_exact_match(self):
        self.assertTrue(is_title_match('Inception', 'Inception'))
        self.assertTrue(is_title_match('盗梦空间', '盗梦空间'))

    def test_is_title_match_case_insensitive(self):
        self.assertTrue(is_title_match('Inception', 'INCEPTION'))
        self.assertTrue(is_title_match('inception', 'INCEPTION'))

    def test_is_title_match_with_punctuation(self):
        self.assertTrue(is_title_match('Inception.2010', 'Inception-2010'))
        self.assertTrue(is_title_match('盗梦空间', '盗梦空间'))

    def test_is_title_match_no_match(self):
        self.assertFalse(is_title_match('Inception', 'Matrix'))
        self.assertFalse(is_title_match('盗梦空间', '黑客帝国'))

    def test_is_title_match_empty(self):
        self.assertFalse(is_title_match('', 'Inception'))
        self.assertFalse(is_title_match('Inception', ''))

    def test_parse_filename_info_extracts_year(self):
        result = parse_filename_info('Inception.2010.mkv')
        self.assertEqual(result['year'], '2010')

    def test_parse_filename_info_extracts_season(self):
        result = parse_filename_info('Breaking.Bad.S01E01.mkv')
        self.assertEqual(result['season'], '01')

    def test_parse_filename_info_extracts_episode(self):
        result = parse_filename_info('Breaking.Bad.S01E01.mkv')
        self.assertEqual(result['episode'], '01')

    def test_parse_filename_info_extracts_titles_chinese(self):
        result = parse_filename_info('盗梦空间.2010.mkv')
        self.assertEqual(result['title_cn'], '盗梦空间')
        self.assertEqual(result['year'], '2010')

    def test_parse_filename_info_extracts_titles_english(self):
        result = parse_filename_info('Inception.2010.mkv')
        self.assertEqual(result['title_en'], 'Inception')

    def test_parse_filename_info_mixed_chinese_english(self):
        result = parse_filename_info('盗梦空间.Inception.2010.mkv')
        self.assertEqual(result['title_cn'], '盗梦空间')
        self.assertEqual(result['title_en'], 'Inception')
        self.assertEqual(result['year'], '2010')

    def test_find_existing_file_no_match(self):
        open(os.path.join(self.test_dir, 'Matrix.1999.mkv'), 'w').close()
        scraped_info = {'title_cn': '盗梦空间', 'title_en': 'Inception', 'year': 2010}
        results = find_existing_file(self.test_dir, scraped_info)
        self.assertEqual(len(results), 0)

    def test_find_existing_file_match_by_cn_title_and_year(self):
        open(os.path.join(self.test_dir, '盗梦空间.2010.mkv'), 'w').close()
        scraped_info = {'title_cn': '盗梦空间', 'title_en': 'Inception', 'year': 2010}
        results = find_existing_file(self.test_dir, scraped_info)
        self.assertEqual(len(results), 1)

    def test_find_existing_file_match_by_en_title_and_year(self):
        open(os.path.join(self.test_dir, 'Inception.2010.mkv'), 'w').close()
        scraped_info = {'title_cn': '盗梦空间', 'title_en': 'Inception', 'year': 2010}
        results = find_existing_file(self.test_dir, scraped_info)
        self.assertEqual(len(results), 1)

    def test_find_existing_file_ignore_diff_year(self):
        open(os.path.join(self.test_dir, 'Inception.2000.mkv'), 'w').close()
        scraped_info = {'title_cn': '盗梦空间', 'title_en': 'Inception', 'year': 2010}
        results = find_existing_file(self.test_dir, scraped_info)
        self.assertEqual(len(results), 0)

    def test_find_existing_file_tv_show_diff_episode(self):
        open(os.path.join(self.test_dir, 'Breaking.Bad.S01E02.mkv'), 'w').close()
        scraped_info = {
            'title_cn': '绝命毒师',
            'title_en': 'Breaking Bad',
            'year': 2008,
            'season': 1,
            'episode': 1
        }
        results = find_existing_file(self.test_dir, scraped_info)
        self.assertEqual(len(results), 0)

    def test_find_existing_file_tv_show_same_episode(self):
        open(os.path.join(self.test_dir, 'Breaking.Bad.2008.S01E01.mkv'), 'w').close()
        scraped_info = {
            'title_cn': '绝命毒师',
            'title_en': 'Breaking Bad',
            'year': 2008,
            'season': 1,
            'episode': 1
        }
        results = find_existing_file(self.test_dir, scraped_info)
        self.assertEqual(len(results), 1)

    def test_find_existing_file_in_subdir(self):
        subdir = os.path.join(self.test_dir, 'movies')
        os.makedirs(subdir)
        open(os.path.join(subdir, 'Inception.2010.mkv'), 'w').close()
        scraped_info = {'title_cn': '盗梦空间', 'title_en': 'Inception', 'year': 2010}
        results = find_existing_file(self.test_dir, scraped_info)
        self.assertEqual(len(results), 1)

    def test_find_existing_file_dir_not_exist(self):
        scraped_info = {'title_cn': '盗梦空间', 'title_en': 'Inception', 'year': 2010}
        results = find_existing_file('/nonexistent/path', scraped_info)
        self.assertEqual(len(results), 0)

    def test_check_duplicate_no_duplicate(self):
        scraped_info = {'title_cn': '盗梦空间', 'title_en': 'Inception', 'year': 2010}
        result = check_duplicate(self.test_dir, scraped_info, 'skip')
        self.assertFalse(result['is_duplicate'])
        self.assertIsNone(result['existing_file'])
        self.assertEqual(result['action'], 'skip')
        self.assertIsNone(result['suggested_filename'])

    def test_check_duplicate_skip_strategy(self):
        open(os.path.join(self.test_dir, 'Inception.2010.mkv'), 'w').close()
        scraped_info = {'title_cn': '盗梦空间', 'title_en': 'Inception', 'year': 2010}
        result = check_duplicate(self.test_dir, scraped_info, 'skip')
        self.assertTrue(result['is_duplicate'])
        self.assertIsNotNone(result['existing_file'])
        self.assertEqual(result['action'], 'skip')
        self.assertIsNone(result['suggested_filename'])

    def test_check_duplicate_overwrite_strategy(self):
        open(os.path.join(self.test_dir, 'Inception.2010.mkv'), 'w').close()
        scraped_info = {'title_cn': '盗梦空间', 'title_en': 'Inception', 'year': 2010}
        result = check_duplicate(self.test_dir, scraped_info, 'overwrite')
        self.assertTrue(result['is_duplicate'])
        self.assertEqual(result['action'], 'overwrite')
        self.assertIsNone(result['suggested_filename'])

    def test_check_duplicate_rename_strategy(self):
        open(os.path.join(self.test_dir, 'Inception.2010.mkv'), 'w').close()
        scraped_info = {
            'title_cn': '盗梦空间',
            'title_en': 'Inception',
            'year': 2010,
            'filename': 'Inception.2010.mkv'
        }
        result = check_duplicate(self.test_dir, scraped_info, 'rename')
        self.assertTrue(result['is_duplicate'])
        self.assertEqual(result['action'], 'rename')
        self.assertIsNotNone(result['suggested_filename'])
        self.assertIn('copy1', result['suggested_filename'])

    def test_check_duplicate_rename_strategy_multiple_copies(self):
        open(os.path.join(self.test_dir, 'Inception.2010.mkv'), 'w').close()
        open(os.path.join(self.test_dir, '盗梦空间_2010_copy1.mkv'), 'w').close()
        scraped_info = {
            'title_cn': '盗梦空间',
            'title_en': 'Inception',
            'year': 2010,
            'filename': 'Inception.2010.mkv'
        }
        result = check_duplicate(self.test_dir, scraped_info, 'rename')
        self.assertTrue(result['is_duplicate'])
        self.assertIn('copy2', result['suggested_filename'])

    def test_check_duplicate_rename_strategy_no_extension(self):
        open(os.path.join(self.test_dir, 'Inception.2010.mkv'), 'w').close()
        scraped_info = {
            'title_cn': '盗梦空间',
            'title_en': 'Inception',
            'year': 2010
        }
        result = check_duplicate(self.test_dir, scraped_info, 'rename')
        self.assertTrue(result['is_duplicate'])
        self.assertTrue(result['suggested_filename'].endswith('.mkv'))


if __name__ == '__main__':
    unittest.main()
