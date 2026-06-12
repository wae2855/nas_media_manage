#!/usr/bin/env python3
"""Disk full edge case tests.

Tests that OSError(ENOSPC) during copy, import, and recycle
operations are properly handled.
"""
import errno
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from media_importer.features.import_flow.services.file_operations import move_to_import
from media_importer.features.recycle import move_to_recycle


class TestCopyDiskFull(unittest.TestCase):
    """mock shutil.copy2 to raise OSError(ENOSPC) -> error propagates from FileCopier."""

    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.tmp_dir = tempfile.mkdtemp()
        self.imp_dir = tempfile.mkdtemp()
        self.video_path = os.path.join(self.tmp_dir, "movie.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"video_content")

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        shutil.rmtree(self.imp_dir, ignore_errors=True)

    @patch("media_importer.infrastructure.filesystem.file_copier.shutil.copy2",
           side_effect=OSError(errno.ENOSPC, "No space left on device"))
    def test_copy_disk_full(self, mock_copy2):
        from media_importer.infrastructure.filesystem import FileCopier
        copier = FileCopier(self.tmp_dir, {".mkv", ".mp4"})

        with self.assertRaises(OSError):
            copier.copy_file_with_marker(self.video_path, self.imp_dir)


class TestImportDiskFull(unittest.TestCase):
    """mock os.rename and shutil.copy2 to raise OSError(ENOSPC) -> move_to_import raises IOError."""

    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.tmp_dir = tempfile.mkdtemp()
        self.imp_dir = tempfile.mkdtemp()
        self.video_path = os.path.join(self.tmp_dir, "movie.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"video_content")

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        shutil.rmtree(self.imp_dir, ignore_errors=True)

    @patch("media_importer.infrastructure.filesystem.safety.os.rename",
           side_effect=OSError(errno.ENOSPC, "No space left on device"))
    @patch("media_importer.infrastructure.filesystem.safety.shutil.copy2",
           side_effect=OSError(errno.ENOSPC, "No space left on device"))
    def test_import_disk_full(self, mock_copy2, mock_rename):
        with self.assertRaises(IOError):
            move_to_import(
                self.video_path,
                [],
                self.imp_dir,
                {"title_cn": "Test", "title_en": "Test", "year": "2024", "type": "movie"},
                {"movie": "{title_cn}.{ext}"},
                allowed_base_dirs=[self.tmp_dir, self.imp_dir],
                overwrite=False,
            )


class TestDedupRecycleDiskFull(unittest.TestCase):
    """mock os.rename and shutil.copy2 in recycle manager -> returns failure."""

    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.imp_dir = tempfile.mkdtemp()
        self.video_path = os.path.join(self.src_dir, "movie.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"video_content")

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.imp_dir, ignore_errors=True)

    @patch("media_importer.features.recycle.manager.os.rename",
           side_effect=OSError(errno.ENOSPC, "No space left on device"))
    @patch("media_importer.features.recycle.manager.shutil.copy2",
           side_effect=OSError(errno.ENOSPC, "No space left on device"))
    def test_dedup_recycle_disk_full(self, mock_copy2, mock_rename):
        recycle_dir = tempfile.mkdtemp()
        try:
            ok, dest, msg = move_to_recycle(
                self.video_path, recycle_dir,
                reason="dedup",
                source_dir=self.src_dir,
            )
            # move_to_recycle catches OSError and returns (False, "", msg)
            self.assertFalse(ok)
        finally:
            shutil.rmtree(recycle_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
