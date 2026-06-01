#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.api.recycle_handlers import (
    delete_from_recycle as api_delete_from_recycle,
)
from media_importer.api.recycle_handlers import (
    list_recycle_dir as api_list_recycle_dir,
)
from media_importer.api.recycle_handlers import (
    restore_from_recycle as api_restore_from_recycle,
)
from media_importer.core import safety
from media_importer.core.recycle import (
    delete_from_recycle as core_delete_from_recycle,
)
from media_importer.core.recycle import list_recycle_dir as core_list_recycle_dir
from media_importer.core.recycle import move_to_recycle as core_move_to_recycle
from media_importer.core.recycle import (
    move_to_recycle_with_companions as core_move_to_recycle_with_companions,
)
from media_importer.core.recycle import recycle_cleanup as core_recycle_cleanup
from media_importer.core.recycle import restore_from_recycle as core_restore_from_recycle
from media_importer.core.recycle.manager import (
    _determine_source_zone,
    _recycle_subpath,
)
from media_importer.domains.recycle import (
    delete_from_recycle,
    list_recycle_dir,
    move_to_recycle,
    move_to_recycle_with_companions,
    recycle_cleanup,
    restore_from_recycle,
)
from media_importer.domains.recycle import browser as domain_browser
from media_importer.domains.recycle import manager as domain_manager
import media_importer.core.recycle.browser as legacy_browser
import media_importer.core.recycle.manager as legacy_manager


class TestRecycleDomainCompatibility(unittest.TestCase):
    def test_domain_reexports_existing_public_objects(self):
        self.assertIs(core_move_to_recycle, move_to_recycle)
        self.assertIs(
            core_move_to_recycle_with_companions,
            move_to_recycle_with_companions,
        )
        self.assertIs(core_list_recycle_dir, list_recycle_dir)
        self.assertIs(core_restore_from_recycle, restore_from_recycle)
        self.assertIs(core_delete_from_recycle, delete_from_recycle)
        self.assertIs(core_recycle_cleanup, recycle_cleanup)

    def test_legacy_modules_alias_domain_modules(self):
        self.assertIs(legacy_manager, domain_manager)
        self.assertIs(legacy_browser, domain_browser)
        self.assertIs(legacy_manager.move_to_recycle, move_to_recycle)
        self.assertIs(legacy_browser.list_recycle_dir, list_recycle_dir)

    def test_safety_and_api_keep_recycle_public_functions(self):
        self.assertIs(safety.move_to_recycle, move_to_recycle)
        self.assertIs(safety.list_recycle_dir, list_recycle_dir)
        self.assertIs(safety.restore_from_recycle, restore_from_recycle)
        self.assertIs(safety.delete_from_recycle, delete_from_recycle)
        self.assertIs(api_list_recycle_dir, list_recycle_dir)
        self.assertIs(api_restore_from_recycle, restore_from_recycle)
        self.assertIs(api_delete_from_recycle, delete_from_recycle)

    def test_legacy_private_helpers_still_available(self):
        subpath = _recycle_subpath(
            "/vol1/downloads/movie.mkv",
            "/vol1/downloads",
            [],
        )
        zone = _determine_source_zone(
            "/vol1/import/movie.mkv",
            "/vol1/downloads",
            ["/vol1/import"],
        )

        self.assertIn("[源目录]", subpath)
        self.assertEqual(zone, "import")

    def test_domain_move_and_list_preserve_metadata_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = os.path.join(tmpdir, "source")
            recycle_dir = os.path.join(tmpdir, "recycle")
            os.makedirs(source_dir)
            os.makedirs(recycle_dir)
            src = os.path.join(source_dir, "movie.mkv")
            with open(src, "w") as f:
                f.write("video")

            ok, dest, _ = move_to_recycle(
                src,
                recycle_dir,
                reason="domain_test",
                task_id="task-1",
                source_dir=source_dir,
            )
            listing = list_recycle_dir(recycle_dir)

            self.assertTrue(ok)
            self.assertTrue(os.path.exists(dest))
            self.assertTrue(os.path.exists(dest + ".meta"))
            with open(dest + ".meta", encoding="utf-8") as f:
                meta = json.load(f)
            self.assertEqual(meta["reason"], "domain_test")
            self.assertEqual(meta["task_id"], "task-1")
            self.assertEqual(meta["source_zone"], "source")
            self.assertEqual(listing["total"], 1)
            self.assertEqual(listing["items"][0]["reason"], "domain_test")


if __name__ == "__main__":
    unittest.main()
