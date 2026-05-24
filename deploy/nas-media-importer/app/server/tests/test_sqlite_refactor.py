#!/usr/bin/env python3
"""
任务系统 SQLite 重构 - 全量功能测试
覆盖: db.py / task_manager.py / file_scanner.py / pipeline.py / api_server.py
每个测试类使用独立的临时数据库，互不影响
"""
import os
import sys
import json
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'media_importer'))

import db as db_module
from task_manager import TaskManager
from file_scanner import FileScanner


# ============================================================
# 1. db.py 测试 - 数据库基础设施
# ============================================================
class TestDB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="test_db_")
        cls.db_path = os.path.join(cls.tmpdir, "test_tasks.db")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.conn = db_module.init_db(self.db_path)

    def tearDown(self):
        self.conn.close()

    def test_01_init_db_creates_tables(self):
        cur = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [r["name"] for r in cur.fetchall()]
        self.assertIn("tasks", tables)
        self.assertIn("task_subtitles", tables)

    def test_02_init_db_creates_indexes(self):
        cur = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
        )
        indexes = [r["name"] for r in cur.fetchall()]
        self.assertTrue(any("source_path" in idx for idx in indexes))
        self.assertTrue(any("status" in idx for idx in indexes))

    def test_03_create_task_basic(self):
        task = db_module.create_task(
            self.conn,
            source_path="/movies/Inception.2010.mkv",
            source_filename="Inception.2010.mkv",
            file_size_mb=2048.5,
        )
        self.assertIsNotNone(task)
        self.assertTrue(len(task["task_id"]) > 0)
        self.assertEqual(task["source_path"], "/movies/Inception.2010.mkv")
        self.assertEqual(task["source_filename"], "Inception.2010.mkv")
        self.assertEqual(task["status"], "PENDING")
        self.assertEqual(task["file_size_mb"], 2048.5)
        self.assertIsNotNone(task["created_at"])

    def test_04_create_task_with_custom_id(self):
        task = db_module.create_task(
            self.conn,
            source_path="/test/video.mp4",
            source_filename="video.mp4",
            task_id="custom_id_001",
        )
        self.assertEqual(task["task_id"], "custom_id_001")

    def test_05_get_task(self):
        created = db_module.create_task(
            self.conn, source_path="/a/b.mkv", source_filename="b.mkv"
        )
        fetched = db_module.get_task(self.conn, created["task_id"])
        self.assertEqual(fetched["task_id"], created["task_id"])
        self.assertEqual(fetched["source_filename"], "b.mkv")

    def test_06_get_task_not_found(self):
        result = db_module.get_task(self.conn, "nonexistent_id")
        self.assertIsNone(result)

    def test_07_update_task_status(self):
        task = db_module.create_task(
            self.conn, source_path="/x/y.mkv", source_filename="y.mkv"
        )
        updated = db_module.update_task(
            self.conn, task["task_id"],
            status="PROCESSING", percentage=50, step_name="scrape"
        )
        self.assertEqual(updated["status"], "PROCESSING")
        self.assertEqual(updated["percentage"], 50)
        self.assertEqual(updated["step_name"], "scrape")

    def test_08_update_task_json_fields(self):
        task = db_module.create_task(
            self.conn, source_path="/x/z.mkv", source_filename="z.mkv"
        )
        scrape_result = {
            "title_cn": "盗梦空间",
            "title_en": "Inception",
            "year": "2010",
            "type": "movie",
            "dimensions": {"media_type": "movie", "restricted_level": "normal"},
            "confidence": 0.95,
        }
        updated = db_module.update_task(
            self.conn, task["task_id"],
            scrape_result=scrape_result,
            scrape_title_cn="盗梦空间",
            scrape_year="2010",
        )
        self.assertIsInstance(updated["scrape_result"], dict)
        self.assertEqual(updated["scrape_result"]["title_cn"], "盗梦空间")

    def test_09_find_by_source_path(self):
        db_module.create_task(
            self.conn,
            source_path="/unique/path/video.mkv",
            source_filename="video.mkv",
        )
        found = db_module.find_by_source_path(self.conn, "/unique/path/video.mkv")
        self.assertIsNotNone(found)
        self.assertEqual(found["source_filename"], "video.mkv")

    def test_10_find_by_source_path_not_found(self):
        found = db_module.find_by_source_path(self.conn, "/nonexistent/path.mkv")
        self.assertIsNone(found)

    def test_11_list_tasks_pagination(self):
        for i in range(25):
            db_module.create_task(
                self.conn,
                source_path=f"/batch/video_{i:03d}.mkv",
                source_filename=f"video_{i:03d}.mkv",
            )
        rows, total, total_pages = db_module.list_tasks(
            self.conn, page=1, page_size=10
        )
        self.assertEqual(len(rows), 10)
        self.assertEqual(total, 25)
        self.assertEqual(total_pages, 3)

        rows2, _, _ = db_module.list_tasks(self.conn, page=3, page_size=10)
        self.assertEqual(len(rows2), 5)

    def test_12_list_tasks_filter_by_status(self):
        t1 = db_module.create_task(self.conn, source_path="/s/a.mkv", source_filename="a.mkv")
        t2 = db_module.create_task(self.conn, source_path="/s/b.mkv", source_filename="b.mkv")
        db_module.update_task(self.conn, t1["task_id"], status="SUCCESS")
        db_module.update_task(self.conn, t2["task_id"], status="FAILED")

        rows, total, _ = db_module.list_tasks(self.conn, page=1, page_size=20, status="SUCCESS")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["status"], "SUCCESS")

        rows2, total2, _ = db_module.list_tasks(self.conn, page=1, page_size=20, status="FAILED")
        self.assertEqual(total2, 1)

    def test_13_count_by_status(self):
        t1 = db_module.create_task(self.conn, source_path="/c/a.mkv", source_filename="a.mkv")
        t2 = db_module.create_task(self.conn, source_path="/c/b.mkv", source_filename="b.mkv")
        t3 = db_module.create_task(self.conn, source_path="/c/c.mkv", source_filename="c.mkv")
        db_module.update_task(self.conn, t1["task_id"], status="SUCCESS")
        db_module.update_task(self.conn, t2["task_id"], status="FAILED")
        counts = db_module.count_by_status(self.conn)
        self.assertEqual(counts["SUCCESS"], 1)
        self.assertEqual(counts["FAILED"], 1)
        self.assertEqual(counts["PENDING"], 1)

    def test_14_has_active_tasks(self):
        self.assertFalse(db_module.has_active_tasks(self.conn))
        t = db_module.create_task(self.conn, source_path="/d/a.mkv", source_filename="a.mkv")
        self.assertTrue(db_module.has_active_tasks(self.conn))
        db_module.update_task(self.conn, t["task_id"], status="SUCCESS")
        self.assertFalse(db_module.has_active_tasks(self.conn))

    def test_15_get_next_pending(self):
        t1 = db_module.create_task(self.conn, source_path="/p/first.mkv", source_filename="first.mkv")
        t2 = db_module.create_task(self.conn, source_path="/p/second.mkv", source_filename="second.mkv")
        next_task = db_module.get_next_pending(self.conn)
        self.assertIsNotNone(next_task)
        self.assertEqual(next_task["task_id"], t1["task_id"])

    def test_16_create_subtitles(self):
        task = db_module.create_task(
            self.conn, source_path="/sub/video.mkv", source_filename="video.mkv"
        )
        subs = db_module.create_subtitles(
            self.conn, task["task_id"],
            ["/sub/video.chs.srt", "/sub/video.eng.srt"]
        )
        self.assertEqual(len(subs), 2)
        self.assertEqual(subs[0]["source_filename"], "video.chs.srt")
        self.assertEqual(subs[1]["source_filename"], "video.eng.srt")

    def test_17_get_subtitles_by_task(self):
        task = db_module.create_task(
            self.conn, source_path="/sub2/video.mkv", source_filename="video.mkv"
        )
        db_module.create_subtitles(
            self.conn, task["task_id"],
            ["/sub2/video.chs.srt"]
        )
        subs = db_module.get_subtitles_by_task(self.conn, task["task_id"])
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0]["status"], "PENDING")

    def test_18_update_subtitle(self):
        task = db_module.create_task(
            self.conn, source_path="/sub3/video.mkv", source_filename="video.mkv"
        )
        subs = db_module.create_subtitles(
            self.conn, task["task_id"],
            ["/sub3/video.chs.srt"]
        )
        updated = db_module.update_subtitle(
            self.conn, subs[0]["id"],
            status="SUCCESS", lang="chs", import_path="/import/video.chs.srt"
        )
        self.assertEqual(updated["status"], "SUCCESS")
        self.assertEqual(updated["lang"], "chs")

    def test_19_count_subtitles_by_task(self):
        task = db_module.create_task(
            self.conn, source_path="/sub4/video.mkv", source_filename="video.mkv"
        )
        db_module.create_subtitles(
            self.conn, task["task_id"],
            ["/sub4/a.srt", "/sub4/b.srt"]
        )
        total, success = db_module.count_subtitles_by_task(self.conn, task["task_id"])
        self.assertEqual(total, 2)
        self.assertEqual(success, 0)

    def test_20_update_subtitles_by_task(self):
        task = db_module.create_task(
            self.conn, source_path="/sub5/video.mkv", source_filename="video.mkv"
        )
        db_module.create_subtitles(
            self.conn, task["task_id"],
            ["/sub5/a.srt", "/sub5/b.srt"]
        )
        db_module.update_subtitles_by_task(
            self.conn, task["task_id"],
            status="SUCCESS", confirm_status="CONFIRMED"
        )
        subs = db_module.get_subtitles_by_task(self.conn, task["task_id"])
        for s in subs:
            self.assertEqual(s["status"], "SUCCESS")
            self.assertEqual(s["confirm_status"], "CONFIRMED")

    def test_21_update_task_ignores_invalid_column(self):
        task = db_module.create_task(
            self.conn, source_path="/inv/a.mkv", source_filename="a.mkv"
        )
        updated = db_module.update_task(
            self.conn, task["task_id"],
            status="PROCESSING", invalid_column="should_be_ignored"
        )
        self.assertEqual(updated["status"], "PROCESSING")

    def test_22_find_failed_too_many(self):
        t = db_module.create_task(self.conn, source_path="/fail/a.mkv", source_filename="a.mkv")
        db_module.update_task(self.conn, t["task_id"], status="FAILED", retry_count=3)
        failed = db_module.find_failed_too_many(self.conn, max_retries=3)
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["task_id"], t["task_id"])


# ============================================================
# 2. TaskManager 测试 - 业务逻辑层
# ============================================================
class TestTaskManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="test_tm_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        db_path = os.path.join(self.tmpdir, f"test_{id(self)}.db")
        data_dir = self.tmpdir
        self.config = {
            "source_dedup": {
                "enabled": True,
            }
        }
        self.tm = TaskManager(data_dir, self.config)
        self.source_dir = os.path.join(self.tmpdir, "source")
        self.quarantine_dir = os.path.join(self.tmpdir, "quarantine")
        os.makedirs(self.source_dir, exist_ok=True)
        os.makedirs(self.quarantine_dir, exist_ok=True)

    def test_01_create_task(self):
        task = self.tm.create_task(
            video_path=os.path.join(self.source_dir, "movie.mkv"),
            video_file="movie.mkv",
            file_size_mb=1024.0,
        )
        self.assertIsNotNone(task)
        self.assertEqual(task["status"], "PENDING")
        self.assertEqual(task["source_filename"], "movie.mkv")

    def test_02_create_task_with_subtitles(self):
        task = self.tm.create_task(
            video_path=os.path.join(self.source_dir, "film.mkv"),
            video_file="film.mkv",
            subtitle_files=["/src/film.chs.srt", "/src/film.eng.srt"],
        )
        self.assertEqual(task["subtitle_total"], 2)

    def test_03_get_task(self):
        created = self.tm.create_task(
            video_path="/src/a.mkv", video_file="a.mkv"
        )
        fetched = self.tm.get_task(created["task_id"])
        self.assertEqual(fetched["task_id"], created["task_id"])

    def test_04_update_progress(self):
        task = self.tm.create_task(
            video_path="/src/b.mkv", video_file="b.mkv"
        )
        self.tm.update_progress(task, 3, "scrape", 50, bytes_copied=100)
        fetched = self.tm.get_task(task["task_id"])
        self.assertEqual(fetched["percentage"], 50)
        self.assertEqual(fetched["step_name"], "scrape")

    def test_05_retry_task(self):
        task = self.tm.create_task(
            video_path="/src/c.mkv", video_file="c.mkv"
        )
        db_module.update_task(self.tm.conn, task["task_id"], status="FAILED")
        retried = self.tm.retry_task(task["task_id"])
        self.assertEqual(retried["status"], "PENDING")
        self.assertEqual(retried["retry_count"], 1)

    def test_06_retry_all_failed(self):
        for i in range(3):
            t = self.tm.create_task(
                video_path=f"/src/f{i}.mkv", video_file=f"f{i}.mkv"
            )
            db_module.update_task(self.tm.conn, t["task_id"], status="FAILED")
        retried = self.tm.retry_all_failed()
        self.assertEqual(len(retried), 3)

    def test_07_count_by_status(self):
        self.tm.create_task(video_path="/src/d.mkv", video_file="d.mkv")
        t2 = self.tm.create_task(video_path="/src/e.mkv", video_file="e.mkv")
        db_module.update_task(self.tm.conn, t2["task_id"], status="SUCCESS")
        counts = self.tm.count_by_status()
        self.assertIn("PENDING", counts)
        self.assertIn("SUCCESS", counts)

    def test_08_has_active_tasks(self):
        self.assertTrue(self.tm.has_active_tasks())

    def test_09_check_source_duplicate_new_file(self):
        result = self.tm.check_source_duplicate("/brand/new/file.mkv")
        self.assertFalse(result["exists"])
        self.assertEqual(result["action"], "CREATE")

    def test_10_check_source_duplicate_previously_success(self):
        t = self.tm.create_task(
            video_path="/dup/success.mkv", video_file="success.mkv"
        )
        db_module.update_task(self.tm.conn, t["task_id"], status="SUCCESS")
        result = self.tm.check_source_duplicate("/dup/success.mkv")
        self.assertTrue(result["exists"])
        self.assertEqual(result["action"], "CREATE")

    def test_11_check_source_duplicate_failed_retryable(self):
        t = self.tm.create_task(
            video_path="/dup/failed.mkv", video_file="failed.mkv"
        )
        db_module.update_task(self.tm.conn, t["task_id"], status="FAILED", retry_count=1)
        result = self.tm.check_source_duplicate("/dup/failed.mkv")
        self.assertTrue(result["exists"])
        self.assertEqual(result["action"], "CREATE")

    def test_12_check_source_duplicate_failed_max_retries(self):
        t = self.tm.create_task(
            video_path="/dup/maxfail.mkv", video_file="maxfail.mkv"
        )
        db_module.update_task(self.tm.conn, t["task_id"], status="FAILED", retry_count=3)
        result = self.tm.check_source_duplicate("/dup/maxfail.mkv")
        self.assertTrue(result["exists"])
        self.assertEqual(result["action"], "CREATE")

    def test_13_check_source_duplicate_processing(self):
        t = self.tm.create_task(
            video_path="/dup/processing.mkv", video_file="processing.mkv"
        )
        db_module.update_task(self.tm.conn, t["task_id"], status="PROCESSING")
        result = self.tm.check_source_duplicate("/dup/processing.mkv")
        self.assertEqual(result["action"], "SKIP")

    def test_14_check_source_duplicate_confirming(self):
        t = self.tm.create_task(
            video_path="/dup/confirming.mkv", video_file="confirming.mkv"
        )
        db_module.update_task(self.tm.conn, t["task_id"], status="CONFIRMING")
        result = self.tm.check_source_duplicate("/dup/confirming.mkv")
        self.assertEqual(result["action"], "SKIP")

    def test_16_move_to_quarantine(self):
        video_path = os.path.join(self.source_dir, "quarantine_test.mkv")
        sub_path = os.path.join(self.source_dir, "quarantine_test.chs.srt")
        with open(video_path, 'w') as f:
            f.write("fake video")
        with open(sub_path, 'w') as f:
            f.write("fake subtitle")

        t = self.tm.create_task(
            video_path=video_path, video_file="quarantine_test.mkv",
            subtitle_files=[sub_path],
        )
        self.tm.move_to_quarantine(
            task_id=t["task_id"],
            source_path=video_path,
            subtitle_paths=[sub_path],
            quarantine_dir=self.quarantine_dir,
        )
        self.assertTrue(os.path.exists(os.path.join(self.quarantine_dir, "quarantine_test.mkv")))
        self.assertTrue(os.path.exists(os.path.join(self.quarantine_dir, "quarantine_test.chs.srt")))
        self.assertFalse(os.path.exists(video_path))
        self.assertFalse(os.path.exists(sub_path))

        updated = self.tm.get_task(t["task_id"])
        self.assertEqual(updated["file_location"], "quarantine")

    def test_17_list_tasks_pagination(self):
        for i in range(15):
            self.tm.create_task(
                video_path=f"/list/v{i:03d}.mkv", video_file=f"v{i:03d}.mkv"
            )
        tasks = self.tm.list_tasks(limit=10)
        self.assertEqual(len(tasks), 10)

    def test_18_get_next_pending(self):
        t1 = self.tm.create_task(video_path="/next/first.mkv", video_file="first.mkv")
        t2 = self.tm.create_task(video_path="/next/second.mkv", video_file="second.mkv")
        next_task = self.tm.get_next_pending()
        self.assertIsNotNone(next_task)


# ============================================================
# 3. FileScanner 测试 - 文件扫描与分组
# ============================================================
class TestFileScanner(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="test_scan_")
        self.config = {
            "source_dir": self.tmpdir,
            "source_dedup": {
                "enabled": True,
                "quarantine_dir": os.path.join(self.tmpdir, "quarantine"),
            },
        }
        self.scanner = FileScanner(self.config)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_file(self, rel_path, content="fake"):
        fpath = os.path.join(self.tmpdir, rel_path)
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, 'w') as f:
            f.write(content)
        return fpath

    def test_01_scan_empty_dir(self):
        groups = self.scanner.scan_path(self.tmpdir)
        self.assertEqual(len(groups), 0)

    def test_02_scan_nonexistent_dir(self):
        groups = self.scanner.scan_path("/nonexistent/path")
        self.assertEqual(len(groups), 0)

    def test_03_scan_single_video(self):
        self._create_file("Inception.2010.1080p.mkv")
        groups = self.scanner.scan_path(self.tmpdir)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["video_file"], "Inception.2010.1080p.mkv")

    def test_04_scan_video_with_subtitles(self):
        self._create_file("Movie.2020.mkv")
        self._create_file("Movie.2020.chs.srt")
        self._create_file("Movie.2020.eng.srt")
        groups = self.scanner.scan_path(self.tmpdir)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["subtitle_files"]), 2)

    def test_05_scan_multiple_videos(self):
        self._create_file("Film.A.2020.mkv")
        self._create_file("Film.B.2021.mkv")
        groups = self.scanner.scan_path(self.tmpdir)
        self.assertEqual(len(groups), 2)

    def test_06_scan_ignores_non_media(self):
        self._create_file("video.mkv")
        self._create_file("readme.txt")
        self._create_file("image.jpg")
        groups = self.scanner.scan_path(self.tmpdir)
        self.assertEqual(len(groups), 1)

    def test_07_scan_subdir(self):
        self._create_file("subdir/DeepVideo.mkv")
        groups = self.scanner.scan_path(self.tmpdir)
        self.assertEqual(len(groups), 1)
        self.assertIn("subdir", groups[0]["video_path"])

    def test_08_scan_skips_hidden_dirs(self):
        self._create_file(".hidden/secret.mkv")
        self._create_file("visible/normal.mkv")
        groups = self.scanner.scan_path(self.tmpdir)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["video_file"], "normal.mkv")

    def test_09_file_size(self):
        fpath = self._create_file("big.mkv", "x" * (2 * 1024 * 1024))
        groups = self.scanner.scan_path(self.tmpdir)
        self.assertEqual(len(groups), 1)
        self.assertGreater(groups[0]["file_size_mb"], 0)

    def test_10_scan_and_group_alias(self):
        self._create_file("test.mkv")
        groups = self.scanner.scan_and_group(self.tmpdir)
        self.assertEqual(len(groups), 1)

    def test_11_scan_and_filter_no_task_manager(self):
        self._create_file("filter_test.mkv")
        groups = self.scanner.scan_and_filter(self.tmpdir)
        self.assertEqual(len(groups), 1)

    def test_12_scan_and_filter_with_dedup(self):
        self._create_file("dedup_test.mkv")
        db_path = os.path.join(self.tmpdir, "test_filter.db")
        conn = db_module.init_db(db_path)
        t = db_module.create_task(
            conn,
            source_path=os.path.join(self.tmpdir, "dedup_test.mkv"),
            source_filename="dedup_test.mkv",
        )
        db_module.update_task(conn, t["task_id"], status="SUCCESS")
        tm = TaskManager(
            os.path.join(self.tmpdir, "filter.json"),
            {"source_dedup": {"enabled": True}},
        )
        tm.conn = conn
        self.config["source_dedup"] = {
            "enabled": True,
            "quarantine_dir": os.path.join(self.tmpdir, "quarantine"),
        }
        scanner = FileScanner(self.config, task_manager=tm)
        groups = scanner.scan_and_filter(self.tmpdir)
        self.assertEqual(len(groups), 1)
        conn.close()

    def test_13_clean_name(self):
        self.assertEqual(self.scanner._clean_name("Inception.2010.1080p.BluRay"), "inception 2010")
        self.assertEqual(self.scanner._clean_name("Movie.2020.WEB-DL.x264"), "movie 2020")


# ============================================================
# 4. Pipeline 测试 - 核心流程 (Mock 外部依赖)
# ============================================================
class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="test_pipe_")
        self.source_dir = os.path.join(self.tmpdir, "source")
        self.temp_dir = os.path.join(self.tmpdir, "temp")
        self.import_dir = os.path.join(self.tmpdir, "import")
        os.makedirs(self.source_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.import_dir, exist_ok=True)

        self.db_path = os.path.join(self.tmpdir, "test_pipe.db")
        self.conn = db_module.init_db(self.db_path)

        self.config = {
            "source_dir": self.source_dir,
            "temp_dir": self.temp_dir,
            "manual_review": {"enabled": False},
            "duplicate_handling": {"enabled": False},
            "path_rules": [
                {
                    "conditions": {"media_type": "movie", "restricted_level": "normal"},
                    "template": os.path.join(self.import_dir, "movies", "{title_cn} ({year})"),
                },
                {
                    "conditions": {"media_type": "tv"},
                    "template": os.path.join(self.import_dir, "tv", "{title_cn}"),
                },
            ],
            "filename_templates": {
                "movie": "{title_cn} ({year}){ext}",
                "tv": "{title_cn} - S{season:02d}E{episode:02d}{ext}",
            },
            "source_file_handling": {"delete_after_process": False},
            "source_dedup": {"enabled": True},
            "_config_path": __file__,
        }

        self.tm = TaskManager(
            os.path.join(self.tmpdir, "pipe.json"), self.config
        )
        self.tm.conn = self.conn

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_video_file(self, filename, content="fake video data"):
        fpath = os.path.join(self.source_dir, filename)
        with open(fpath, 'w') as f:
            f.write(content)
        return fpath

    @patch('pipeline.HookRunner')
    @patch('pipeline.FileCopier')
    @patch('pipeline.LLMScraper')
    def test_01_process_one_success_flow(self, MockScraper, MockCopier, MockHooks):
        from pipeline import PipelineRunner, PipelineError

        video_path = self._create_video_file("Inception.2010.mkv")
        temp_copy = os.path.join(self.temp_dir, "Inception.2010.mkv")
        with open(temp_copy, 'w') as f:
            f.write("copied")

        MockCopier.return_value.copy_to_temp.return_value = [temp_copy]
        MockScraper.return_value.scrape.return_value = {
            "title_cn": "盗梦空间",
            "title_en": "Inception",
            "year": "2010",
            "type": "movie",
            "dimensions": {"media_type": "movie", "restricted_level": "normal"},
            "confidence": 0.95,
        }
        MockHooks.return_value.run_before_process.return_value = None
        MockHooks.return_value.run_after_success.return_value = None

        with patch('pipeline.classify') as mock_classify, \
             patch('pipeline.move_to_import') as mock_move, \
             patch('pipeline.apply_filename_template') as mock_rename:
            mock_classify.return_value = os.path.join(self.import_dir, "movies", "盗梦空间 (2010)")
            mock_rename.return_value = "盗梦空间 (2010).mkv"
            mock_move.return_value = {
                "video": os.path.join(self.import_dir, "movies", "盗梦空间 (2010)", "盗梦空间 (2010).mkv"),
                "subtitles": [],
            }

            pipeline = PipelineRunner(
                config=self.config, task_manager=self.tm,
                metrics=None, logger=None, notifier=None,
            )
            task = self.tm.create_task(
                video_path=video_path, video_file="Inception.2010.mkv",
                file_size_mb=2048.0,
            )
            result = pipeline.process_one(task)
            self.assertTrue(result)
            self.assertEqual(task["status"], "SUCCESS")

    @patch('pipeline.HookRunner')
    @patch('pipeline.FileCopier')
    @patch('pipeline.LLMScraper')
    def test_02_process_one_confirming_flow(self, MockScraper, MockCopier, MockHooks):
        from pipeline import PipelineRunner

        video_path = self._create_video_file("ConfirmMovie.mkv")
        temp_copy = os.path.join(self.temp_dir, "ConfirmMovie.mkv")
        with open(temp_copy, 'w') as f:
            f.write("copied")

        MockCopier.return_value.copy_to_temp.return_value = [temp_copy]
        MockScraper.return_value.scrape.return_value = {
            "title_cn": "确认电影",
            "year": "2023",
            "type": "movie",
            "dimensions": {"media_type": "movie", "restricted_level": "normal"},
            "confidence": 0.9,
        }
        MockHooks.return_value.run_before_process.return_value = None
        MockHooks.return_value.run_after_success.return_value = None

        self.config["manual_review"] = {"enabled": True}

        with patch('pipeline.classify') as mock_classify:
            mock_classify.return_value = os.path.join(self.import_dir, "movies", "确认电影 (2023)")
            pipeline = PipelineRunner(
                config=self.config, task_manager=self.tm,
                metrics=None, logger=None, notifier=None,
            )
            task = self.tm.create_task(
                video_path=video_path, video_file="ConfirmMovie.mkv",
            )
            result = pipeline.process_one(task)
            self.assertTrue(result)
            self.assertEqual(task["status"], "CONFIRMING")
            self.assertEqual(task["confirm_status"], "PENDING")

    @patch('pipeline.HookRunner')
    @patch('pipeline.FileCopier')
    @patch('pipeline.LLMScraper')
    def test_03_process_one_scrape_failure(self, MockScraper, MockCopier, MockHooks):
        from pipeline import PipelineRunner
        from llm_scraper import LLMScrapeError

        video_path = self._create_video_file("BadFile.mkv")
        temp_copy = os.path.join(self.temp_dir, "BadFile.mkv")
        with open(temp_copy, 'w') as f:
            f.write("copied")

        MockCopier.return_value.copy_to_temp.return_value = [temp_copy]
        MockScraper.return_value.scrape.side_effect = LLMScrapeError("API timeout")
        MockHooks.return_value.run_before_process.return_value = None
        MockHooks.return_value.run_after_failure.return_value = None

        with patch('pipeline.delete_source_files'):
            pipeline = PipelineRunner(
                config=self.config, task_manager=self.tm,
                metrics=None, logger=None, notifier=None,
            )
            task = self.tm.create_task(
                video_path=video_path, video_file="BadFile.mkv",
            )
            result = pipeline.process_one(task)
            self.assertFalse(result)
            self.assertEqual(task["status"], "FAILED")
            self.assertIn("刮削失败", task["error_message"])

    @patch('pipeline.HookRunner')
    @patch('pipeline.FileCopier')
    @patch('pipeline.LLMScraper')
    def test_04_process_one_classify_failure(self, MockScraper, MockCopier, MockHooks):
        from pipeline import PipelineRunner

        video_path = self._create_video_file("NoRuleFile.mkv")
        temp_copy = os.path.join(self.temp_dir, "NoRuleFile.mkv")
        with open(temp_copy, 'w') as f:
            f.write("copied")

        MockCopier.return_value.copy_to_temp.return_value = [temp_copy]
        MockScraper.return_value.scrape.return_value = {
            "title_cn": "无规则电影",
            "year": "2023",
            "type": "movie",
            "dimensions": {"media_type": "unknown_type"},
            "confidence": 0.8,
        }
        MockHooks.return_value.run_before_process.return_value = None
        MockHooks.return_value.run_after_failure.return_value = None

        with patch('pipeline.classify') as mock_classify, \
             patch('pipeline.delete_source_files'):
            mock_classify.return_value = None
            pipeline = PipelineRunner(
                config=self.config, task_manager=self.tm,
                metrics=None, logger=None, notifier=None,
            )
            task = self.tm.create_task(
                video_path=video_path, video_file="NoRuleFile.mkv",
            )
            result = pipeline.process_one(task)
            self.assertFalse(result)
            self.assertEqual(task["status"], "FAILED")
            self.assertIn("分类匹配失败", task["error_message"])

    @patch('pipeline.HookRunner')
    @patch('pipeline.FileCopier')
    @patch('pipeline.LLMScraper')
    def test_05_confirm_task(self, MockScraper, MockCopier, MockHooks):
        from pipeline import PipelineRunner

        video_path = self._create_video_file("ConfirmTest.mkv")
        temp_copy = os.path.join(self.temp_dir, "ConfirmTest.mkv")
        with open(temp_copy, 'w') as f:
            f.write("copied")

        MockCopier.return_value.copy_to_temp.return_value = [temp_copy]
        MockScraper.return_value.scrape.return_value = {
            "title_cn": "确认测试",
            "year": "2024",
            "type": "movie",
            "dimensions": {"media_type": "movie", "restricted_level": "normal"},
            "confidence": 0.9,
        }
        MockHooks.return_value.run_before_process.return_value = None
        MockHooks.return_value.run_after_success.return_value = None

        self.config["manual_review"] = {"enabled": True}

        with patch('pipeline.classify') as mock_classify, \
             patch('pipeline.move_to_import') as mock_move, \
             patch('pipeline.apply_filename_template') as mock_rename, \
             patch('pipeline.delete_source_files'):
            mock_classify.return_value = os.path.join(self.import_dir, "movies", "确认测试 (2024)")
            mock_rename.return_value = "确认测试 (2024).mkv"
            mock_move.return_value = {
                "video": os.path.join(self.import_dir, "确认测试 (2024).mkv"),
                "subtitles": [],
            }

            pipeline = PipelineRunner(
                config=self.config, task_manager=self.tm,
                metrics=None, logger=None, notifier=None,
            )
            task = self.tm.create_task(
                video_path=video_path, video_file="ConfirmTest.mkv",
            )
            pipeline.process_one(task)
            self.assertEqual(task["status"], "CONFIRMING")

            ok = pipeline.confirm_task(task["task_id"])
            self.assertTrue(ok)
            updated = self.tm.get_task(task["task_id"])
            self.assertEqual(updated["status"], "SUCCESS")

    @patch('pipeline.HookRunner')
    @patch('pipeline.FileCopier')
    @patch('pipeline.LLMScraper')
    def test_06_confirm_task_wrong_status(self, MockScraper, MockCopier, MockHooks):
        from pipeline import PipelineRunner, PipelineError

        MockHooks.return_value.run_before_process.return_value = None
        pipeline = PipelineRunner(
            config=self.config, task_manager=self.tm,
            metrics=None, logger=None, notifier=None,
        )
        task = self.tm.create_task(
            video_path="/src/pending.mkv", video_file="pending.mkv",
        )
        with self.assertRaises(PipelineError):
            pipeline.confirm_task(task["task_id"])

    @patch('pipeline.HookRunner')
    @patch('pipeline.FileCopier')
    @patch('pipeline.LLMScraper')
    def test_08_reclassify_task(self, MockScraper, MockCopier, MockHooks):
        from pipeline import PipelineRunner

        video_path = self._create_video_file("ReclassifyTest.mkv")
        temp_copy = os.path.join(self.temp_dir, "ReclassifyTest.mkv")
        with open(temp_copy, 'w') as f:
            f.write("copied")

        MockCopier.return_value.copy_to_temp.return_value = [temp_copy]
        MockScraper.return_value.scrape.return_value = {
            "title_cn": "重分类测试",
            "year": "2024",
            "type": "movie",
            "dimensions": {"media_type": "movie", "restricted_level": "normal"},
            "confidence": 0.9,
        }
        MockHooks.return_value.run_before_process.return_value = None
        MockHooks.return_value.run_after_success.return_value = None

        self.config["manual_review"] = {"enabled": True}

        with patch('pipeline.classify') as mock_classify:
            mock_classify.return_value = os.path.join(self.import_dir, "movies", "重分类测试 (2024)")
            pipeline = PipelineRunner(
                config=self.config, task_manager=self.tm,
                metrics=None, logger=None, notifier=None,
            )
            task = self.tm.create_task(
                video_path=video_path, video_file="ReclassifyTest.mkv",
            )
            pipeline.process_one(task)
            self.assertEqual(task["status"], "CONFIRMING")

            with patch('pipeline.classify') as mock_classify2, \
                 patch('pipeline.move_to_import') as mock_move, \
                 patch('pipeline.apply_filename_template') as mock_rename:
                mock_classify2.return_value = os.path.join(self.import_dir, "tv", "重分类测试")
                mock_rename.return_value = "重分类测试.mkv"
                mock_move.return_value = {
                    "video": os.path.join(self.import_dir, "tv", "重分类测试", "重分类测试.mkv"),
                    "subtitles": [],
                }
                result = pipeline.reclassify_task(
                    task["task_id"],
                    {"media_type": "tv", "restricted_level": "normal"},
                )
                self.assertEqual(result["status"], "SUCCESS")

    def test_09_extract_series_name(self):
        from pipeline import _extract_series_name
        self.assertEqual(_extract_series_name("Breaking.Bad.S01E01.1080p.mkv"), "Breaking Bad")
        self.assertEqual(_extract_series_name("Game.of.Thrones.S02.mkv"), "Game of Thrones")

    @patch('pipeline.HookRunner')
    @patch('pipeline.FileCopier')
    @patch('pipeline.LLMScraper')
    def test_10_process_one_validate_failure(self, MockScraper, MockCopier, MockHooks):
        from pipeline import PipelineRunner

        video_path = self._create_video_file("EmptyScrape.mkv")
        temp_copy = os.path.join(self.temp_dir, "EmptyScrape.mkv")
        with open(temp_copy, 'w') as f:
            f.write("copied")

        MockCopier.return_value.copy_to_temp.return_value = [temp_copy]
        MockScraper.return_value.scrape.return_value = {
            "title_cn": "",
            "title_en": "",
            "year": "",
            "type": "",
            "dimensions": {},
            "confidence": 0.1,
        }
        MockHooks.return_value.run_before_process.return_value = None
        MockHooks.return_value.run_after_failure.return_value = None

        with patch('pipeline.delete_source_files'):
            pipeline = PipelineRunner(
                config=self.config, task_manager=self.tm,
                metrics=None, logger=None, notifier=None,
            )
            task = self.tm.create_task(
                video_path=video_path, video_file="EmptyScrape.mkv",
            )
            result = pipeline.process_one(task)
            self.assertFalse(result)
            self.assertEqual(task["status"], "FAILED")
            self.assertIn("刮削信息不足", task["error_message"])


# ============================================================
# 5. API Server 测试 - REST 端点
# ============================================================
class TestAPIServer(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="test_api_")
        self.db_path = os.path.join(self.tmpdir, "test_api.db")
        self.conn = db_module.init_db(self.db_path)
        self.config = {
            "source_dir": os.path.join(self.tmpdir, "source"),
            "temp_dir": os.path.join(self.tmpdir, "temp"),
            "manual_review": {"enabled": False},
            "source_dedup": {"enabled": True},
        }
        os.makedirs(self.config["source_dir"], exist_ok=True)
        os.makedirs(self.config["temp_dir"], exist_ok=True)
        self.tm = TaskManager(
            os.path.join(self.tmpdir, "api.json"), self.config
        )
        self.tm.conn = self.conn

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_01_task_stats(self):
        t1 = db_module.create_task(self.conn, source_path="/a.mkv", source_filename="a.mkv")
        db_module.update_task(self.conn, t1["task_id"], status="SUCCESS")
        t2 = db_module.create_task(self.conn, source_path="/b.mkv", source_filename="b.mkv")
        db_module.update_task(self.conn, t2["task_id"], status="FAILED")
        counts = self.tm.count_by_status()
        self.assertEqual(counts["SUCCESS"], 1)
        self.assertEqual(counts["FAILED"], 1)

    def test_02_task_subtitles(self):
        t = db_module.create_task(self.conn, source_path="/c.mkv", source_filename="c.mkv")
        db_module.create_subtitles(self.conn, t["task_id"], ["/c.chs.srt", "/c.eng.srt"])
        subs = db_module.get_subtitles_by_task(self.conn, t["task_id"])
        self.assertEqual(len(subs), 2)

    def test_03_task_ignore(self):
        t = db_module.create_task(self.conn, source_path="/d.mkv", source_filename="d.mkv")
        db_module.update_task(self.conn, t["task_id"], status="FAILED")
        db_module.update_task(self.conn, t["task_id"], status="SKIPPED", skip_reason="用户忽略")
        updated = db_module.get_task(self.conn, t["task_id"])
        self.assertEqual(updated["status"], "SKIPPED")

    def test_04_list_tasks_with_page(self):
        for i in range(30):
            db_module.create_task(
                self.conn,
                source_path=f"/page/v{i:03d}.mkv",
                source_filename=f"v{i:03d}.mkv",
            )
        rows, total, total_pages = db_module.list_tasks(self.conn, page=2, page_size=10)
        self.assertEqual(total, 30)
        self.assertEqual(total_pages, 3)
        self.assertEqual(len(rows), 10)

    def test_05_list_tasks_status_filter(self):
        t1 = db_module.create_task(self.conn, source_path="/f/a.mkv", source_filename="a.mkv")
        db_module.update_task(self.conn, t1["task_id"], status="CONFIRMING")
        t2 = db_module.create_task(self.conn, source_path="/f/b.mkv", source_filename="b.mkv")
        db_module.update_task(self.conn, t2["task_id"], status="SUCCESS")

        rows, total, _ = db_module.list_tasks(self.conn, page=1, page_size=20, status="CONFIRMING")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["status"], "CONFIRMING")

    def test_06_task_confirm_all_scenario(self):
        confirming_ids = []
        for i in range(3):
            t = db_module.create_task(
                self.conn,
                source_path=f"/conf/{i}.mkv",
                source_filename=f"{i}.mkv",
            )
            db_module.update_task(self.conn, t["task_id"], status="CONFIRMING")
            confirming_ids.append(t["task_id"])

        rows, total, _ = db_module.list_tasks(self.conn, page=1, page_size=20, status="CONFIRMING")
        self.assertEqual(total, 3)

    def test_08_task_retry_db_update(self):
        t = db_module.create_task(self.conn, source_path="/rt/a.mkv", source_filename="a.mkv")
        db_module.update_task(self.conn, t["task_id"], status="FAILED", retry_count=0)
        retried = self.tm.retry_task(t["task_id"])
        self.assertEqual(retried["status"], "PENDING")
        self.assertEqual(retried["retry_count"], 1)


# ============================================================
# 6. 端到端集成测试 - 完整流程模拟
# ============================================================
class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="test_e2e_")
        self.source_dir = os.path.join(self.tmpdir, "source")
        self.temp_dir = os.path.join(self.tmpdir, "temp")
        self.import_dir = os.path.join(self.tmpdir, "import")
        self.quarantine_dir = os.path.join(self.tmpdir, "quarantine")
        for d in [self.source_dir, self.temp_dir, self.import_dir, self.quarantine_dir]:
            os.makedirs(d, exist_ok=True)

        self.db_path = os.path.join(self.tmpdir, "e2e.db")
        self.conn = db_module.init_db(self.db_path)

        self.config = {
            "source_dir": self.source_dir,
            "temp_dir": self.temp_dir,
            "source_dedup": {
                "enabled": True,
                "quarantine_dir": self.quarantine_dir,
            },
            "manual_review": {"enabled": False},
            "duplicate_handling": {"enabled": False},
            "path_rules": [
                {
                    "conditions": {"media_type": "movie", "restricted_level": "normal"},
                    "template": os.path.join(self.import_dir, "movies", "{title_cn} ({year})"),
                },
                {
                    "conditions": {"media_type": "tv"},
                    "template": os.path.join(self.import_dir, "tv", "{title_cn}"),
                },
            ],
            "filename_templates": {
                "movie": "{title_cn} ({year}){ext}",
                "tv": "{title_cn} - S{season:02d}E{episode:02d}{ext}",
            },
            "source_file_handling": {"delete_after_process": False},
            "source_dedup": {"enabled": True},
            "_config_path": __file__,
        }

        self.tm = TaskManager(
            os.path.join(self.tmpdir, "e2e.json"), self.config
        )
        self.tm.conn = self.conn

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_source_file(self, filename, content="fake video"):
        fpath = os.path.join(self.source_dir, filename)
        with open(fpath, 'w') as f:
            f.write(content)
        return fpath

    @patch('pipeline.HookRunner')
    @patch('pipeline.FileCopier')
    @patch('pipeline.LLMScraper')
    def test_01_full_movie_pipeline(self, MockScraper, MockCopier, MockHooks):
        from pipeline import PipelineRunner

        video_path = self._create_source_file("The.Matrix.1999.mkv")
        temp_copy = os.path.join(self.temp_dir, "The.Matrix.1999.mkv")
        with open(temp_copy, 'w') as f:
            f.write("copied")

        MockCopier.return_value.copy_to_temp.return_value = [temp_copy]
        MockScraper.return_value.scrape.return_value = {
            "title_cn": "黑客帝国",
            "title_en": "The Matrix",
            "year": "1999",
            "type": "movie",
            "dimensions": {"media_type": "movie", "restricted_level": "normal"},
            "confidence": 0.98,
        }
        MockHooks.return_value.run_before_process.return_value = None
        MockHooks.return_value.run_after_success.return_value = None

        with patch('pipeline.classify') as mock_classify, \
             patch('pipeline.move_to_import') as mock_move, \
             patch('pipeline.apply_filename_template') as mock_rename:
            mock_classify.return_value = os.path.join(self.import_dir, "movies", "黑客帝国 (1999)")
            mock_rename.return_value = "黑客帝国 (1999).mkv"
            mock_move.return_value = {
                "video": os.path.join(self.import_dir, "黑客帝国 (1999).mkv"),
                "subtitles": [],
            }

            pipeline = PipelineRunner(
                config=self.config, task_manager=self.tm,
                metrics=None, logger=None, notifier=None,
            )
            task = self.tm.create_task(
                video_path=video_path, video_file="The.Matrix.1999.mkv",
                file_size_mb=1500.0,
            )
            result = pipeline.process_one(task)

            self.assertTrue(result)
            self.assertEqual(task["status"], "SUCCESS")
            self.assertEqual(task["scrape_title_cn"], "黑客帝国")
            self.assertEqual(task["scrape_year"], "1999")
            self.assertEqual(task["import_success"], 1)

            db_task = db_module.get_task(self.conn, task["task_id"])
            self.assertEqual(db_task["status"], "SUCCESS")
            self.assertIsNotNone(db_task["completed_at"])

    @patch('pipeline.HookRunner')
    @patch('pipeline.FileCopier')
    @patch('pipeline.LLMScraper')
    def test_02_confirming_then_confirm(self, MockScraper, MockCopier, MockHooks):
        from pipeline import PipelineRunner

        video_path = self._create_source_file("Review.Movie.2024.mkv")
        temp_copy = os.path.join(self.temp_dir, "Review.Movie.2024.mkv")
        with open(temp_copy, 'w') as f:
            f.write("copied")

        MockCopier.return_value.copy_to_temp.return_value = [temp_copy]
        MockScraper.return_value.scrape.return_value = {
            "title_cn": "审核电影",
            "year": "2024",
            "type": "movie",
            "dimensions": {"media_type": "movie", "restricted_level": "normal"},
            "confidence": 0.9,
        }
        MockHooks.return_value.run_before_process.return_value = None
        MockHooks.return_value.run_after_success.return_value = None

        self.config["manual_review"] = {"enabled": True}

        with patch('pipeline.classify') as mock_classify, \
             patch('pipeline.move_to_import') as mock_move, \
             patch('pipeline.apply_filename_template') as mock_rename, \
             patch('pipeline.delete_source_files'):
            mock_classify.return_value = os.path.join(self.import_dir, "movies", "审核电影 (2024)")
            mock_rename.return_value = "审核电影 (2024).mkv"
            mock_move.return_value = {
                "video": os.path.join(self.import_dir, "审核电影 (2024).mkv"),
                "subtitles": [],
            }

            pipeline = PipelineRunner(
                config=self.config, task_manager=self.tm,
                metrics=None, logger=None, notifier=None,
            )
            task = self.tm.create_task(
                video_path=video_path, video_file="Review.Movie.2024.mkv",
            )
            pipeline.process_one(task)
            self.assertEqual(task["status"], "CONFIRMING")

            ok = pipeline.confirm_task(task["task_id"])
            self.assertTrue(ok)

            db_task = db_module.get_task(self.conn, task["task_id"])
            self.assertEqual(db_task["status"], "SUCCESS")
            self.assertEqual(db_task["confirm_status"], "CONFIRMED")

    @patch('pipeline.HookRunner')
    @patch('pipeline.FileCopier')
    @patch('pipeline.LLMScraper')
    def test_04_confirming_then_reclassify(self, MockScraper, MockCopier, MockHooks):
        from pipeline import PipelineRunner

        video_path = self._create_source_file("Reclassify.Movie.2024.mkv")
        temp_copy = os.path.join(self.temp_dir, "Reclassify.Movie.2024.mkv")
        with open(temp_copy, 'w') as f:
            f.write("copied")

        MockCopier.return_value.copy_to_temp.return_value = [temp_copy]
        MockScraper.return_value.scrape.return_value = {
            "title_cn": "重分类电影",
            "year": "2024",
            "type": "movie",
            "dimensions": {"media_type": "movie", "restricted_level": "normal"},
            "confidence": 0.9,
        }
        MockHooks.return_value.run_before_process.return_value = None
        MockHooks.return_value.run_after_success.return_value = None

        self.config["manual_review"] = {"enabled": True}

        with patch('pipeline.classify') as mock_classify:
            mock_classify.return_value = os.path.join(self.import_dir, "movies", "重分类电影 (2024)")
            pipeline = PipelineRunner(
                config=self.config, task_manager=self.tm,
                metrics=None, logger=None, notifier=None,
            )
            task = self.tm.create_task(
                video_path=video_path, video_file="Reclassify.Movie.2024.mkv",
            )
            pipeline.process_one(task)
            self.assertEqual(task["status"], "CONFIRMING")

            with patch('pipeline.classify') as mock_classify2, \
                 patch('pipeline.move_to_import') as mock_move, \
                 patch('pipeline.apply_filename_template') as mock_rename:
                mock_classify2.return_value = os.path.join(self.import_dir, "tv", "重分类电影")
                mock_rename.return_value = "重分类电影.mkv"
                mock_move.return_value = {
                    "video": os.path.join(self.import_dir, "tv", "重分类电影", "重分类电影.mkv"),
                    "subtitles": [],
                }
                result = pipeline.reclassify_task(
                    task["task_id"],
                    {"media_type": "tv"},
                )
                self.assertEqual(result["status"], "SUCCESS")
                self.assertIn("tv", result["import_path"])

    def test_05_source_dedup_create_for_ended_task(self):
        t = db_module.create_task(
            self.conn,
            source_path=os.path.join(self.source_dir, "old_movie.mkv"),
            source_filename="old_movie.mkv",
        )
        db_module.update_task(self.conn, t["task_id"], status="SUCCESS")

        video_path = self._create_source_file("old_movie.mkv")

        dedup = self.tm.check_source_duplicate(video_path)
        self.assertEqual(dedup["action"], "CREATE")

    def test_06_source_dedup_skip_processing(self):
        t = db_module.create_task(
            self.conn,
            source_path=os.path.join(self.source_dir, "processing.mkv"),
            source_filename="processing.mkv",
        )
        db_module.update_task(self.conn, t["task_id"], status="PROCESSING")

        dedup = self.tm.check_source_duplicate(
            os.path.join(self.source_dir, "processing.mkv")
        )
        self.assertEqual(dedup["action"], "SKIP")

    def test_07_source_dedup_failed_returns_create(self):
        t = db_module.create_task(
            self.conn,
            source_path=os.path.join(self.source_dir, "retry_movie.mkv"),
            source_filename="retry_movie.mkv",
        )
        db_module.update_task(self.conn, t["task_id"], status="FAILED", retry_count=1)

        dedup = self.tm.check_source_duplicate(
            os.path.join(self.source_dir, "retry_movie.mkv")
        )
        self.assertEqual(dedup["action"], "CREATE")

    def test_08_multiple_tasks_batch_stats(self):
        for i in range(5):
            t = db_module.create_task(
                self.conn,
                source_path=f"/batch/{i}.mkv",
                source_filename=f"{i}.mkv",
            )
            if i < 2:
                db_module.update_task(self.conn, t["task_id"], status="SUCCESS")
            elif i < 4:
                db_module.update_task(self.conn, t["task_id"], status="FAILED")

        counts = db_module.count_by_status(self.conn)
        self.assertEqual(counts["SUCCESS"], 2)
        self.assertEqual(counts["FAILED"], 2)
        self.assertEqual(counts["PENDING"], 1)

    def test_09_subtitle_lifecycle(self):
        t = db_module.create_task(
            self.conn,
            source_path="/lifecycle/video.mkv",
            source_filename="video.mkv",
        )
        subs = db_module.create_subtitles(
            self.conn, t["task_id"],
            ["/lifecycle/video.chs.srt", "/lifecycle/video.eng.srt"],
        )
        self.assertEqual(len(subs), 2)

        db_module.update_subtitle(
            self.conn, subs[0]["id"],
            status="SUCCESS", lang="chs", import_path="/import/video.chs.srt"
        )
        db_module.update_subtitle(
            self.conn, subs[1]["id"],
            status="SUCCESS", lang="eng", import_path="/import/video.eng.srt"
        )

        total, success = db_module.count_subtitles_by_task(self.conn, t["task_id"])
        self.assertEqual(total, 2)
        self.assertEqual(success, 2)

        db_module.update_subtitles_by_task(
            self.conn, t["task_id"],
            confirm_status="CONFIRMED",
        )
        all_subs = db_module.get_subtitles_by_task(self.conn, t["task_id"])
        for s in all_subs:
            self.assertEqual(s["confirm_status"], "CONFIRMED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
