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
from media_importer.features.source_cleaning import SourceCleaner, collect_task_paths, execute_source_cleaning
from media_importer.features.source_cleaning.records import (
    get_cleaner_records,
    save_cleaner_record,
)


class TestSourceCleaningFeatureCompatibility(unittest.TestCase):
    def test_feature_reexports_existing_public_objects(self):
        self.assertIs(ApiSourceCleaner, SourceCleaner)
        self.assertIs(save_cleaner_record, core_save_cleaner_record)
        self.assertIs(get_cleaner_records, core_get_cleaner_records)

    def test_preview_keeps_source_cleaner_behavior_under_feature_entry(self):
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
                "media_importer.features.source_cleaning.cleaner.move_to_recycle",
                return_value=(True, os.path.join(recycle_dir, "readme.txt"), "ok"),
            ) as patched:
                record = cleaner.execute()

        self.assertEqual(record["total_files"], 1)
        patched.assert_called_once()
        self.assertEqual(patched.call_args.args[0], junk_path)

    def test_collect_task_paths_merges_video_import_and_subtitle_locations(self):
        tasks = [
            {
                "source_path": "/source/a.mkv",
                "video_path": "/temp/a.mkv",
                "import_video_path": "/library/a.mkv",
                "subtitle_files": [
                    "/temp/a.srt",
                    {"source_path": "/source/a.ass", "target_path": "/library/a.ass"},
                ],
            }
        ]

        with patch(
            "media_importer.features.source_cleaning.application_service.list_all_tasks",
            return_value=tasks,
        ):
            paths = collect_task_paths(conn=object())

        self.assertEqual(
            paths,
            {
                "/source/a.mkv",
                "/temp/a.mkv",
                "/library/a.mkv",
                "/temp/a.srt",
                "/library/a.ass",
            },
        )

    def test_execute_source_cleaning_returns_permission_error_before_running_cleaner(self):
        config = {
            "source_policy": {"mode": "preserve_media", "recycle_dir": "/recycle"},
            "source_cleaner": {"enabled": True},
        }

        result = execute_source_cleaning(
            config=config,
            conn=object(),
            permission_check=lambda path, need_write=True: {"ok": False, "message": "denied"},
        )

        self.assertFalse(result.ok)
        self.assertIn("回收站目录权限不足", result.message)
        self.assertIsNone(result.record)

    # Requirement: REQ-20260831-004019
    def test_execute_source_cleaning_disabled_never_runs_cleaner(self):
        with patch(
            "media_importer.features.source_cleaning.application_service.SourceCleaner"
        ) as cleaner:
            result = execute_source_cleaning(
                config={
                    "source_dir": "/source",
                    "source_policy": {"mode": "preserve_all", "recycle_dir": "/recycle"},
                    "source_cleaner": {"enabled": False},
                },
                conn=object(),
            )

        self.assertFalse(result.ok)
        self.assertIn("未启用", result.message)
        cleaner.assert_not_called()

    # Requirement: REQ-20260831-004019
    def test_execute_source_cleaning_blocks_mount_identity_change(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = {}
            for name in ("source", "temp", "recycle", "library"):
                path = os.path.join(tmpdir, name)
                os.makedirs(path)
                paths[name] = path
            config = {
                "source_dir": paths["source"],
                "temp_dir": paths["temp"],
                "source_policy": {"mode": "preserve_media", "recycle_dir": paths["recycle"]},
                "source_cleaner": {"enabled": True},
                "library_roots": [
                    {"id": "main", "name": "主片库", "path": paths["library"], "enabled": True},
                ],
                "default_library_root_id": "main",
                "library_root": paths["library"],
                "storage_identities": {
                    "source": {
                        "realpath": paths["source"],
                        "device": -1,
                        "mount_source": "stale-mount",
                    },
                },
            }
            with patch(
                "media_importer.features.source_cleaning.application_service.SourceCleaner"
            ) as cleaner:
                result = execute_source_cleaning(config, conn=object())

        self.assertFalse(result.ok)
        self.assertIn("挂载身份", result.message)
        cleaner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
