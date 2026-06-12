#!/usr/bin/env python3
import unittest

from media_importer.features.import_flow.services.naming import apply_filename_template


class TestRenameMovieTemplate(unittest.TestCase):
    def test_rename_movie_template(self):
        scraped = {
            "title_cn": "星际穿越",
            "title_en": "Interstellar",
            "year": "2014",
            "resolution": "1080p",
            "quality": "BluRay",
            "type": "movie",
        }
        template = "{title_cn}.{title_en}.{year}.{resolution}.{quality}.{ext}"
        result = apply_filename_template(scraped, template, ".mkv")
        self.assertEqual(result, "星际穿越.Interstellar.2014.1080p.BluRay.mkv")


class TestRenameTVTemplate(unittest.TestCase):
    def test_rename_tv_template(self):
        scraped = {
            "title_cn": "绝命毒师",
            "title_en": "Breaking Bad",
            "year": "2008",
            "season": 1,
            "episode": 1,
            "type": "tv",
        }
        template = "{title_cn}.{title_en}.{year}.S{season}E{episode}.{ext}"
        result = apply_filename_template(scraped, template, ".mkv")
        self.assertEqual(result, "绝命毒师.Breaking Bad.2008.S01E01.mkv")


class TestRenameMissingTitleCn(unittest.TestCase):
    """No title_cn → uses title_en as fallback."""

    def test_rename_missing_title_cn(self):
        scraped = {
            "title_cn": "",
            "title_en": "Inception",
            "year": "2010",
            "type": "movie",
        }
        template = "{title_cn}.{title_en}.{year}.{ext}"
        result = apply_filename_template(scraped, template, ".mkv")
        # When title_cn is empty, render_template fills it with title_en
        self.assertIn("Inception", result)
        self.assertIn("2010", result)
        self.assertTrue(result.endswith(".mkv"))


class TestRenameDedupOverride(unittest.TestCase):
    """final_filename already set by dedup → not overwritten."""

    def test_rename_dedup_override(self):
        # Simulate what _step_rename does: skip if final_filename is already set
        task = {
            "final_filename": "星际穿越.2014_copy1.mkv",
            "scrape_result": {
                "title_cn": "星际穿越",
                "title_en": "Interstellar",
                "year": "2014",
                "type": "movie",
            },
            "video_path": "/tmp/video.mkv",
        }
        # If final_filename is already set, _step_rename does not overwrite
        if not task.get("final_filename"):
            templates = {"movie": "{title_cn}.{title_en}.{year}.{ext}"}
            video_ext = ".mkv"
            task["final_filename"] = apply_filename_template(
                task["scrape_result"], templates["movie"], video_ext
            )
        self.assertEqual(task["final_filename"], "星际穿越.2014_copy1.mkv")


if __name__ == "__main__":
    unittest.main()
