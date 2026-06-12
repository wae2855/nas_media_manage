#!/usr/bin/env python3
"""File locked edge case tests.

Tests that source or target file locked by another process
is properly handled during copy and import.
"""
import errno
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, mock_open

from media_importer.features.import_flow.services.file_operations import move_to_import
from media_importer.features.import_flow.utils import PipelineError
from media_importer.infrastructure.filesystem import FileCopier


class TestCopyFileLocked(unittest.TestCase):
    """Source file locked by another process -> copy may fail with IOError."""

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

    def test_copy_file_locked(self):
        """When source file is unreadable (locked), copy_file_with_marker raises IOError."""
        copier = FileCopier(self.tmp_dir, {".mkv", ".mp4"})

        # Mock check_read_permission to simulate file locked
        with patch("media_importer.infrastructure.filesystem.file_copier.check_read_permission",
                   return_value=(False, "Permission denied - file locked")):
            with self.assertRaises(IOError):
                copier.copy_file_with_marker(self.video_path, self.imp_dir)


class TestImportFileLocked(unittest.TestCase):
    """Target file locked -> safe_move returns failure -> move_to_import raises IOError."""

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
           side_effect=PermissionError("Permission denied - target locked"))
    @patch("media_importer.infrastructure.filesystem.safety.shutil.copy2",
           side_effect=PermissionError("Permission denied - target locked"))
    def test_import_file_locked(self, mock_copy2, mock_rename):
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


if __name__ == "__main__":
    unittest.main()
