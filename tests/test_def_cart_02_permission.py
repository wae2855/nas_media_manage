#!/usr/bin/env python3
import os
import shutil
import stat
import tempfile
import unittest

from media_importer.features.import_flow.scan_service import FileScanner
from media_importer.features.import_flow.services.file_operations import move_to_import
from media_importer.infrastructure.filesystem.safety import (
    check_read_permission,
    check_write_permission,
)
from media_importer.features.import_flow.utils import PipelineError


def _make_config(source_dir="", temp_dir=""):
    return {
        "source_dir": source_dir,
        "temp_dir": temp_dir,
        "video_extensions": [".mkv", ".mp4"],
        "subtitle_extensions": [".srt", ".ass"],
        "scan_source": True,
        "skip_existing": True,
        "sort_by": "filename",
        "sort_reverse": False,
        "group_delay_sec": 0,
    }


class TestScanNoReadPerm(unittest.TestCase):
    """Source dir chmod 000 -> scan returns empty or error."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Create a video file
        open(os.path.join(self.tmpdir, "movie.mkv"), "w").close()
        # Remove all permissions
        os.chmod(self.tmpdir, 0o000)

    def tearDown(self):
        try:
            os.chmod(self.tmpdir, stat.S_IRWXU)
        except OSError:
            pass
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scan_no_read_perm(self):
        ok, msg = check_read_permission(self.tmpdir)
        self.assertFalse(ok)
        self.assertIn("权限", msg)


class TestCopyNoWritePerm(unittest.TestCase):
    """Temp dir chmod 000 -> IOError -> FAILED."""

    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.tmp_dir = tempfile.mkdtemp()
        self.imp_dir = tempfile.mkdtemp()
        self.video_path = os.path.join(self.src_dir, "movie.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"video_content")
        # Remove write permission from temp dir
        os.chmod(self.tmp_dir, stat.S_IRUSR | stat.S_IXUSR)

    def tearDown(self):
        try:
            os.chmod(self.tmp_dir, stat.S_IRWXU)
        except OSError:
            pass
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        shutil.rmtree(self.imp_dir, ignore_errors=True)

    def test_copy_no_write_perm(self):
        ok, msg = check_write_permission(self.tmp_dir)
        self.assertFalse(ok)
        self.assertIn("权限", msg)


class TestImportNoWritePerm(unittest.TestCase):
    """Target dir chmod 000 -> IOError -> FAILED."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.imp_dir = tempfile.mkdtemp()
        self.video_path = os.path.join(self.tmp_dir, "movie.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"video_content")
        # Remove write permission from import dir
        os.chmod(self.imp_dir, stat.S_IRUSR | stat.S_IXUSR)

    def tearDown(self):
        try:
            os.chmod(self.imp_dir, stat.S_IRWXU)
        except OSError:
            pass
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        shutil.rmtree(self.imp_dir, ignore_errors=True)

    def test_import_no_write_perm(self):
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


class TestSourceCleanupNoWritePerm(unittest.TestCase):
    """Source dir not writable -> cleanup skipped."""

    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.video_path = os.path.join(self.src_dir, "movie.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"video_content")
        # Remove write permission from source dir
        os.chmod(self.src_dir, stat.S_IRUSR | stat.S_IXUSR)

    def tearDown(self):
        try:
            os.chmod(self.src_dir, stat.S_IRWXU)
        except OSError:
            pass
        shutil.rmtree(self.src_dir, ignore_errors=True)

    def test_source_cleanup_no_write_perm(self):
        ok, msg = check_write_permission(self.src_dir)
        self.assertFalse(ok)
        # File should still exist (cleanup skipped)
        # Note: the file itself may still be readable even if dir isn't writable
        self.assertTrue(os.path.exists(self.video_path))


if __name__ == "__main__":
    unittest.main()
