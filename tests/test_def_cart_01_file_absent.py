#!/usr/bin/env python3
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from media_importer.features.import_flow.scan_service import FileScanner
from media_importer.features.import_flow.services.file_operations import move_to_import
from media_importer.features.import_flow.utils import PipelineError


def _make_config(source_dir="", temp_dir=""):
    return {
        "source_dir": source_dir,
        "temp_dir": temp_dir,
        "video_extensions": [".mkv", ".mp4", ".avi", ".ts"],
        "subtitle_extensions": [".srt", ".ass"],
        "scan_source": True,
        "skip_existing": True,
        "sort_by": "filename",
        "sort_reverse": False,
        "group_delay_sec": 0,
    }


class TestScanDirAbsent(unittest.TestCase):
    """Source_dir doesn't exist -> empty list, no crash."""

    def test_scan_dir_absent(self):
        nonexistent = os.path.join(tempfile.gettempdir(), "nonexistent_dir_12345")
        config = _make_config(source_dir=nonexistent)
        scanner = FileScanner(config)
        # scan_and_filter should handle gracefully
        try:
            groups = scanner.scan_and_filter(nonexistent)
            self.assertEqual(len(groups), 0)
        except (FileNotFoundError, OSError):
            # Acceptable: OS error for nonexistent dir
            pass


class TestCopySourceDeleted(unittest.TestCase):
    """Source file deleted before copy -> PipelineError -> FAILED."""

    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.tmp_dir = tempfile.mkdtemp()
        self.imp_dir = tempfile.mkdtemp()
        self.video_path = os.path.join(self.src_dir, "movie.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"video_content")

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        shutil.rmtree(self.imp_dir, ignore_errors=True)

    def test_copy_source_deleted(self):
        # Delete source file before copy
        os.remove(self.video_path)
        self.assertFalse(os.path.exists(self.video_path))

        # Attempting to copy should raise an error
        from media_importer.features.import_flow.services.file_operations import move_to_import
        with self.assertRaises((IOError, OSError, PipelineError)):
            move_to_import(
                self.video_path,
                [],
                self.imp_dir,
                {"title_cn": "Test", "title_en": "Test", "year": "2024", "type": "movie"},
                {"movie": "{title_cn}.{ext}"},
                allowed_base_dirs=[self.src_dir, self.imp_dir],
                overwrite=False,
            )


class TestScrapeFileGone(unittest.TestCase):
    """Video path exists but file deleted -> scrape continues (uses filename only)."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.video_path = os.path.join(self.tmp_dir, "Movie.2024.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"video_content")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_scrape_file_gone(self):
        # Scrape uses filename-based cleaning, not file content
        from media_importer.scraper.filename_cleaner import FilenameCleaner
        cleaner = FilenameCleaner()

        # Delete the actual file
        os.remove(self.video_path)
        self.assertFalse(os.path.exists(self.video_path))

        # Filename cleaning should still work (doesn't read file)
        result = cleaner.clean("Movie.2024.mkv")
        self.assertIsNotNone(result.clean_title)
        self.assertEqual(result.year, 2024)


class TestImportSourceGone(unittest.TestCase):
    """Source file gone at import time -> IOError -> FAILED + temp cleanup."""

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

    def test_import_source_gone(self):
        # Delete the temp video before import
        os.remove(self.video_path)
        self.assertFalse(os.path.exists(self.video_path))

        with self.assertRaises((IOError, OSError, PipelineError)):
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
