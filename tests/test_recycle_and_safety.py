#!/usr/bin/env python3
import unittest
import os
import sys
import tempfile
import shutil
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.core.safety import (
    move_to_recycle, move_to_recycle_with_companions,
    make_fingerprint, safe_delete, validate_path_safety,
)
from media_importer.core.recycle.manager import (
    _recycle_subpath, _determine_source_zone,
)
from media_importer.core.db.connection import init_db
from media_importer.core.db.task_repo import (
    create_task, find_by_source_path, find_by_fingerprint,
    update_task, list_tasks,
)
from media_importer.core.task_manager import TaskManager
from media_importer.core.config_loader import load_config


class TestMakeFingerprint(unittest.TestCase):
    def test_same_file_same_fingerprint(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mkv") as f:
            f.write(b"x" * 1024)
            path = f.name
        try:
            fp1 = make_fingerprint(path)
            fp2 = make_fingerprint(path)
            self.assertEqual(fp1, fp2)
            self.assertEqual(len(fp1), 16)
        finally:
            os.unlink(path)

    def test_different_files_different_fingerprint(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mkv") as f1:
            f1.write(b"a" * 1024)
            path1 = f1.name
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mkv") as f2:
            f2.write(b"b" * 2048)
            path2 = f2.name
        try:
            fp1 = make_fingerprint(path1)
            fp2 = make_fingerprint(path2)
            self.assertNotEqual(fp1, fp2)
        finally:
            os.unlink(path1)
            os.unlink(path2)

    def test_nonexistent_file_returns_empty(self):
        fp = make_fingerprint("/nonexistent/file.mkv")
        self.assertEqual(fp, "")

    def test_fingerprint_format_hex(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mkv") as f:
            f.write(b"test")
            path = f.name
        try:
            fp = make_fingerprint(path)
            self.assertTrue(all(c in "0123456789abcdef" for c in fp))
        finally:
            os.unlink(path)


class TestRecycleSubpath(unittest.TestCase):
    def test_source_zone_file(self):
        result = _recycle_subpath("/vol1/downloads/movie.mkv", "/vol1/downloads", [])
        self.assertIn("[源目录]", result)

    def test_import_zone_file(self):
        result = _recycle_subpath("/vol1/影视/电影/movie.mkv", "/vol1/downloads", ["/vol1/影视"])
        self.assertIn("[入库目录]", result)

    def test_other_zone_file(self):
        result = _recycle_subpath("/tmp/random.mkv", "/vol1/downloads", ["/vol1/影视"])
        self.assertIn("[其他]", result)

    def test_nested_source_path(self):
        result = _recycle_subpath("/vol1/downloads/subdir/movie.mkv", "/vol1/downloads", [])
        self.assertIn("[源目录]", result)
        self.assertIn("subdir", result)


class TestDetermineSourceZone(unittest.TestCase):
    def test_source_zone(self):
        result = _determine_source_zone("/vol1/downloads/movie.mkv", "/vol1/downloads", [])
        self.assertEqual(result, "source")

    def test_import_zone(self):
        result = _determine_source_zone("/vol1/影视/电影/movie.mkv", "/vol1/downloads", ["/vol1/影视"])
        self.assertEqual(result, "import")

    def test_other_zone(self):
        result = _determine_source_zone("/tmp/random.mkv", "/vol1/downloads", ["/vol1/影视"])
        self.assertEqual(result, "other")

    def test_empty_source_dir(self):
        result = _determine_source_zone("/tmp/random.mkv", "", [])
        self.assertEqual(result, "other")


class TestMoveToRecycle(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.recycle_dir = os.path.join(self.test_dir, "recycle")
        os.makedirs(self.recycle_dir)
        self.source_dir = os.path.join(self.test_dir, "source")
        os.makedirs(self.source_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_basic_move(self):
        src = os.path.join(self.source_dir, "movie.mkv")
        with open(src, "w") as f:
            f.write("test content")
        ok, dest, msg = move_to_recycle(src, self.recycle_dir, reason="test")
        self.assertTrue(ok)
        self.assertFalse(os.path.exists(src))
        self.assertTrue(os.path.exists(dest))
        meta_path = dest + ".meta"
        self.assertTrue(os.path.exists(meta_path))
        with open(meta_path) as f:
            meta = json.load(f)
        self.assertEqual(meta["reason"], "test")

    def test_same_name_conflict(self):
        src1 = os.path.join(self.source_dir, "movie.mkv")
        with open(src1, "w") as f:
            f.write("content1")
        ok1, dest1, _ = move_to_recycle(src1, self.recycle_dir, reason="test1")

        src2 = os.path.join(self.source_dir, "movie.mkv")
        with open(src2, "w") as f:
            f.write("content2")
        ok2, dest2, _ = move_to_recycle(src2, self.recycle_dir, reason="test2")

        self.assertTrue(ok1)
        self.assertTrue(ok2)
        self.assertNotEqual(dest1, dest2)
        self.assertIn("_1", dest2)

    def test_date_subdirectory(self):
        src = os.path.join(self.source_dir, "movie.mkv")
        with open(src, "w") as f:
            f.write("test")
        ok, dest, _ = move_to_recycle(src, self.recycle_dir, reason="test")
        date_str = time.strftime("%Y-%m-%d")
        self.assertIn(date_str, dest)

    def test_nonexistent_source(self):
        ok, dest, msg = move_to_recycle("/nonexistent.mkv", self.recycle_dir)
        self.assertTrue(ok)
        self.assertEqual(dest, "")

    def test_no_recycle_dir_configured(self):
        src = os.path.join(self.source_dir, "movie.mkv")
        with open(src, "w") as f:
            f.write("test")
        ok, _, msg = move_to_recycle(src, "", reason="test")
        self.assertFalse(ok)

    def test_source_zone_in_meta(self):
        src = os.path.join(self.source_dir, "movie.mkv")
        with open(src, "w") as f:
            f.write("test")
        ok, dest, _ = move_to_recycle(
            src, self.recycle_dir, reason="source_cleanup",
            source_dir=self.source_dir
        )
        meta_path = dest + ".meta"
        with open(meta_path) as f:
            meta = json.load(f)
        self.assertEqual(meta["source_zone"], "source")

    def test_import_zone_in_meta(self):
        import_dir = os.path.join(self.test_dir, "影视")
        os.makedirs(import_dir)
        src = os.path.join(import_dir, "movie.mkv")
        with open(src, "w") as f:
            f.write("test")
        ok, dest, _ = move_to_recycle(
            src, self.recycle_dir, reason="dedup_replace",
            source_dir=self.source_dir, import_roots=[import_dir]
        )
        meta_path = dest + ".meta"
        with open(meta_path) as f:
            meta = json.load(f)
        self.assertEqual(meta["source_zone"], "import")

    def test_meta_contains_task_id(self):
        src = os.path.join(self.source_dir, "movie.mkv")
        with open(src, "w") as f:
            f.write("test")
        ok, dest, _ = move_to_recycle(
            src, self.recycle_dir, reason="test", task_id="abc123"
        )
        meta_path = dest + ".meta"
        with open(meta_path) as f:
            meta = json.load(f)
        self.assertEqual(meta["task_id"], "abc123")

    def test_extra_meta_merged(self):
        src = os.path.join(self.source_dir, "movie.mkv")
        with open(src, "w") as f:
            f.write("test")
        ok, dest, _ = move_to_recycle(
            src, self.recycle_dir, reason="test",
            extra_meta={"custom_field": "custom_value"}
        )
        meta_path = dest + ".meta"
        with open(meta_path) as f:
            meta = json.load(f)
        self.assertEqual(meta["custom_field"], "custom_value")


class TestMoveToRecycleWithCompanions(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.recycle_dir = os.path.join(self.test_dir, "recycle")
        os.makedirs(self.recycle_dir)
        self.source_dir = os.path.join(self.test_dir, "source")
        os.makedirs(self.source_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_video_with_subtitle(self):
        video = os.path.join(self.source_dir, "movie.mkv")
        sub = os.path.join(self.source_dir, "movie.zh.srt")
        with open(video, "w") as f:
            f.write("video")
        with open(sub, "w") as f:
            f.write("subtitle")

        count = move_to_recycle_with_companions(
            video, [sub], [".mkv"], [".srt"],
            self.recycle_dir, reason="source_cleanup",
            source_dir=self.source_dir,
        )
        self.assertEqual(count, 2)
        self.assertFalse(os.path.exists(video))
        self.assertFalse(os.path.exists(sub))

    def test_auto_detect_companion_subtitles(self):
        video = os.path.join(self.source_dir, "movie.mkv")
        sub = os.path.join(self.source_dir, "movie.zh.srt")
        with open(video, "w") as f:
            f.write("video")
        with open(sub, "w") as f:
            f.write("subtitle")

        count = move_to_recycle_with_companions(
            video, [], [".mkv"], [".srt"],
            self.recycle_dir, reason="source_cleanup",
            source_dir=self.source_dir,
        )
        self.assertGreaterEqual(count, 2)

    def test_no_subtitle_companions(self):
        video = os.path.join(self.source_dir, "movie.mkv")
        with open(video, "w") as f:
            f.write("video")

        count = move_to_recycle_with_companions(
            video, [], [".mkv"], [".srt"],
            self.recycle_dir, reason="source_cleanup",
            source_dir=self.source_dir,
        )
        self.assertEqual(count, 1)
        self.assertFalse(os.path.exists(video))

    def test_nonexistent_video(self):
        count = move_to_recycle_with_companions(
            "/nonexistent.mkv", [], [".mkv"], [".srt"],
            self.recycle_dir, reason="test",
        )
        self.assertEqual(count, 0)


class TestFindFingerprint(unittest.TestCase):
    def setUp(self):
        self.db_dir = tempfile.mkdtemp()
        db_path = os.path.join(self.db_dir, "test.db")
        self.conn = init_db(db_path)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.db_dir, ignore_errors=True)

    def test_find_by_fingerprint(self):
        task = create_task(self.conn, "/source/movie.mkv", "movie.mkv", 1500.0)
        update_task(self.conn, task["task_id"],
                    source_fingerprint="abc123def456", status="SUCCESS")
        result = find_by_fingerprint(self.conn, "abc123def456")
        self.assertIsNotNone(result)
        self.assertEqual(result["task_id"], task["task_id"])

    def test_find_by_fingerprint_no_match(self):
        result = find_by_fingerprint(self.conn, "nonexistent")
        self.assertIsNone(result)

    def test_find_by_fingerprint_empty(self):
        result = find_by_fingerprint(self.conn, "")
        self.assertIsNone(result)

    def test_find_by_fingerprint_without_status_filter(self):
        task = create_task(self.conn, "/source/movie.mkv", "movie.mkv", 1500.0)
        update_task(self.conn, task["task_id"],
                    source_fingerprint="fp_pending", status="PENDING")
        result = find_by_fingerprint(self.conn, "fp_pending")
        self.assertIsNotNone(result)

    def test_find_by_fingerprint_with_status_filter(self):
        task = create_task(self.conn, "/source/movie.mkv", "movie.mkv", 1500.0)
        update_task(self.conn, task["task_id"],
                    source_fingerprint="fp_pending", status="PENDING")
        result = find_by_fingerprint(self.conn, "fp_pending", status_filter="SUCCESS")
        self.assertIsNone(result)

    def test_find_by_fingerprint_returns_latest(self):
        t1 = create_task(self.conn, "/source/movie.mkv", "movie.mkv", 1500.0)
        update_task(self.conn, t1["task_id"],
                    source_fingerprint="shared_fp", status="SUCCESS")
        t2 = create_task(self.conn, "/source/movie2.mkv", "movie2.mkv", 2000.0)
        update_task(self.conn, t2["task_id"],
                    source_fingerprint="shared_fp", status="SUCCESS")
        result = find_by_fingerprint(self.conn, "shared_fp")
        self.assertIsNotNone(result)
        self.assertEqual(result["task_id"], t2["task_id"])


class TestCheckSourceDuplicate(unittest.TestCase):
    def setUp(self):
        self.db_dir = tempfile.mkdtemp()
        self.tm = TaskManager(self.db_dir, config={
            "source_dir": "/source",
            "recycle_dir": "/recycle",
        })
        self.conn = self.tm.conn

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.db_dir, ignore_errors=True)

    def test_new_file_create(self):
        result = self.tm.check_source_duplicate("/source/new_movie.mkv")
        self.assertEqual(result["action"], "CREATE")
        self.assertFalse(result["exists"])

    def test_processing_skip(self):
        task = create_task(self.conn, "/source/movie.mkv", "movie.mkv", 1500.0)
        update_task(self.conn, task["task_id"], status="PROCESSING")
        result = self.tm.check_source_duplicate("/source/movie.mkv")
        self.assertEqual(result["action"], "SKIP")

    def test_confirming_skip(self):
        task = create_task(self.conn, "/source/movie.mkv", "movie.mkv", 1500.0)
        update_task(self.conn, task["task_id"], status="CONFIRMING")
        result = self.tm.check_source_duplicate("/source/movie.mkv")
        self.assertEqual(result["action"], "SKIP")

    def test_rename_detected(self):
        task = create_task(self.conn, "/source/old_name.mkv", "old_name.mkv", 1500.0)
        update_task(self.conn, task["task_id"],
                    source_fingerprint="a1b2c3d4e5f6", status="SUCCESS")
        result = self.tm.check_source_duplicate("/source/new_name.mkv",
                                                source_fingerprint="a1b2c3d4e5f6")
        self.assertEqual(result["action"], "RENAME_DETECTED")
        self.assertEqual(result["old_path"], "/source/old_name.mkv")

    def test_rename_detected_processing_skip(self):
        task = create_task(self.conn, "/source/old_name.mkv", "old_name.mkv", 1500.0)
        update_task(self.conn, task["task_id"],
                    source_fingerprint="fp_proc", status="PROCESSING")
        result = self.tm.check_source_duplicate("/source/new_name.mkv",
                                                source_fingerprint="fp_proc")
        self.assertEqual(result["action"], "SKIP")

    def test_fingerprint_no_match_creates(self):
        result = self.tm.check_source_duplicate("/source/movie.mkv",
                                                source_fingerprint="xyz789")
        self.assertEqual(result["action"], "CREATE")

    def test_finished_task_creates_new(self):
        task = create_task(self.conn, "/source/movie.mkv", "movie.mkv", 1500.0)
        update_task(self.conn, task["task_id"], status="FAILED")
        result = self.tm.check_source_duplicate("/source/movie.mkv")
        self.assertEqual(result["action"], "CREATE")

    def test_no_fingerprint_no_history_creates(self):
        result = self.tm.check_source_duplicate("/source/movie.mkv",
                                                source_fingerprint="")
        self.assertEqual(result["action"], "CREATE")


class TestConfigLoader(unittest.TestCase):
    def _write_config(self, config_dir, content):
        config_path = os.path.join(config_dir, "config.yaml")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(content)
        return config_path

    def test_cleanup_source_after_done_default(self):
        tmp = tempfile.mkdtemp()
        try:
            cp = self._write_config(tmp, """
source_dir: /tmp/src
temp_dir: /tmp/tmp
log_dir: /tmp/log
llm:
  api_key: test-key
source_policy: {}
""")
            config = load_config(cp)
            self.assertTrue(config["source_policy"]["cleanup_source_after_done"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cleanup_source_after_done_false(self):
        tmp = tempfile.mkdtemp()
        try:
            cp = self._write_config(tmp, """
source_dir: /tmp/src
temp_dir: /tmp/tmp
log_dir: /tmp/log
llm:
  api_key: test-key
source_policy:
  cleanup_source_after_done: false
""")
            config = load_config(cp)
            self.assertFalse(config["source_policy"]["cleanup_source_after_done"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_source_cleaner_default(self):
        tmp = tempfile.mkdtemp()
        try:
            cp = self._write_config(tmp, """
source_dir: /tmp/src
temp_dir: /tmp/tmp
log_dir: /tmp/log
llm:
  api_key: test-key
source_policy: {}
""")
            config = load_config(cp)
            self.assertIn("source_cleaner", config)
            self.assertFalse(config["source_cleaner"]["enabled"])
            self.assertEqual(config["source_cleaner"]["cleanup_mode"], "media_only")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_quarantine_dir_migration(self):
        tmp = tempfile.mkdtemp()
        try:
            cp = self._write_config(tmp, """
source_dir: /tmp/src
temp_dir: /tmp/tmp
log_dir: /tmp/log
llm:
  api_key: test-key
source_policy:
  quarantine_dir: /old/path
""")
            config = load_config(cp)
            self.assertEqual(config["source_policy"]["recycle_dir"], "/old/path")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_no_source_policy_gets_defaults(self):
        tmp = tempfile.mkdtemp()
        try:
            cp = self._write_config(tmp, """
source_dir: /tmp/src
temp_dir: /tmp/tmp
log_dir: /tmp/log
llm:
  api_key: test-key
""")
            config = load_config(cp)
            self.assertIn("source_policy", config)
            self.assertTrue(config["source_policy"]["cleanup_source_after_done"])
            self.assertIn("source_cleaner", config)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cleanup_mode_migration_read_only(self):
        tmp = tempfile.mkdtemp()
        try:
            cp = self._write_config(tmp, """
source_dir: /tmp/src
temp_dir: /tmp/tmp
log_dir: /tmp/log
llm:
  api_key: test-key
source_policy:
  cleanup_mode: read_only
""")
            config = load_config(cp)
            self.assertFalse(config["source_policy"]["cleanup_source_after_done"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestProviderFields(unittest.TestCase):
    def test_provider_columns_in_ddl(self):
        from media_importer.core.db.constants import CREATE_TASKS_TABLE
        self.assertIn("provider_type", CREATE_TASKS_TABLE)
        self.assertIn("provider_id", CREATE_TASKS_TABLE)

    def test_fingerprint_columns_in_ddl(self):
        from media_importer.core.db.constants import CREATE_TASKS_TABLE
        self.assertIn("source_fingerprint", CREATE_TASKS_TABLE)
        self.assertIn("source_file_size", CREATE_TASKS_TABLE)
        self.assertIn("source_mtime", CREATE_TASKS_TABLE)

    def test_fingerprint_index(self):
        from media_importer.core.db.constants import CREATE_TASKS_INDEXES
        self.assertTrue(any("fingerprint" in idx for idx in CREATE_TASKS_INDEXES))

    def test_provider_fields_in_valid_columns(self):
        import inspect
        from media_importer.core.db import task_repo
        source = inspect.getsource(task_repo.update_task)
        for col in ["provider_type", "provider_id", "source_fingerprint",
                     "source_file_size", "source_mtime"]:
            self.assertIn(col, source)

    def test_db_migration_adds_columns(self):
        db_dir = tempfile.mkdtemp()
        db_path = os.path.join(db_dir, "test.db")
        conn = init_db(db_path)
        columns = [row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()]
        self.assertIn("provider_type", columns)
        self.assertIn("provider_id", columns)
        self.assertIn("source_fingerprint", columns)
        self.assertIn("source_file_size", columns)
        self.assertIn("source_mtime", columns)
        conn.close()
        shutil.rmtree(db_dir, ignore_errors=True)

    def test_provider_fields_read_write(self):
        db_dir = tempfile.mkdtemp()
        db_path = os.path.join(db_dir, "test.db")
        conn = init_db(db_path)
        try:
            task = create_task(conn, "/source/movie.mkv", "movie.mkv", 1500.0)
            update_task(conn, task["task_id"],
                        provider_type="tmdb", provider_id="12345",
                        source_fingerprint="abc123", source_file_size=1572864,
                        source_mtime="2025-01-01T00:00:00")
            updated = conn.execute(
                "SELECT provider_type, provider_id, source_fingerprint, "
                "source_file_size, source_mtime FROM tasks WHERE task_id=?",
                (task["task_id"],)
            ).fetchone()
            self.assertEqual(updated[0], "tmdb")
            self.assertEqual(updated[1], "12345")
            self.assertEqual(updated[2], "abc123")
            self.assertEqual(updated[3], 1572864)
            self.assertEqual(updated[4], "2025-01-01T00:00:00")
        finally:
            conn.close()
            shutil.rmtree(db_dir, ignore_errors=True)


class TestMetadataScraperProviderFields(unittest.TestCase):
    def _make_scraper(self, providers=None, llm_result=None):
        from media_importer.scraper.metadata_scraper import MetadataScraper
        from unittest.mock import MagicMock

        config = {
            "llm": {"api_key": "test", "model": "test"},
            "confidence": {},
            "metadata": {"providers": []},
        }
        scraper = MetadataScraper(config)
        if providers is not None:
            scraper.providers = providers
        if llm_result is not None:
            scraper.llm_scraper.scrape = MagicMock(return_value=llm_result)
            scraper.llm_scraper.scrape_with_context = MagicMock(return_value=llm_result)
        scraper.confidence_engine.calculate = MagicMock(
            return_value=MagicMock(
                final_confidence=0.9, scrape_trace={}, gate_blocked=False,
                search_conf=0.9, data_gate=1.0
            )
        )
        scraper.confidence_engine.calculate_ai_only = MagicMock(
            return_value=MagicMock(
                final_confidence=0.5, scrape_trace={}, gate_blocked=False,
                search_conf=0.0, data_gate=0.5
            )
        )
        return scraper

    def _make_provider(self, provider_type="tmdb", item_id="12345"):
        from unittest.mock import MagicMock
        from media_importer.scraper.providers.base import SearchItem, SearchResult

        provider = MagicMock()
        provider.provider_type = provider_type
        provider.display_name = provider_type.upper()
        provider.fallback_language = "en-US"
        provider.language = "zh-CN"
        search_item = SearchItem(
            provider_type=provider_type, item_id=item_id,
            title="Test Movie", original_title="Test Movie Original",
            year=2024, media_type="movie", poster_url="",
            vote_average=8.0, raw_data={}
        )
        provider.search = MagicMock(return_value=SearchResult(
            items=[search_item], total_results=1
        ))
        from media_importer.scraper.providers.base import MediaDetails, Genre
        provider.get_details = MagicMock(return_value=MediaDetails(
            provider_type=provider_type, item_id=item_id,
            media_type="movie", title="测试电影",
            original_title="Test Movie", year=2024,
            genres=[Genre(id="1", name="动作")],
            overview="test", vote_average=8.0,
            origin_country=[], original_language="zh",
            adult=False, tagline="", poster_url="", raw_data={}
        ))
        provider.map_dimensions = MagicMock(return_value=[])
        return provider, search_item

    def test_provider_search_returns_provider_fields(self):
        llm_result = {"title_cn": "测试", "confidence": 0.9}
        provider, _ = self._make_provider("tmdb", "67890")
        scraper = self._make_scraper(providers=[provider], llm_result=llm_result)
        result = scraper.scrape("Test.Movie.2024.mkv")
        self.assertEqual(result.get("provider_type"), "tmdb")
        self.assertEqual(result.get("provider_id"), "67890")

    def test_ai_only_returns_empty_provider_fields(self):
        llm_result = {"title_cn": "测试", "confidence": 0.5}
        scraper = self._make_scraper(providers=[], llm_result=llm_result)
        result = scraper.scrape("Unknown.Movie.mkv")
        self.assertEqual(result.get("provider_type"), "")
        self.assertEqual(result.get("provider_id"), "")

    def test_provider_details_fallback_returns_empty_fields(self):
        from unittest.mock import MagicMock
        from media_importer.scraper.providers.base import SearchItem, SearchResult

        provider = MagicMock()
        provider.provider_type = "tmdb"
        provider.display_name = "TMDB"
        provider.fallback_language = "en-US"
        provider.language = "zh-CN"
        search_item = SearchItem(
            provider_type="tmdb", item_id="99999",
            title="Test", original_title="Test",
            year=2024, media_type="movie", poster_url="",
            vote_average=8.0, raw_data={}
        )
        provider.search = MagicMock(return_value=SearchResult(
            items=[search_item], total_results=1
        ))
        provider.get_details = MagicMock(side_effect=Exception("API error"))
        provider.map_dimensions = MagicMock(return_value=[])

        llm_result = {"title_cn": "测试", "confidence": 0.5}
        scraper = self._make_scraper(providers=[provider], llm_result=llm_result)
        result = scraper.scrape("Test.Movie.2024.mkv")
        self.assertEqual(result.get("provider_type"), "")
        self.assertEqual(result.get("provider_id"), "")


if __name__ == "__main__":
    unittest.main()
