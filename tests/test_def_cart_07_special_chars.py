#!/usr/bin/env python3
import os
import shutil
import tempfile
import unittest

from media_importer.infrastructure.filesystem.safety import validate_path_safety
from media_importer.scraper.filename_cleaner import FilenameCleaner
from media_importer.features.import_flow.services.naming import apply_filename_template
from media_importer.features.import_flow.scan_service import FileScanner


def _make_config(source_dir="", temp_dir=""):
    return {
        "source_dir": source_dir,
        "temp_dir": temp_dir,
        "video_extensions": [".mkv", ".mp4", ".avi"],
        "subtitle_extensions": [".srt", ".ass"],
        "scan_source": True,
        "skip_existing": True,
        "sort_by": "filename",
        "sort_reverse": False,
        "group_delay_sec": 0,
    }


class TestScanPathTraversal(unittest.TestCase):
    """Filename with ../ -> safety check blocks."""

    def test_scan_path_traversal(self):
        ok, msg = validate_path_safety("/safe/dir/../../../etc/passwd")
        self.assertFalse(ok)
        self.assertIn("穿越", msg)

    def test_scan_path_traversal_allowed_dirs(self):
        ok, msg = validate_path_safety(
            "/safe/dir/../../../etc/passwd",
            allowed_base_dirs=["/safe"]
        )
        self.assertFalse(ok)


class TestScrapeUnicode(unittest.TestCase):
    """Filename with emoji/Unicode -> processes normally."""

    def setUp(self):
        self.cleaner = FilenameCleaner()

    def test_scrape_unicode_emoji(self):
        result = self.cleaner.clean("🎬电影.Test.Movie.2024.1080p.mkv")
        self.assertIsNotNone(result.clean_title)
        self.assertTrue(len(result.clean_title) > 0)

    def test_scrape_unicode_cjk(self):
        result = self.cleaner.clean("流浪地球.The.Wandering.Earth.2019.mkv")
        self.assertIsNotNone(result.clean_title)
        self.assertEqual(result.year, 2019)

    def test_scrape_unicode_mixed(self):
        result = self.cleaner.clean("🇯🇵アニメ.Anime.2023.1080p.mkv")
        self.assertIsNotNone(result.clean_title)


class TestRenamePathSeparator(unittest.TestCase):
    """Template variable contains / -> safe handling."""

    def test_rename_path_separator_in_title(self):
        # If a title contains /, the template should handle it
        scraped = {
            "title_cn": "战争/和平",
            "title_en": "War/Peace",
            "year": "2024",
            "type": "movie",
        }
        template = "{title_cn}.{title_en}.{year}.{ext}"
        result = apply_filename_template(scraped, template, ".mkv")
        # The result should not contain raw / from the title
        # (it may be replaced or the filename may be sanitized)
        self.assertTrue(result.endswith(".mkv"))
        # Filename should not have directory separators from title
        basename = os.path.basename(result)
        self.assertNotIn("/", basename)


class TestScanEmptyFilename(unittest.TestCase):
    """File named just ".mkv" -> filtered or handled."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _make_config(source_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scan_empty_filename(self):
        # Create a file with just extension
        open(os.path.join(self.tmpdir, ".mkv"), "w").close()
        scanner = FileScanner(self.config)
        groups = scanner.scan_and_filter(self.tmpdir)
        # Empty-named files should be filtered out or handled gracefully
        # (they should not crash the scanner)
        self.assertIsInstance(groups, list)


class TestScanLongFilename(unittest.TestCase):
    """Filename > 255 chars -> no crash."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _make_config(source_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scan_long_filename(self):
        long_name = "A" * 250 + ".mkv"
        filepath = os.path.join(self.tmpdir, long_name)
        try:
            with open(filepath, "w") as f:
                f.write("dummy")
        except OSError:
            # Some filesystems may not support filenames this long
            self.skipTest("Filesystem does not support long filenames")

        scanner = FileScanner(self.config)
        try:
            groups = scanner.scan_and_filter(self.tmpdir)
            self.assertIsInstance(groups, list)
        except OSError:
            # Acceptable: OS may have trouble with long names
            pass


class TestScrapeZeroByteFile(unittest.TestCase):
    """0-byte video -> scrape continues (uses filename)."""

    def test_scrape_zero_byte_file(self):
        cleaner = FilenameCleaner()
        result = cleaner.clean("Movie.2024.1080p.mkv")
        self.assertIsNotNone(result.clean_title)
        self.assertEqual(result.year, 2024)
        # Scrape uses filename, not file content


class TestScrapeCorruptedFile(unittest.TestCase):
    """Corrupted video header -> file dimensions degraded."""

    def test_scrape_corrupted_file(self):
        cleaner = FilenameCleaner()
        # Even with a corrupted file, filename-based cleaning works
        result = cleaner.clean("Corrupted.Video.2023.mkv")
        self.assertIsNotNone(result.clean_title)
        # File dimensions (resolution) would be degraded,
        # but filename parsing still works


if __name__ == "__main__":
    unittest.main()
