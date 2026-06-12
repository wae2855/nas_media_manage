#!/usr/bin/env python3
import os
import shutil
import stat
import tempfile
import unittest

from media_importer.infrastructure.filesystem import FileCopier
from media_importer.features.import_flow.utils import PipelineError


MEDIA_EXTS = {".mkv", ".mp4", ".avi", ".ts", ".srt", ".ass"}


class TestCopySingleFile(unittest.TestCase):
    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.tmp_dir = tempfile.mkdtemp()
        self.video_path = os.path.join(self.src_dir, "movie.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"fake_video_content_12345")

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_copy_single_file(self):
        copier = FileCopier(self.tmp_dir, MEDIA_EXTS)
        copied = copier.copy_to_temp(self.video_path, [])
        self.assertEqual(len(copied), 1)
        dest = copied[0]
        self.assertTrue(os.path.isfile(dest))
        with open(self.video_path, "rb") as sf, open(dest, "rb") as df:
            self.assertEqual(sf.read(), df.read())


class TestCopyWithSubtitles(unittest.TestCase):
    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.tmp_dir = tempfile.mkdtemp()
        self.video_path = os.path.join(self.src_dir, "movie.mkv")
        self.sub1 = os.path.join(self.src_dir, "movie.srt")
        self.sub2 = os.path.join(self.src_dir, "movie.ass")
        with open(self.video_path, "wb") as f:
            f.write(b"video_data")
        with open(self.sub1, "wb") as f:
            f.write(b"subtitle_srt")
        with open(self.sub2, "wb") as f:
            f.write(b"subtitle_ass")

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_copy_with_subtitles(self):
        copier = FileCopier(self.tmp_dir, MEDIA_EXTS)
        copied = copier.copy_to_temp(self.video_path, [self.sub1, self.sub2])
        self.assertEqual(len(copied), 3)
        for path in copied:
            self.assertTrue(os.path.isfile(path), f"Copied file should exist: {path}")


class TestCopySourceMissing(unittest.TestCase):
    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.tmp_dir = tempfile.mkdtemp()
        self.missing_path = os.path.join(self.src_dir, "nonexistent.mkv")

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_copy_source_missing(self):
        copier = FileCopier(self.tmp_dir, MEDIA_EXTS)
        with self.assertRaises(IOError):
            copier.copy_to_temp(self.missing_path, [])


class TestCopyTempNoWritePerm(unittest.TestCase):
    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.tmp_dir = tempfile.mkdtemp()
        self.video_path = os.path.join(self.src_dir, "movie.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"video_data")
        # Remove write permission from temp dir
        os.chmod(self.tmp_dir, stat.S_IRUSR | stat.S_IXUSR)

    def tearDown(self):
        # Restore permissions before cleanup
        try:
            os.chmod(self.tmp_dir, stat.S_IRWXU)
        except OSError:
            pass
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_copy_temp_no_write_perm(self):
        copier = FileCopier(self.tmp_dir, MEDIA_EXTS)
        with self.assertRaises(IOError):
            copier.copy_to_temp(self.video_path, [])


class TestCopyProgressCallback(unittest.TestCase):
    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.tmp_dir = tempfile.mkdtemp()
        # Create a file larger than 1MB to ensure at least one chunk
        self.video_path = os.path.join(self.src_dir, "bigmovie.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"x" * (2 * 1024 * 1024 + 100))

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_copy_progress_callback(self):
        copier = FileCopier(self.tmp_dir, MEDIA_EXTS)
        progress_calls = []

        def progress_cb(copied, total):
            progress_calls.append((copied, total))

        copier.copy_to_temp(self.video_path, [], progress_callback=progress_cb)
        self.assertGreater(len(progress_calls), 0, "Progress callback should be called")
        # Last call should report total bytes
        last_copied, last_total = progress_calls[-1]
        self.assertEqual(last_copied, last_total)
        self.assertGreater(last_total, 0)


if __name__ == "__main__":
    unittest.main()
