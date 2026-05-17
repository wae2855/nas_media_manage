#!/usr/bin/env python3
import unittest
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'media_importer'))

from file_copier import FileCopier
from file_mover import (
    apply_filename_template,
    apply_subtitle_template,
    move_to_import,
    detect_subtitle_lang,
    delete_source_files,
    move_with_cross_device_fallback
)


class TestFileCopier(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.copier = FileCopier(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization(self):
        self.assertEqual(self.copier.temp_dir, self.temp_dir)
        self.assertTrue(os.path.exists(self.temp_dir))

    def test_check_disk_space(self):
        result = self.copier.check_disk_space(1024)
        self.assertTrue(result)

    def test_copy_file_with_marker(self):
        src = os.path.join(self.temp_dir, 'source.mkv')
        with open(src, 'w') as f:
            f.write('test content')

        dest = os.path.join(self.temp_dir, 'dest.mkv')
        result = self.copier.copy_file_with_marker(src, dest)

        self.assertEqual(result, dest)
        self.assertTrue(os.path.exists(dest))
        self.assertFalse(os.path.exists(dest + '.copying'))
        with open(dest, 'r') as f:
            self.assertEqual(f.read(), 'test content')

    def test_copy_file_creates_copying_marker(self):
        src = os.path.join(self.temp_dir, 'source.mkv')
        with open(src, 'w') as f:
            f.write('test content')

        dest = os.path.join(self.temp_dir, 'dest.mkv')
        temp_dest = dest + '.copying'

        self.copier.copy_file_with_marker(src, dest)
        self.assertFalse(os.path.exists(temp_dest))

    def test_copy_to_temp_video(self):
        src = os.path.join(self.temp_dir, 'source.mkv')
        with open(src, 'w') as f:
            f.write('video content')

        dest_video = self.copier.copy_to_temp(src, [])
        self.assertEqual(len(dest_video), 1)
        self.assertTrue(os.path.exists(dest_video[0]))

    def test_copy_to_temp_with_subtitles(self):
        video_src = os.path.join(self.temp_dir, 'video.mkv')
        sub_src = os.path.join(self.temp_dir, 'video.zh.srt')

        with open(video_src, 'w') as f:
            f.write('video')
        with open(sub_src, 'w') as f:
            f.write('subtitle')

        dest_files = self.copier.copy_to_temp(video_src, [sub_src])
        self.assertEqual(len(dest_files), 2)

    def test_cleanup_residual_copies(self):
        copying_file = os.path.join(self.temp_dir, 'test.mkv.copying')
        with open(copying_file, 'w') as f:
            f.write('residual')

        self.assertTrue(os.path.exists(copying_file))
        self.copier.cleanup_residual_copies()
        self.assertFalse(os.path.exists(copying_file))

    def test_cleanup_preserves_normal_files(self):
        normal_file = os.path.join(self.temp_dir, 'normal.mkv')
        with open(normal_file, 'w') as f:
            f.write('normal')

        self.copier.cleanup_residual_copies()
        self.assertTrue(os.path.exists(normal_file))

    def test_progress_callback(self):
        src = os.path.join(self.temp_dir, 'source.mkv')
        with open(src, 'w') as f:
            f.write('test content')

        dest = os.path.join(self.temp_dir, 'dest.mkv')
        progress_calls = []

        def callback(copied, total):
            progress_calls.append((copied, total))

        self.copier.copy_file_with_marker(src, dest, callback)
        self.assertTrue(len(progress_calls) > 0)
        self.assertEqual(progress_calls[-1][0], progress_calls[-1][1])


class TestFileMover(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_apply_filename_template_movie(self):
        scraped_info = {
            'title_cn': '盗梦空间',
            'title_en': 'Inception',
            'year': 2010,
            'resolution': '1080p',
            'quality': 'BluRay'
        }
        template = '{title_cn}.{title_en}.{year}.{resolution}.{quality}.{ext}'
        result = apply_filename_template(scraped_info, template, '.mkv')
        self.assertEqual(result, '盗梦空间.Inception.2010.1080p.BluRay.mkv')

    def test_apply_filename_template_tv(self):
        scraped_info = {
            'title_cn': '绝命毒师',
            'title_en': 'Breaking Bad',
            'year': 2008,
            'season': 1,
            'episode': 1
        }
        template = '{title_cn}.{title_en}.{year}.S{season}E{episode}.{ext}'
        result = apply_filename_template(scraped_info, template, '.mkv')
        self.assertEqual(result, '绝命毒师.Breaking Bad.2008.S01E01.mkv')

    def test_apply_filename_template_missing_fields(self):
        scraped_info = {
            'title_cn': '盗梦空间'
        }
        template = '{title_cn}.{title_en}.{year}.{ext}'
        result = apply_filename_template(scraped_info, template, '.mkv')
        self.assertEqual(result, '盗梦空间.mkv')

    def test_apply_subtitle_template(self):
        result = apply_subtitle_template({}, '{video_filename}.{lang}', 'Inception.2010.mkv', 'zh')
        self.assertEqual(result, 'Inception.2010.zh')

    def test_detect_subtitle_lang_zh(self):
        self.assertEqual(detect_subtitle_lang('movie.zh.srt'), 'zh')
        self.assertEqual(detect_subtitle_lang('movie.chs.srt'), 'zh')

    def test_detect_subtitle_lang_en(self):
        self.assertEqual(detect_subtitle_lang('movie.en.srt'), 'en')
        self.assertEqual(detect_subtitle_lang('movie.eng.srt'), 'en')

    def test_detect_subtitle_lang_unknown(self):
        self.assertEqual(detect_subtitle_lang('movie.srt'), 'unknown')
        self.assertEqual(detect_subtitle_lang('movie.fr.srt'), 'unknown')

    def test_move_to_import_creates_directory(self):
        import_dir = os.path.join(self.temp_dir, 'import')
        video_path = os.path.join(self.temp_dir, 'video.mkv')
        with open(video_path, 'w') as f:
            f.write('video')

        scraped_info = {
            'title_cn': '盗梦空间',
            'type': 'movie',
            'year': 2010
        }
        filename_templates = {
            'movie': '{title_cn}.{year}.{ext}'
        }

        result = move_to_import(video_path, [], import_dir, scraped_info, filename_templates)
        self.assertTrue(os.path.exists(import_dir))
        self.assertTrue(os.path.exists(result['video']))

    def test_move_to_import_video_only(self):
        import_dir = os.path.join(self.temp_dir, 'import')
        video_path = os.path.join(self.temp_dir, 'video.mkv')
        with open(video_path, 'w') as f:
            f.write('video')

        scraped_info = {
            'title_cn': '盗梦空间',
            'type': 'movie',
            'year': 2010
        }
        filename_templates = {
            'movie': '{title_cn}.{year}.{ext}'
        }

        result = move_to_import(video_path, [], import_dir, scraped_info, filename_templates)
        self.assertFalse(os.path.exists(video_path))
        self.assertTrue(os.path.exists(result['video']))
        self.assertEqual(len(result['subtitles']), 0)

    def test_move_to_import_with_subtitles(self):
        import_dir = os.path.join(self.temp_dir, 'import')
        video_path = os.path.join(self.temp_dir, 'video.mkv')
        sub_path = os.path.join(self.temp_dir, 'video.zh.srt')

        with open(video_path, 'w') as f:
            f.write('video')
        with open(sub_path, 'w') as f:
            f.write('subtitle')

        scraped_info = {
            'title_cn': '盗梦空间',
            'type': 'movie',
            'year': 2010
        }
        filename_templates = {
            'movie': '{title_cn}.{year}.{ext}',
            'subtitle': '{video_filename}.{lang}.{ext}'
        }

        result = move_to_import(video_path, [sub_path], import_dir, scraped_info, filename_templates)
        self.assertFalse(os.path.exists(video_path))
        self.assertFalse(os.path.exists(sub_path))
        self.assertEqual(len(result['subtitles']), 1)
        self.assertTrue(os.path.exists(result['subtitles'][0]))

    def test_delete_source_files(self):
        files = []
        for i in range(3):
            path = os.path.join(self.temp_dir, f'file{i}.txt')
            with open(path, 'w') as f:
                f.write(f'content{i}')
            files.append(path)

        delete_source_files(files)
        for path in files:
            self.assertFalse(os.path.exists(path))

    def test_move_with_cross_device_fallback_rename(self):
        src = os.path.join(self.temp_dir, 'source.mkv')
        dest = os.path.join(self.temp_dir, 'dest.mkv')

        with open(src, 'w') as f:
            f.write('content')

        result = move_with_cross_device_fallback(src, dest)
        self.assertTrue(result)
        self.assertTrue(os.path.exists(dest))
        self.assertFalse(os.path.exists(src))

    def test_move_with_cross_device_fallback_copy(self):
        src = os.path.join(self.temp_dir, 'source.mkv')
        dest = os.path.join(self.temp_dir, 'dest.mkv')

        with open(src, 'w') as f:
            f.write('content')

        result = move_with_cross_device_fallback(src, dest)
        self.assertTrue(result)
        self.assertTrue(os.path.exists(dest))


if __name__ == '__main__':
    unittest.main()