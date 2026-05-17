#!/usr/bin/env python3
import unittest
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'media_importer'))

from file_scanner import (
    match_filename_pattern,
    find_video_files,
    find_subtitle_files,
    scan_source_dir
)


class TestFileScanner(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_match_filename_pattern_match(self):
        patterns = ['*.tmp', '.DS_Store', '*partial*']
        self.assertTrue(match_filename_pattern('test.tmp', patterns))
        self.assertTrue(match_filename_pattern('.DS_Store', patterns))
        self.assertTrue(match_filename_pattern('movie.partial.mkv', patterns))

    def test_match_filename_pattern_no_match(self):
        patterns = ['*.tmp', '.DS_Store', '*partial*']
        self.assertFalse(match_filename_pattern('movie.mkv', patterns))
        self.assertFalse(match_filename_pattern('subtitle.srt', patterns))

    def test_find_video_files_single_file(self):
        video_path = os.path.join(self.test_dir, 'Inception.2010.mkv')
        open(video_path, 'w').close()

        videos = find_video_files(
            self.test_dir,
            extensions=['.mkv', '.mp4'],
            ignore_patterns=['*.tmp', '.DS_Store'],
            max_depth=5
        )

        self.assertEqual(len(videos), 1)
        self.assertIn('Inception.2010.mkv', videos[0])

    def test_find_video_files_multiple_extensions(self):
        open(os.path.join(self.test_dir, 'movie1.mkv'), 'w').close()
        open(os.path.join(self.test_dir, 'movie2.mp4'), 'w').close()
        open(os.path.join(self.test_dir, 'movie3.avi'), 'w').close()
        open(os.path.join(self.test_dir, 'document.txt'), 'w').close()

        videos = find_video_files(
            self.test_dir,
            extensions=['.mkv', '.mp4', '.avi'],
            ignore_patterns=['*.tmp'],
            max_depth=5
        )

        self.assertEqual(len(videos), 3)

    def test_find_video_files_ignore_patterns(self):
        open(os.path.join(self.test_dir, 'valid.mkv'), 'w').close()
        open(os.path.join(self.test_dir, 'temp.tmp'), 'w').close()
        open(os.path.join(self.test_dir, '.DS_Store'), 'w').close()

        videos = find_video_files(
            self.test_dir,
            extensions=['.mkv', '.mp4'],
            ignore_patterns=['*.tmp', '.DS_Store'],
            max_depth=5
        )

        self.assertEqual(len(videos), 1)
        self.assertIn('valid.mkv', videos[0])

    def test_find_video_files_max_depth(self):
        level1_dir = os.path.join(self.test_dir, 'level1')
        level2_dir = os.path.join(level1_dir, 'level2')
        os.makedirs(level2_dir)

        open(os.path.join(self.test_dir, 'root.mkv'), 'w').close()
        open(os.path.join(level1_dir, 'level1.mkv'), 'w').close()
        open(os.path.join(level2_dir, 'level2.mkv'), 'w').close()

        videos = find_video_files(
            self.test_dir,
            extensions=['.mkv'],
            ignore_patterns=[],
            max_depth=1
        )

        self.assertEqual(len(videos), 2)

    def test_find_video_files_nonexistent_dir(self):
        videos = find_video_files(
            '/nonexistent/directory',
            extensions=['.mkv'],
            ignore_patterns=[],
            max_depth=5
        )

        self.assertEqual(len(videos), 0)

    def test_find_subtitle_files_match(self):
        video_path = os.path.join(self.test_dir, 'Breaking.Bad.S01E01.mkv')
        open(video_path, 'w').close()
        open(os.path.join(self.test_dir, 'Breaking.Bad.S01E01.zh.srt'), 'w').close()
        open(os.path.join(self.test_dir, 'Breaking.Bad.S01E01.en.srt'), 'w').close()

        subtitles = find_subtitle_files(video_path, ['.srt', '.ass'])

        self.assertEqual(len(subtitles), 2)

    def test_find_subtitle_files_no_match(self):
        video_path = os.path.join(self.test_dir, 'Inception.2010.mkv')
        open(video_path, 'w').close()
        open(os.path.join(self.test_dir, 'Other.Movie.zh.srt'), 'w').close()

        subtitles = find_subtitle_files(video_path, ['.srt'])

        self.assertEqual(len(subtitles), 0)

    def test_find_subtitle_files_multiple_extensions(self):
        video_path = os.path.join(self.test_dir, 'movie.mkv')
        open(video_path, 'w').close()
        open(os.path.join(self.test_dir, 'movie.zh.srt'), 'w').close()
        open(os.path.join(self.test_dir, 'movie.en.ass'), 'w').close()
        open(os.path.join(self.test_dir, 'movie.ssa'), 'w').close()

        subtitles = find_subtitle_files(video_path, ['.srt', '.ass', '.ssa'])

        self.assertEqual(len(subtitles), 3)

    def test_scan_source_dir_movie_no_subtitles(self):
        video_path = os.path.join(self.test_dir, 'Inception.2010.mkv')
        open(video_path, 'w').close()

        config = {
            'source_dir_scan': {
                'recursive': True,
                'max_depth': 5,
                'ignore_patterns': ['*.tmp', '.DS_Store']
            },
            'video_extensions': ['.mkv', '.mp4'],
            'subtitle_extensions': ['.srt', '.ass']
        }

        groups = scan_source_dir(self.test_dir, config)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['group_name'], 'Inception.2010')
        self.assertEqual(len(groups[0]['subtitles']), 0)
        self.assertIn('Inception.2010.mkv', groups[0]['video'])

    def test_scan_source_dir_tv_with_subtitles(self):
        video_path = os.path.join(self.test_dir, 'Breaking.Bad.S01E01.mkv')
        open(video_path, 'w').close()
        open(os.path.join(self.test_dir, 'Breaking.Bad.S01E01.zh.srt'), 'w').close()

        config = {
            'source_dir_scan': {
                'recursive': True,
                'max_depth': 5,
                'ignore_patterns': ['*.tmp']
            },
            'video_extensions': ['.mkv'],
            'subtitle_extensions': ['.srt']
        }

        groups = scan_source_dir(self.test_dir, config)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['group_name'], 'Breaking.Bad.S01E01')
        self.assertEqual(len(groups[0]['subtitles']), 1)
        self.assertIn('Breaking.Bad.S01E01.zh.srt', groups[0]['subtitles'][0])

    def test_scan_source_dir_ignore_files(self):
        open(os.path.join(self.test_dir, 'valid.mkv'), 'w').close()
        open(os.path.join(self.test_dir, 'temp.tmp'), 'w').close()
        open(os.path.join(self.test_dir, '.DS_Store'), 'w').close()

        config = {
            'source_dir_scan': {
                'recursive': True,
                'max_depth': 5,
                'ignore_patterns': ['*.tmp', '.DS_Store']
            },
            'video_extensions': ['.mkv'],
            'subtitle_extensions': ['.srt']
        }

        groups = scan_source_dir(self.test_dir, config)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['group_name'], 'valid')

    def test_scan_source_dir_empty_dir(self):
        config = {
            'source_dir_scan': {
                'recursive': True,
                'max_depth': 5,
                'ignore_patterns': []
            },
            'video_extensions': ['.mkv'],
            'subtitle_extensions': ['.srt']
        }

        groups = scan_source_dir(self.test_dir, config)

        self.assertEqual(len(groups), 0)

    def test_scan_source_dir_multiple_movies(self):
        open(os.path.join(self.test_dir, 'movie1.mkv'), 'w').close()
        open(os.path.join(self.test_dir, 'movie2.mp4'), 'w').close()
        open(os.path.join(self.test_dir, 'movie1.zh.srt'), 'w').close()

        config = {
            'source_dir_scan': {
                'recursive': True,
                'max_depth': 5,
                'ignore_patterns': []
            },
            'video_extensions': ['.mkv', '.mp4'],
            'subtitle_extensions': ['.srt']
        }

        groups = scan_source_dir(self.test_dir, config)

        self.assertEqual(len(groups), 2)
        group_names = sorted([g['group_name'] for g in groups])
        self.assertEqual(group_names, ['movie1', 'movie2'])

    def test_scan_source_dir_subdirectories(self):
        subdir = os.path.join(self.test_dir, 'movies')
        os.makedirs(subdir)
        open(os.path.join(subdir, 'Inception.2010.mkv'), 'w').close()

        config = {
            'source_dir_scan': {
                'recursive': True,
                'max_depth': 5,
                'ignore_patterns': []
            },
            'video_extensions': ['.mkv'],
            'subtitle_extensions': ['.srt']
        }

        groups = scan_source_dir(self.test_dir, config)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['group_name'], 'Inception.2010')

    def test_scan_source_dir_no_recursive(self):
        subdir = os.path.join(self.test_dir, 'movies')
        os.makedirs(subdir)
        open(os.path.join(self.test_dir, 'root.mkv'), 'w').close()
        open(os.path.join(subdir, 'subdir.mkv'), 'w').close()

        config = {
            'source_dir_scan': {
                'recursive': False,
                'max_depth': 5,
                'ignore_patterns': []
            },
            'video_extensions': ['.mkv'],
            'subtitle_extensions': ['.srt']
        }

        groups = scan_source_dir(self.test_dir, config)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['group_name'], 'root')


if __name__ == '__main__':
    unittest.main()
