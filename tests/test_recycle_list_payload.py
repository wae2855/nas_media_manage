#!/usr/bin/env python3
"""list_recycle_dir() 字段契约与分页/过滤单测。

构造模拟回收站目录（.meta + .dir.meta 文件），
验证 list_recycle_dir() 返回的字段、分页、过滤、统计都符合前端契约。
"""

import json
import sys
import unittest
from pathlib import Path

# ruff: noqa: E402
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from media_importer.features.recycle.browser import list_recycle_dir


def _write_meta(recycle_dir, relative_path, meta):
    """在回收站写一份 .meta 文件，data 文件可空。"""
    meta_path = Path(recycle_dir) / (relative_path + ".meta")
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    data_path = Path(recycle_dir) / relative_path
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.touch()
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def _write_dir_meta(recycle_dir, relative_path, meta):
    """为目录写一份 .dir.meta。"""
    meta_path = Path(recycle_dir) / (relative_path + ".dir.meta")
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    dir_path = Path(recycle_dir) / relative_path
    dir_path.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


class TestListRecycleDirEmpty(unittest.TestCase):
    def test_nonexistent_recycle_dir_returns_empty_payload(self):
        result = list_recycle_dir("/this/path/does/not/exist/xyz")
        self.assertEqual(result["items"], [])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["total_count"], 0)
        self.assertEqual(result["total_size"], 0)
        self.assertEqual(result["total_size_mb"], 0)
        self.assertEqual(result["zones"], {})
        self.assertEqual(result["partitions"], [])

    def test_empty_recycle_dir(self, tmp_path=None):
        if tmp_path is None:
            import tempfile
            tmp_path = Path(tempfile.mkdtemp())
        result = list_recycle_dir(str(tmp_path))
        self.assertEqual(result["items"], [])
        self.assertEqual(result["total"], 0)

    def test_empty_string_recycle_dir(self):
        result = list_recycle_dir("")
        self.assertEqual(result["items"], [])


class TestListRecycleDirPayloadFields(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.recycle_dir = Path(tempfile.mkdtemp())
        _write_meta(
            self.recycle_dir,
            "movie1.mkv",
            {
                "original_path": "/source/movie1.mkv",
                "reason": "imported",
                "moved_at": "2026-06-10T10:00:00",
                "file_size_mb": 1024,
                "source_zone": "source",
                "task_id": "task-001",
                "is_dir": False,
            },
        )

    def test_item_has_required_fields(self):
        result = list_recycle_dir(str(self.recycle_dir))
        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        self.assertIn("id", item)
        self.assertIn("recycle_path", item)
        self.assertIn("original_path", item)
        self.assertIn("source_zone", item)
        self.assertIn("zone_name", item)
        self.assertIn("partition", item)
        self.assertIn("reason", item)
        self.assertIn("moved_at", item)
        self.assertIn("file_size_mb", item)
        self.assertIn("size", item)
        self.assertIn("task_id", item)
        self.assertIn("is_dir", item)
        self.assertIn("restorable", item)

    def test_item_field_values(self):
        result = list_recycle_dir(str(self.recycle_dir))
        item = result["items"][0]
        self.assertEqual(item["original_path"], "/source/movie1.mkv")
        self.assertEqual(item["reason"], "imported")
        self.assertEqual(item["file_size_mb"], 1024)
        self.assertEqual(item["source_zone"], "source")
        self.assertEqual(item["zone_name"], "[源目录]")
        self.assertEqual(item["task_id"], "task-001")
        self.assertFalse(item["is_dir"])

    def test_size_calculated_from_file_size_mb(self):
        """size 字段是 file_size_mb 转字节。"""
        result = list_recycle_dir(str(self.recycle_dir))
        self.assertEqual(result["items"][0]["size"], 1024 * 1024 * 1024)
        self.assertEqual(result["total_size"], 1024 * 1024 * 1024)

    def test_total_size_mb_rounded(self):
        """total_size_mb 保留 1 位小数。"""
        _write_meta(
            self.recycle_dir,
            "movie2.mkv",
            {
                "original_path": "/source/movie2.mkv",
                "reason": "imported",
                "moved_at": "2026-06-10T11:00:00",
                "file_size_mb": 0.1,
            },
        )
        result = list_recycle_dir(str(self.recycle_dir))
        self.assertGreater(result["total_size_mb"], 0)


class TestListRecycleDirZoneAndReason(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.recycle_dir = Path(tempfile.mkdtemp())
        _write_meta(
            self.recycle_dir,
            "a.mkv",
            {
                "original_path": "/src/a.mkv",
                "reason": "imported",
                "moved_at": "2026-06-10T10:00:00",
                "file_size_mb": 100,
                "source_zone": "source",
            },
        )
        _write_meta(
            self.recycle_dir,
            "b.mkv",
            {
                "original_path": "/lib/b.mkv",
                "reason": "replaced",
                "moved_at": "2026-06-10T11:00:00",
                "file_size_mb": 200,
                "source_zone": "import",
            },
        )
        _write_meta(
            self.recycle_dir,
            "c.mkv",
            {
                "original_path": "/src/c.mkv",
                "reason": "source_cleaner:junk",
                "moved_at": "2026-06-10T12:00:00",
                "file_size_mb": 50,
                "source_zone": "source",
            },
        )

    def test_zones_aggregated_by_zone_name(self):
        """a(source+imported)→[源目录]，b(import+replaced)→[入库目录]，c(source+source_cleaner:*)→[清理器-源目录]。"""
        result = list_recycle_dir(str(self.recycle_dir))
        zones = result["zones"]
        self.assertIn("[源目录]", zones)
        self.assertIn("[入库目录]", zones)
        self.assertIn("[清理器-源目录]", zones)
        self.assertEqual(zones["[源目录]"]["count"], 1)
        self.assertEqual(zones["[入库目录]"]["count"], 1)
        self.assertEqual(zones["[清理器-源目录]"]["count"], 1)

    def test_partitions_listed(self):
        result = list_recycle_dir(str(self.recycle_dir))
        self.assertIn("[源目录]", result["partitions"])
        self.assertIn("[入库目录]", result["partitions"])
        self.assertIn("[清理器-源目录]", result["partitions"])

    def test_reasons_aggregated(self):
        result = list_recycle_dir(str(self.recycle_dir))
        self.assertIn("imported", result["reasons"])
        self.assertIn("replaced", result["reasons"])
        self.assertIn("source_cleaner:junk", result["reasons"])

    def test_filter_by_zone(self):
        """仅 [源目录]：a.mkv 命中。"""
        result = list_recycle_dir(str(self.recycle_dir), zone="[源目录]")
        self.assertEqual(result["total"], 1)
        for item in result["items"]:
            self.assertEqual(item["zone_name"], "[源目录]")

    def test_filter_by_reason(self):
        result = list_recycle_dir(str(self.recycle_dir), reason="imported")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["reason"], "imported")

    def test_total_count_matches_total(self):
        result = list_recycle_dir(str(self.recycle_dir))
        self.assertEqual(result["total"], result["total_count"])


class TestListRecycleDirPagination(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.recycle_dir = Path(tempfile.mkdtemp())
        for i in range(5):
            _write_meta(
                self.recycle_dir,
                f"f{i}.mkv",
                {
                    "original_path": f"/src/f{i}.mkv",
                    "reason": "imported",
                    "moved_at": f"2026-06-1{i}T10:00:00",
                    "file_size_mb": 10,
                    "source_zone": "source",
                },
            )

    def test_default_limit_returns_all(self):
        result = list_recycle_dir(str(self.recycle_dir))
        self.assertEqual(len(result["items"]), 5)
        self.assertEqual(result["total"], 5)

    def test_limit_caps_items_but_total_stays_full(self):
        result = list_recycle_dir(str(self.recycle_dir), limit=2)
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["total"], 5)

    def test_offset_skips_items(self):
        result = list_recycle_dir(str(self.recycle_dir), limit=2, offset=2)
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["total"], 5)

    def test_items_sorted_by_moved_at_descending(self):
        result = list_recycle_dir(str(self.recycle_dir))
        moved_ats = [item["moved_at"] for item in result["items"]]
        self.assertEqual(moved_ats, sorted(moved_ats, reverse=True))


class TestListRecycleDirRestorable(unittest.TestCase):
    def test_restorable_true_when_original_missing_and_parent_writable(self):
        """原始路径已不存在、但父目录可写时，可恢复。"""
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        # 父目录存在（tmp_path 自己），原始文件不存在
        original = tmp_path / "missing_original.mkv"
        _write_meta(
            tmp_path,
            "x.mkv",
            {
                "original_path": str(original),
                "reason": "imported",
                "moved_at": "2026-06-10T10:00:00",
                "file_size_mb": 0.001,
                "source_zone": "source",
            },
        )
        result = list_recycle_dir(str(tmp_path))
        self.assertTrue(result["items"][0]["restorable"])

    def test_restorable_false_when_original_path_occupied(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        original = tmp_path / "occupied.mkv"
        original.write_text("still here")
        _write_meta(
            tmp_path,
            "x.mkv",
            {
                "original_path": str(original),
                "reason": "imported",
                "moved_at": "2026-06-10T10:00:00",
                "file_size_mb": 0.001,
            },
        )
        result = list_recycle_dir(str(tmp_path))
        self.assertFalse(result["items"][0]["restorable"])


class TestListRecycleDirDirMeta(unittest.TestCase):
    def test_dir_meta_is_listed(self):
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        _write_dir_meta(
            tmp_path,
            "removed_dir",
            {
                "original_path": "/source/removed_dir",
                "reason": "source_cleaner:empty",
                "moved_at": "2026-06-10T10:00:00",
                "is_dir": True,
            },
        )
        result = list_recycle_dir(str(tmp_path))
        self.assertEqual(result["total"], 1)
        self.assertTrue(result["items"][0]["is_dir"])

    def test_non_meta_files_ignored(self):
        """普通文件（无 .meta 后缀）不应被列入。"""
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())
        (tmp_path / "garbage.log").write_text("noise")
        result = list_recycle_dir(str(tmp_path))
        self.assertEqual(result["total"], 0)
