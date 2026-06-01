#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.api.source_cleaner_handlers import SourceCleaner as ApiSourceCleaner
from media_importer.core.db.cleaner_repo import (
    get_cleaner_records as core_get_cleaner_records,
)
from media_importer.core.db.cleaner_repo import (
    save_cleaner_record as core_save_cleaner_record,
)
from media_importer.domains.source_cleaning import SourceCleaner
from media_importer.domains.source_cleaning import cleaner as domain_cleaner
from media_importer.domains.source_cleaning.records import (
    get_cleaner_records,
    save_cleaner_record,
)
from media_importer.storage.source_cleaner import SourceCleaner as StorageSourceCleaner
import media_importer.storage.source_cleaner as legacy_cleaner


class TestSourceCleaningDomainCompatibility(unittest.TestCase):
    def test_domain_reexports_existing_public_objects(self):
        self.assertIs(StorageSourceCleaner, SourceCleaner)
        self.assertIs(ApiSourceCleaner, SourceCleaner)
        self.assertIs(save_cleaner_record, core_save_cleaner_record)
        self.assertIs(get_cleaner_records, core_get_cleaner_records)

    def test_legacy_storage_module_aliases_domain_module_for_patch_paths(self):
        self.assertIs(legacy_cleaner, domain_cleaner)
        self.assertIs(legacy_cleaner.SourceCleaner, SourceCleaner)

    def test_preview_keeps_source_cleaner_behavior_under_domain_entry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = os.path.join(tmpdir, "source")
            recycle_dir = os.path.join(tmpdir, "recycle")
            os.makedirs(source_dir)
            os.makedirs(recycle_dir)
            junk_path = os.path.join(source_dir, "readme.txt")
            movie_path = os.path.join(source_dir, "movie.mkv")
            with open(junk_path, "w") as f:
                f.write("ad")
            with open(movie_path, "w") as f:
                f.write("video")

            cleaner = SourceCleaner({
                "source_dir": source_dir,
                "source_policy": {"recycle_dir": recycle_dir},
                "video_extensions": [".mkv"],
                "subtitle_extensions": [".srt"],
                "source_cleaner": {
                    "cleanup_mode": "media_only",
                    "ai_enabled": False,
                    "junk_video_max_size_mb": 0,
                    "delete_extensions": [".txt"],
                },
            })

            items = cleaner.preview()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["path"], junk_path)
        self.assertEqual(items[0]["category"], "delete_extension")

    def test_old_patch_path_still_controls_execute_recycle_call(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = os.path.join(tmpdir, "source")
            recycle_dir = os.path.join(tmpdir, "recycle")
            os.makedirs(source_dir)
            os.makedirs(recycle_dir)
            junk_path = os.path.join(source_dir, "readme.txt")
            with open(junk_path, "w") as f:
                f.write("ad")

            cleaner = SourceCleaner({
                "source_dir": source_dir,
                "source_policy": {"recycle_dir": recycle_dir},
                "video_extensions": [".mkv"],
                "subtitle_extensions": [".srt"],
                "source_cleaner": {
                    "cleanup_mode": "media_only",
                    "ai_enabled": False,
                    "junk_video_max_size_mb": 0,
                    "delete_extensions": [".txt"],
                },
            })

            with patch(
                "media_importer.storage.source_cleaner.move_to_recycle",
                return_value=(True, os.path.join(recycle_dir, "readme.txt"), "ok"),
            ) as patched:
                record = cleaner.execute()

        self.assertEqual(record["total_files"], 1)
        patched.assert_called_once()
        self.assertEqual(patched.call_args.args[0], junk_path)


if __name__ == "__main__":
    unittest.main()
