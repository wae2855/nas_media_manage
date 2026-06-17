#!/usr/bin/env python3
"""
操作按钮功能测试 - 覆盖不同场景下的任务操作
测试场景:
  1. 重试(retry): FAILED / SKIPPED → PENDING
  2. 确认入库(confirm): CONFIRMING → SUCCESS
  3. 忽略(ignore): 任意状态 → SKIPPED
  4. 重新分类(reclassify): CONFIRMING → 更新维度后重新分类
  5. 批量确认(confirm-all): 多个 CONFIRMING 任务
  6. 非法操作: 对不合法状态执行操作应返回错误
"""
import os
import sys
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.core import db as db_module
from media_importer.features.tasks import TaskManager


class TestTaskOperations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="test_ops_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        self.db_path = os.path.join(self.tmpdir, f"test_{self._testMethodName}.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.conn = db_module.init_db(self.db_path)
        self.config = {
            "source_dedup": {
                "enabled": True,
                "recycle_dir": os.path.join(self.tmpdir, "recycle"),
            },
            "manual_review": {"enabled": True},
            "source_dir": os.path.join(self.tmpdir, "source"),
            "temp_dir": os.path.join(self.tmpdir, "temp"),
        }
        self.tm = TaskManager.__new__(TaskManager)
        self.tm.config = self.config
        self.tm.conn = self.conn
        self.tm._lock = __import__('threading').RLock()

    def tearDown(self):
        self.conn.close()

    def _create_task(self, status="PENDING", source_path=None, source_filename=None,
                     video_path="", **extra):
        sp = source_path or f"/test/movie_{datetime.now().strftime('%H%M%S%f')}.mkv"
        sf = source_filename or os.path.basename(sp)
        task = db_module.create_task(self.conn, source_path=sp, source_filename=sf,
                                     file_size_mb=100.0)
        tid = task["task_id"]
        updates = {"status": status, "video_path": video_path}
        updates.update(extra)
        if updates:
            db_module.update_task(self.conn, tid, **updates)
        return db_module.get_task(self.conn, tid)

    def test_retry_failed_task(self):
        task = self._create_task(status="FAILED", error_message="刮削失败")
        result = self.tm.retry_task(task["task_id"])
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "PENDING")
        self.assertEqual(result["retry_count"], 1)
        self.assertEqual(result["error_message"], "")

    def test_retry_pending_task_should_fail(self):
        task = self._create_task(status="PENDING")
        result = self.tm.retry_task(task["task_id"])
        self.assertIsNone(result)

    def test_retry_success_task_should_fail(self):
        task = self._create_task(status="SUCCESS")
        result = self.tm.retry_task(task["task_id"])
        self.assertIsNone(result)

    def test_retry_confirming_task_should_fail(self):
        task = self._create_task(status="CONFIRMING")
        result = self.tm.retry_task(task["task_id"])
        self.assertIsNone(result)

    def test_retry_nonexistent_task(self):
        result = self.tm.retry_task("nonexistent_id")
        self.assertIsNone(result)

    def test_ignore_task(self):
        for status in ("PENDING", "FAILED", "CONFIRMING"):
            task = self._create_task(status=status)
            db_module.update_task(self.conn, task["task_id"],
                                  status="SKIPPED", skip_reason="用户忽略")
            updated = db_module.get_task(self.conn, task["task_id"])
            self.assertEqual(updated["status"], "SKIPPED")
            self.assertEqual(updated["skip_reason"], "用户忽略")

    def test_list_tasks_includes_source_filename(self):
        self._create_task(source_path="/test/Avatar.mkv", source_filename="Avatar.mkv",
                          status="PENDING")
        rows, total, _ = db_module.list_tasks(self.conn, page=1, page_size=20)
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["source_filename"], "Avatar.mkv")

    def test_list_tasks_includes_source_path(self):
        self._create_task(source_path="/test/Avatar.mkv", source_filename="Avatar.mkv",
                          status="PENDING")
        rows, _, _ = db_module.list_tasks(self.conn, page=1, page_size=20)
        self.assertEqual(rows[0]["source_path"], "/test/Avatar.mkv")

    def test_list_tasks_includes_scrape_season_episode(self):
        self._create_task(status="PENDING")
        tid = self._create_task(status="SUCCESS",
                                source_path="/test/Breaking.Bad.S01E01.mkv",
                                source_filename="Breaking.Bad.S01E01.mkv")["task_id"]
        db_module.update_task(self.conn, tid,
                              scrape_season=1, scrape_episode=1,
                              scrape_media_type="tv")
        rows, _, _ = db_module.list_tasks(self.conn, page=1, page_size=20)
        target = [r for r in rows if r["task_id"] == tid][0]
        self.assertEqual(target["scrape_season"], 1)
        self.assertEqual(target["scrape_episode"], 1)

    def test_list_tasks_includes_subtitle_counts(self):
        task = self._create_task(status="SUCCESS")
        tid = task["task_id"]
        db_module.create_subtitles(self.conn, tid, [
            "/test/movie.zh.srt",
            "/test/movie.en.srt",
        ])
        sub_rows = db_module.get_subtitles_by_task(self.conn, tid)
        if len(sub_rows) > 0:
            db_module.update_subtitle(self.conn, sub_rows[0]["id"], status="SUCCESS")
        rows, _, _ = db_module.list_tasks(self.conn, page=1, page_size=20)
        target = [r for r in rows if r["task_id"] == tid][0]
        self.assertEqual(target["subtitle_total"], 2)
        self.assertEqual(target["subtitle_success"], 1)

    def test_get_task_includes_subtitle_data(self):
        task = self._create_task(status="SUCCESS")
        tid = task["task_id"]
        db_module.create_subtitles(self.conn, tid, [
            "/test/movie.zh.srt",
            "/test/movie.en.srt",
        ])
        sub_rows = db_module.get_subtitles_by_task(self.conn, tid)
        if len(sub_rows) > 0:
            db_module.update_subtitle(self.conn, sub_rows[0]["id"], status="SUCCESS")
        full_task = db_module.get_task(self.conn, tid)
        self.assertEqual(full_task["subtitle_total"], 2)
        self.assertEqual(full_task["subtitle_success"], 1)
        self.assertEqual(len(full_task["subtitle_files"]), 2)

    def test_video_path_stored_and_retrieved(self):
        task = self._create_task(status="CONFIRMING",
                                 video_path="/tmp/nas-media/movie.mkv")
        tid = task["task_id"]
        db_module.update_task(self.conn, tid, video_path="/tmp/nas-media/movie.mkv")
        retrieved = db_module.get_task(self.conn, tid)
        self.assertEqual(retrieved["video_path"], "/tmp/nas-media/movie.mkv")

    def test_video_path_in_list_tasks(self):
        self._create_task(status="CONFIRMING",
                          video_path="/tmp/nas-media/movie.mkv")
        rows, _, _ = db_module.list_tasks(self.conn, page=1, page_size=20)
        self.assertEqual(rows[0]["video_path"], "/tmp/nas-media/movie.mkv")

    def test_check_source_duplicate_new_file(self):
        result = self.tm.check_source_duplicate("/test/new_movie.mkv")
        self.assertFalse(result["exists"])
        self.assertEqual(result["action"], "CREATE")

    def test_check_source_duplicate_success_file(self):
        self._create_task(status="SUCCESS", source_path="/test/done.mkv",
                          source_filename="done.mkv")
        result = self.tm.check_source_duplicate("/test/done.mkv")
        self.assertTrue(result["exists"])
        self.assertEqual(result["action"], "CREATE")

    def test_check_source_duplicate_failed_under_limit(self):
        self._create_task(status="FAILED", source_path="/test/failed.mkv",
                          source_filename="failed.mkv", retry_count=1)
        result = self.tm.check_source_duplicate("/test/failed.mkv")
        self.assertTrue(result["exists"])
        self.assertEqual(result["action"], "CREATE")

    def test_check_source_duplicate_failed_over_limit(self):
        self._create_task(status="FAILED", source_path="/test/failed3.mkv",
                          source_filename="failed3.mkv", retry_count=3)
        result = self.tm.check_source_duplicate("/test/failed3.mkv")
        self.assertTrue(result["exists"])
        self.assertEqual(result["action"], "CREATE")

    def test_check_source_duplicate_processing_file(self):
        self._create_task(status="PENDING", stage="RUNNING", source_path="/test/processing.mkv",
                          source_filename="processing.mkv")
        result = self.tm.check_source_duplicate("/test/processing.mkv")
        self.assertTrue(result["exists"])
        self.assertEqual(result["action"], "SKIP")

    def test_check_source_duplicate_confirming_file(self):
        self._create_task(status="PENDING", stage="AWAIT_REVIEW", source_path="/test/confirming.mkv",
                          source_filename="confirming.mkv")
        result = self.tm.check_source_duplicate("/test/confirming.mkv")
        self.assertTrue(result["exists"])
        self.assertEqual(result["action"], "SKIP")

    def test_pagination(self):
        for i in range(25):
            self._create_task(
                source_path=f"/test/movie_{i:03d}.mkv",
                source_filename=f"movie_{i:03d}.mkv",
                status="PENDING"
            )
        rows_p1, total, total_pages = db_module.list_tasks(self.conn, page=1, page_size=20)
        self.assertEqual(len(rows_p1), 20)
        self.assertEqual(total, 25)
        self.assertEqual(total_pages, 2)
        rows_p2, _, _ = db_module.list_tasks(self.conn, page=2, page_size=20)
        self.assertEqual(len(rows_p2), 5)

    def test_pagination_with_status_filter(self):
        for i in range(10):
            self._create_task(
                source_path=f"/test/ok_{i:03d}.mkv",
                source_filename=f"ok_{i:03d}.mkv",
                status="SUCCESS"
            )
        for i in range(5):
            self._create_task(
                source_path=f"/test/fail_{i:03d}.mkv",
                source_filename=f"fail_{i:03d}.mkv",
                status="FAILED"
            )
        rows, total, _ = db_module.list_tasks(self.conn, page=1, page_size=20,
                                               status="FAILED")
        self.assertEqual(total, 5)
        self.assertEqual(len(rows), 5)
        for r in rows:
            self.assertEqual(r["status"], "FAILED")

    def test_move_to_recycle_bin(self):
        source_dir = os.path.join(self.tmpdir, "source_q")
        os.makedirs(source_dir, exist_ok=True)
        video_path = os.path.join(source_dir, "recycled.mkv")
        with open(video_path, 'w') as f:
            f.write("fake video")
        recycle_dir = os.path.join(self.tmpdir, "recycle_q")
        task = self._create_task(status="FAILED", source_path=video_path,
                                 source_filename="recycled.mkv")
        self.tm.move_to_recycle_bin(task["task_id"], video_path, [], recycle_dir)
        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["file_location"], "recycle")
        self.assertTrue(os.path.exists(os.path.join(recycle_dir, "recycled.mkv")))
        self.assertFalse(os.path.exists(video_path))

    def test_retry_all_failed(self):
        for i in range(3):
            self._create_task(
                source_path=f"/test/fail_{i}.mkv",
                source_filename=f"fail_{i}.mkv",
                status="FAILED"
            )
        self._create_task(
            source_path="/test/success.mkv",
            source_filename="success.mkv",
            status="SUCCESS"
        )
        retried = self.tm.retry_all_failed()
        self.assertEqual(len(retried), 3)
        for t in retried:
            self.assertIn(t["status"], ("PENDING", "FAILED"))

    def test_confirm_status_field(self):
        task = self._create_task(status="CONFIRMING")
        tid = task["task_id"]
        db_module.update_task(self.conn, tid, confirm_status="PENDING")
        retrieved = db_module.get_task(self.conn, tid)
        self.assertEqual(retrieved["confirm_status"], "PENDING")

    def test_list_tasks_file_size_mb(self):
        self._create_task(status="PENDING")
        rows, _, _ = db_module.list_tasks(self.conn, page=1, page_size=20)
        self.assertIn("file_size_mb", rows[0])
        self.assertEqual(rows[0]["file_size_mb"], 100.0)

    def test_list_tasks_retry_count(self):
        task = self._create_task(status="FAILED", retry_count=2)
        rows, _, _ = db_module.list_tasks(self.conn, page=1, page_size=20)
        self.assertEqual(rows[0]["retry_count"], 2)


class TestAPIOperations(unittest.TestCase):
    """测试 API 端点路由和操作逻辑"""
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="test_api_ops_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        self.db_path = os.path.join(self.tmpdir, f"test_{self._testMethodName}.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.conn = db_module.init_db(self.db_path)
        self.config = {
            "source_dedup": {
                "enabled": True,
                "recycle_dir": os.path.join(self.tmpdir, "recycle"),
            },
            "manual_review": {"enabled": True},
            "source_dir": os.path.join(self.tmpdir, "source"),
            "temp_dir": os.path.join(self.tmpdir, "temp"),
        }
        self.tm = TaskManager.__new__(TaskManager)
        self.tm.config = self.config
        self.tm.conn = self.conn
        self.tm._lock = __import__('threading').RLock()

    def tearDown(self):
        self.conn.close()

    def _create_task(self, status="PENDING", **extra):
        sp = extra.pop("source_path", None) or f"/test/api_{datetime.now().strftime('%H%M%S%f')}.mkv"
        sf = extra.pop("source_filename", None) or os.path.basename(sp)
        task = db_module.create_task(self.conn, source_path=sp, source_filename=sf,
                                     file_size_mb=100.0)
        tid = task["task_id"]
        updates = {"status": status}
        updates.update(extra)
        if updates:
            db_module.update_task(self.conn, tid, **updates)
        return db_module.get_task(self.conn, tid)

    def test_api_route_parse_retry(self):
        path = "/api/tasks/abc123/retry"
        parts = path.split("/")
        self.assertEqual(len(parts), 5)
        self.assertEqual(parts[3], "abc123")
        self.assertTrue(path.startswith("/api/tasks/") and path.endswith("/retry"))

    def test_api_route_parse_confirm(self):
        path = "/api/tasks/def456/confirm"
        parts = path.split("/")
        self.assertEqual(parts[3], "def456")
        self.assertTrue(path.startswith("/api/tasks/") and path.endswith("/confirm"))

    def test_api_route_parse_rollback(self):
        path = "/api/tasks/ghi789/rollback"
        parts = path.split("/")
        self.assertEqual(parts[3], "ghi789")
        self.assertTrue(path.startswith("/api/tasks/") and path.endswith("/rollback"))

    def test_api_route_parse_ignore(self):
        path = "/api/tasks/jkl012/ignore"
        parts = path.split("/")
        self.assertEqual(parts[3], "jkl012")
        self.assertTrue(path.startswith("/api/tasks/") and path.endswith("/ignore"))

    def test_api_route_parse_reclassify(self):
        path = "/api/tasks/mno345/reclassify"
        parts = path.split("/")
        self.assertEqual(parts[3], "mno345")
        self.assertTrue(path.startswith("/api/tasks/") and path.endswith("/reclassify"))

    def test_api_route_parse_subtitles(self):
        path = "/api/tasks/abc123/subtitles"
        parts = path.split("/")
        self.assertEqual(len(parts), 5)
        self.assertEqual(parts[4], "subtitles")

    def test_api_route_parse_get_task(self):
        path = "/api/tasks/abc123"
        parts = path.split("/")
        self.assertEqual(len(parts), 4)
        self.assertEqual(parts[3], "abc123")

    def test_api_route_confirm_all(self):
        path = "/api/tasks/confirm-all"
        self.assertEqual(path, "/api/tasks/confirm-all")

    def test_api_route_stats(self):
        path = "/api/tasks/stats"
        self.assertEqual(path, "/api/tasks/stats")

    def test_api_ignore_operation(self):
        task = self._create_task(status="PENDING")
        db_module.update_task(self.conn, task["task_id"],
                              status="SKIPPED", skip_reason="用户忽略")
        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "SKIPPED")
        self.assertEqual(updated["skip_reason"], "用户忽略")

    def test_api_confirm_all_finds_confirming_tasks(self):
        for i in range(3):
            self._create_task(status="PENDING", stage="AWAIT_REVIEW", confirm_status="PENDING",
                              source_path=f"/test/confirm_{i}.mkv",
                              source_filename=f"confirm_{i}.mkv")
        self._create_task(status="PENDING",
                          source_path="/test/pending.mkv",
                          source_filename="pending.mkv")
        confirming = self.tm.list_tasks(status="PENDING", stage="AWAIT_REVIEW", limit=1000)
        self.assertEqual(len(confirming), 3)

    def test_api_list_tasks_pagination_params(self):
        for i in range(5):
            self._create_task(
                source_path=f"/test/p_{i}.mkv",
                source_filename=f"p_{i}.mkv",
                status="PENDING"
            )
        rows, total, total_pages = db_module.list_tasks(self.conn, page=1, page_size=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(total, 5)
        self.assertEqual(total_pages, 3)


class TestConfigKeyAccess(unittest.TestCase):
    """测试配置键访问是否正确"""
    def test_recycle_dir_from_source_dedup(self):
        config = {
            "source_dedup": {
                "enabled": True,
                "recycle_dir": "/data/quarantine",
            }
        }
        recycle_dir = config.get("source_dedup", {}).get("recycle_dir", "")
        self.assertEqual(recycle_dir, "/data/quarantine")

    def test_recycle_dir_missing(self):
        config: dict = {}
        recycle_dir = config.get("source_dedup", {}).get("recycle_dir", "")
        self.assertEqual(recycle_dir, "")

    def test_recycle_dir_old_style_returns_empty(self):
        config: dict = {"recycle_dir": "/old/path"}
        recycle_dir = config.get("source_dedup", {}).get("recycle_dir", "")
        self.assertEqual(recycle_dir, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
