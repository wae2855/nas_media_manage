#!/usr/bin/env python3
"""
NAS影视入库系统 - 全流程测试（状态简化后）
覆盖 6 种状态: PENDING / PROCESSING / SUCCESS / FAILED / SKIPPED / CONFIRMING
测试场景:
  A. 正常流程: PENDING → PROCESSING → SUCCESS
  B. 失败流程: PENDING → PROCESSING → FAILED (含隔离区)
  C. 跳过流程: PENDING → PROCESSING → SKIPPED (去重/质量判定)
  D. 重试流程: FAILED/SKIPPED → PENDING
  E. 忽略流程: FAILED/CONFIRMING → SKIPPED
  F. 人工确认流程: CONFIRMING → SUCCESS
  G. 修改分类流程: CONFIRMING → reclassify → SUCCESS
  H. 删除任务
  I. DB 迁移: 旧状态 → 新状态
  J. 状态验证: VALID_STATUSES / 旧API已移除
  K. 队列控制
  L. 改名 API
"""
import os
import sys
import json
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'media_importer'))

import db as db_module
from db import VALID_STATUSES
from task_manager import TaskManager
from pipeline import PipelineRunner, PipelineError, PipelineSkipError


class BaseTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="nas_test_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        self.db_path = os.path.join(self.tmpdir, f"test_{self._testMethodName}.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.conn = db_module.init_db(self.db_path)

        self.source_dir = os.path.join(self.tmpdir, "source")
        self.temp_dir = os.path.join(self.tmpdir, "temp")
        self.quarantine_dir = os.path.join(self.tmpdir, "quarantine")
        self.import_dir = os.path.join(self.tmpdir, "import")

        for d in [self.source_dir, self.temp_dir, self.quarantine_dir, self.import_dir]:
            os.makedirs(d, exist_ok=True)

        self.config = {
            "source_dir": self.source_dir,
            "temp_dir": self.temp_dir,
            "log_dir": os.path.join(self.tmpdir, "logs"),
            "source_policy": {
                "dedup_enabled": True,
                "quarantine_dir": self.quarantine_dir,
                "scan_recursive": True,
                "scan_max_depth": 5,
            },
            "manual_review": {"enabled": False},
            "duplicate_handling": {"strategy": "quality"},
            "path_rules": [
                {"conditions": {"media_type": "movie", "documentary": "false"},
                 "template": os.path.join(self.import_dir, "movies")},
                {"conditions": {"media_type": "tv", "documentary": "false"},
                 "template": os.path.join(self.import_dir, "tv")},
                {"conditions": {"media_type": "movie", "documentary": "true"},
                 "template": os.path.join(self.import_dir, "doc_movies")},
                {"conditions": {"media_type": "tv", "documentary": "true"},
                 "template": os.path.join(self.import_dir, "doc_tv")},
            ],
            "filename_templates": {
                "movie": "{title_cn}.{year}.{ext}",
                "tv": "{title_cn}.S{season}E{episode}.{ext}",
                "subtitle": "{video_filename}.{lang}.{ext}",
            },
            "video_extensions": [".mkv", ".mp4", ".avi", ".ts"],
            "subtitle_extensions": [".srt", ".ass"],
            "dimensions": [
                {"name": "media_type", "label": "影视类型", "values": ["movie", "tv"]},
                {"name": "documentary", "label": "是否纪录片", "values": ["true", "false"]},
            ],
            "_config_path": os.path.join(self.tmpdir, "config.yaml"),
        }

        self.tm = TaskManager.__new__(TaskManager)
        self.tm.config = self.config
        self.tm.conn = self.conn
        self.tm._lock = threading.RLock()

    def tearDown(self):
        self.conn.close()

    def _create_source_file(self, filename, content="fake video", subdir=""):
        d = os.path.join(self.source_dir, subdir) if subdir else self.source_dir
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, filename)
        with open(path, 'w') as f:
            f.write(content)
        return path

    def _create_task(self, status="PENDING", source_path=None, source_filename=None,
                     file_location="source", **extra):
        sp = source_path or f"{self.source_dir}/movie_{datetime.now().strftime('%H%M%S%f')}.mkv"
        sf = source_filename or os.path.basename(sp)
        task = db_module.create_task(self.conn, source_path=sp, source_filename=sf,
                                     file_size_mb=100.0)
        tid = task["task_id"]
        updates = {"status": status, "file_location": file_location}
        updates.update(extra)
        if updates:
            db_module.update_task(self.conn, tid, **updates)
        return db_module.get_task(self.conn, tid)

    def _mock_scrape_result(self, title_cn="测试电影", title_en="TestMovie",
                            year="2024", media_type="movie", confidence=0.9,
                            dimensions=None, **extra):
        result = {
            "title_cn": title_cn,
            "title_en": title_en,
            "year": year,
            "type": media_type,
            "confidence": confidence,
            "dimensions": dimensions or {"media_type": media_type, "documentary": "false"},
        }
        result.update(extra)
        return result

    def _make_pipeline(self, manual_review=False):
        self.config["manual_review"]["enabled"] = manual_review
        pipeline = PipelineRunner.__new__(PipelineRunner)
        pipeline.config = self.config
        pipeline.task_manager = self.tm
        pipeline.metrics = None
        pipeline.logger = None
        pipeline.notifier = None
        pipeline._paused = threading.Event()
        pipeline._last_notified_error = None
        pipeline._last_notified_time = 0
        pipeline._error_notify_cooldown = 300
        pipeline.hooks = MagicMock()
        pipeline.hooks.run_before_process = MagicMock()
        pipeline.hooks.run_after_success = MagicMock()
        pipeline.hooks.run_after_failure = MagicMock()
        return pipeline


# ============================================================
# A. 正常流程: PENDING → PROCESSING → SUCCESS
# ============================================================
class TestANormalFlow(BaseTestCase):
    """A. 正常流程: PENDING → PROCESSING → SUCCESS"""

    def test_A1_create_task_pending(self):
        source_path = self._create_source_file("NormalMovie.2024.1080p.mkv")
        task = self.tm.create_task(
            video_path=source_path,
            video_file="NormalMovie.2024.1080p.mkv",
            file_size_mb=100.0,
        )
        self.assertEqual(task["status"], "PENDING")
        self.assertEqual(task["source_filename"], "NormalMovie.2024.1080p.mkv")
        self.assertEqual(task["file_location"], "source")

    @patch('pipeline.LLMScraper')
    @patch('pipeline.FileCopier')
    def test_A2_process_to_success(self, MockCopier, MockScraper):
        source_path = self._create_source_file("SuccessMovie.2024.mkv")

        copier_instance = MagicMock()
        copier_instance.copy_to_temp.return_value = [
            os.path.join(self.temp_dir, "SuccessMovie.2024.mkv"),
        ]
        MockCopier.return_value = copier_instance

        scraper_instance = MagicMock()
        scraper_instance.scrape.return_value = self._mock_scrape_result(
            title_cn="成功电影", year="2024"
        )
        MockScraper.return_value = scraper_instance

        pipeline = self._make_pipeline()
        pipeline.copier = copier_instance
        pipeline.scraper = scraper_instance

        task = self.tm.create_task(
            video_path=source_path,
            video_file="SuccessMovie.2024.mkv",
            file_size_mb=100.0,
        )

        with patch.object(pipeline, '_step_import'):
            with patch.object(pipeline, '_step_dedup'):
                result = pipeline.process_one(task)

        self.assertTrue(result)
        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "SUCCESS")
        self.assertEqual(updated["import_success"], 1)
        self.assertEqual(updated["file_location"], "import")

    @patch('pipeline.LLMScraper')
    @patch('pipeline.FileCopier')
    def test_A3_success_file_location_import(self, MockCopier, MockScraper):
        source_path = self._create_source_file("LocTest.2024.mkv")

        copier_instance = MagicMock()
        copier_instance.copy_to_temp.return_value = [
            os.path.join(self.temp_dir, "LocTest.2024.mkv"),
        ]
        MockCopier.return_value = copier_instance

        scraper_instance = MagicMock()
        scraper_instance.scrape.return_value = self._mock_scrape_result()
        MockScraper.return_value = scraper_instance

        pipeline = self._make_pipeline()
        pipeline.copier = copier_instance
        pipeline.scraper = scraper_instance

        task = self.tm.create_task(
            video_path=source_path,
            video_file="LocTest.2024.mkv",
            file_size_mb=100.0,
        )

        with patch.object(pipeline, '_step_import'):
            with patch.object(pipeline, '_step_dedup'):
                pipeline.process_one(task)

        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["file_location"], "import")
        self.assertEqual(updated["import_success"], 1)


# ============================================================
# B. 失败流程: PENDING → PROCESSING → FAILED
# ============================================================
class TestBFailureFlow(BaseTestCase):
    """B. 失败流程: PENDING → PROCESSING → FAILED"""

    @patch('pipeline.LLMScraper')
    @patch('pipeline.FileCopier')
    def test_B1_scrape_failure(self, MockCopier, MockScraper):
        from llm_scraper import LLMScrapeError

        source_path = self._create_source_file("FailMovie.2024.mkv")

        copier_instance = MagicMock()
        copier_instance.copy_to_temp.return_value = [
            os.path.join(self.temp_dir, "FailMovie.2024.mkv"),
        ]
        MockCopier.return_value = copier_instance

        scraper_instance = MagicMock()
        scraper_instance.scrape.side_effect = LLMScrapeError("API连接超时")
        MockScraper.return_value = scraper_instance

        pipeline = self._make_pipeline()
        pipeline.copier = copier_instance
        pipeline.scraper = scraper_instance

        task = self.tm.create_task(
            video_path=source_path,
            video_file="FailMovie.2024.mkv",
            file_size_mb=100.0,
        )

        result = pipeline.process_one(task)
        self.assertFalse(result)

        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "FAILED")
        self.assertIn("API连接超时", updated["error_message"])

    @patch('pipeline.LLMScraper')
    @patch('pipeline.FileCopier')
    def test_B2_failed_moved_to_quarantine(self, MockCopier, MockScraper):
        from llm_scraper import LLMScrapeError

        source_path = self._create_source_file("QuarantineMovie.2024.mkv")

        copier_instance = MagicMock()
        copier_instance.copy_to_temp.return_value = [
            os.path.join(self.temp_dir, "QuarantineMovie.2024.mkv"),
        ]
        MockCopier.return_value = copier_instance

        scraper_instance = MagicMock()
        scraper_instance.scrape.side_effect = LLMScrapeError("刮削失败")
        MockScraper.return_value = scraper_instance

        pipeline = self._make_pipeline()
        pipeline.copier = copier_instance
        pipeline.scraper = scraper_instance

        task = self.tm.create_task(
            video_path=source_path,
            video_file="QuarantineMovie.2024.mkv",
            file_size_mb=100.0,
        )

        pipeline.process_one(task)

        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "FAILED")
        self.assertEqual(updated["file_location"], "quarantine")
        self.assertTrue(os.path.exists(
            os.path.join(self.quarantine_dir, "QuarantineMovie.2024.mkv")))

    @patch('pipeline.LLMScraper')
    @patch('pipeline.FileCopier')
    def test_B3_classify_failure(self, MockCopier, MockScraper):
        source_path = self._create_source_file("NoRuleMovie.2024.mkv")

        copier_instance = MagicMock()
        copier_instance.copy_to_temp.return_value = [
            os.path.join(self.temp_dir, "NoRuleMovie.2024.mkv"),
        ]
        MockCopier.return_value = copier_instance

        scraper_instance = MagicMock()
        scraper_instance.scrape.return_value = self._mock_scrape_result(
            dimensions={"media_type": "unknown", "documentary": "false"}
        )
        MockScraper.return_value = scraper_instance

        pipeline = self._make_pipeline()
        pipeline.copier = copier_instance
        pipeline.scraper = scraper_instance

        task = self.tm.create_task(
            video_path=source_path,
            video_file="NoRuleMovie.2024.mkv",
            file_size_mb=100.0,
        )

        result = pipeline.process_one(task)
        self.assertFalse(result)

        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "FAILED")
        self.assertIn("分类匹配失败", updated["error_message"])

    @patch('pipeline.LLMScraper')
    @patch('pipeline.FileCopier')
    def test_B4_validate_failure(self, MockCopier, MockScraper):
        source_path = self._create_source_file("BadScrape.2024.mkv")

        copier_instance = MagicMock()
        copier_instance.copy_to_temp.return_value = [
            os.path.join(self.temp_dir, "BadScrape.2024.mkv"),
        ]
        MockCopier.return_value = copier_instance

        scraper_instance = MagicMock()
        scraper_instance.scrape.return_value = {
            "title_cn": "",
            "title_en": "",
            "year": "",
            "type": "",
            "confidence": 0.1,
            "dimensions": {},
            "low_confidence": True,
        }
        MockScraper.return_value = scraper_instance

        pipeline = self._make_pipeline()
        pipeline.copier = copier_instance
        pipeline.scraper = scraper_instance

        task = self.tm.create_task(
            video_path=source_path,
            video_file="BadScrape.2024.mkv",
            file_size_mb=100.0,
        )

        result = pipeline.process_one(task)
        self.assertTrue(result)

        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "CONFIRMING")

    @patch('pipeline.LLMScraper')
    @patch('pipeline.FileCopier')
    def test_B5_failed_no_quarantine_dir(self, MockCopier, MockScraper):
        from llm_scraper import LLMScrapeError

        source_path = self._create_source_file("NoQuarantine.2024.mkv")

        self.config["source_policy"]["quarantine_dir"] = ""

        copier_instance = MagicMock()
        copier_instance.copy_to_temp.return_value = [
            os.path.join(self.temp_dir, "NoQuarantine.2024.mkv"),
        ]
        MockCopier.return_value = copier_instance

        scraper_instance = MagicMock()
        scraper_instance.scrape.side_effect = LLMScrapeError("失败")
        MockScraper.return_value = scraper_instance

        pipeline = self._make_pipeline()
        pipeline.copier = copier_instance
        pipeline.scraper = scraper_instance

        task = self.tm.create_task(
            video_path=source_path,
            video_file="NoQuarantine.2024.mkv",
            file_size_mb=100.0,
        )

        pipeline.process_one(task)

        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "FAILED")
        self.assertEqual(updated["file_location"], "source")

        self.config["source_policy"]["quarantine_dir"] = self.quarantine_dir


# ============================================================
# C. 跳过流程: PENDING → PROCESSING → SKIPPED
# ============================================================
class TestCSkipFlow(BaseTestCase):
    """C. 跳过流程: PENDING → PROCESSING → SKIPPED (去重/质量判定)"""

    @patch('pipeline.LLMScraper')
    @patch('pipeline.FileCopier')
    def test_C1_dedup_skip_strategy(self, MockCopier, MockScraper):
        source_path = self._create_source_file("DupSkip.2024.mkv")

        self.config["duplicate_handling"]["strategy"] = "skip"

        copier_instance = MagicMock()
        copier_instance.copy_to_temp.return_value = [
            os.path.join(self.temp_dir, "DupSkip.2024.mkv"),
        ]
        MockCopier.return_value = copier_instance

        scraper_instance = MagicMock()
        scraper_instance.scrape.return_value = self._mock_scrape_result(
            title_cn="重复电影"
        )
        MockScraper.return_value = scraper_instance

        pipeline = self._make_pipeline()
        pipeline.copier = copier_instance
        pipeline.scraper = scraper_instance

        task = self.tm.create_task(
            video_path=source_path,
            video_file="DupSkip.2024.mkv",
            file_size_mb=100.0,
        )

        with patch.object(pipeline, '_step_dedup') as mock_dedup:
            mock_dedup.side_effect = PipelineSkipError("同名文件已存在: existing.mkv")
            result = pipeline.process_one(task)

        self.assertTrue(result)

        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "SKIPPED")
        self.assertIn("同名文件已存在", updated["skip_reason"])

        self.config["duplicate_handling"]["strategy"] = "quality"

    @patch('pipeline.LLMScraper')
    @patch('pipeline.FileCopier')
    def test_C2_skipped_moved_to_quarantine(self, MockCopier, MockScraper):
        source_path = self._create_source_file("SkipQuarantine.2024.mkv")

        copier_instance = MagicMock()
        copier_instance.copy_to_temp.return_value = [
            os.path.join(self.temp_dir, "SkipQuarantine.2024.mkv"),
        ]
        MockCopier.return_value = copier_instance

        scraper_instance = MagicMock()
        scraper_instance.scrape.return_value = self._mock_scrape_result()
        MockScraper.return_value = scraper_instance

        pipeline = self._make_pipeline()
        pipeline.copier = copier_instance
        pipeline.scraper = scraper_instance

        task = self.tm.create_task(
            video_path=source_path,
            video_file="SkipQuarantine.2024.mkv",
            file_size_mb=100.0,
        )

        with patch.object(pipeline, '_step_dedup') as mock_dedup:
            mock_dedup.side_effect = PipelineSkipError("质量优先: 保留已存在文件")
            pipeline.process_one(task)

        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "SKIPPED")
        self.assertEqual(updated["file_location"], "quarantine")

    @patch('pipeline.LLMScraper')
    @patch('pipeline.FileCopier')
    def test_C3_quality_keep_existing(self, MockCopier, MockScraper):
        source_path = self._create_source_file("LowQuality.2024.480p.mkv")

        copier_instance = MagicMock()
        copier_instance.copy_to_temp.return_value = [
            os.path.join(self.temp_dir, "LowQuality.2024.480p.mkv"),
        ]
        MockCopier.return_value = copier_instance

        scraper_instance = MagicMock()
        scraper_instance.scrape.return_value = self._mock_scrape_result(
            title_cn="低质量电影"
        )
        MockScraper.return_value = scraper_instance

        pipeline = self._make_pipeline()
        pipeline.copier = copier_instance
        pipeline.scraper = scraper_instance

        task = self.tm.create_task(
            video_path=source_path,
            video_file="LowQuality.2024.480p.mkv",
            file_size_mb=100.0,
        )

        with patch.object(pipeline, '_step_dedup') as mock_dedup:
            mock_dedup.side_effect = PipelineSkipError("质量优先: 保留已存在文件")
            pipeline.process_one(task)

        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "SKIPPED")
        self.assertIn("质量优先", updated["skip_reason"])

    @patch('pipeline.LLMScraper')
    @patch('pipeline.FileCopier')
    def test_C4_skipped_no_quarantine_dir(self, MockCopier, MockScraper):
        source_path = self._create_source_file("SkipNoQ.2024.mkv")

        self.config["source_policy"]["quarantine_dir"] = ""

        copier_instance = MagicMock()
        copier_instance.copy_to_temp.return_value = [
            os.path.join(self.temp_dir, "SkipNoQ.2024.mkv"),
        ]
        MockCopier.return_value = copier_instance

        scraper_instance = MagicMock()
        scraper_instance.scrape.return_value = self._mock_scrape_result()
        MockScraper.return_value = scraper_instance

        pipeline = self._make_pipeline()
        pipeline.copier = copier_instance
        pipeline.scraper = scraper_instance

        task = self.tm.create_task(
            video_path=source_path,
            video_file="SkipNoQ.2024.mkv",
            file_size_mb=100.0,
        )

        with patch.object(pipeline, '_step_dedup') as mock_dedup:
            mock_dedup.side_effect = PipelineSkipError("跳过")
            pipeline.process_one(task)

        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "SKIPPED")
        self.assertEqual(updated["file_location"], "source")

        self.config["source_policy"]["quarantine_dir"] = self.quarantine_dir


# ============================================================
# D. 重试流程: FAILED/SKIPPED → PENDING
# ============================================================
class TestDRetryFlow(BaseTestCase):
    """D. 重试流程: FAILED/SKIPPED → PENDING"""

    def test_D1_retry_failed(self):
        task = self._create_task(status="FAILED", error_message="刮削失败")
        result = self.tm.retry_task(task["task_id"])
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "PENDING")
        self.assertEqual(result["retry_count"], 1)
        self.assertEqual(result["error_message"], "")

    def test_D2_retry_skipped(self):
        task = self._create_task(status="SKIPPED", skip_reason="同名文件已存在")
        result = self.tm.retry_task(task["task_id"])
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "PENDING")
        self.assertEqual(result["retry_count"], 1)

    def test_D3_cannot_retry_success(self):
        task = self._create_task(status="SUCCESS")
        result = self.tm.retry_task(task["task_id"])
        self.assertIsNone(result)

    def test_D4_cannot_retry_pending(self):
        task = self._create_task(status="PENDING")
        result = self.tm.retry_task(task["task_id"])
        self.assertIsNone(result)

    def test_D5_cannot_retry_confirming(self):
        task = self._create_task(status="CONFIRMING")
        result = self.tm.retry_task(task["task_id"])
        self.assertIsNone(result)

    def test_D6_cannot_retry_processing(self):
        task = self._create_task(status="PROCESSING")
        result = self.tm.retry_task(task["task_id"])
        self.assertIsNone(result)

    def test_D7_retry_nonexistent_task(self):
        result = self.tm.retry_task("nonexistent_id")
        self.assertIsNone(result)

    def test_D8_retry_from_quarantine_sets_location_to_source(self):
        task = self._create_task(status="FAILED", file_location="quarantine",
                                 source_path=os.path.join(self.quarantine_dir, "q.mkv"))
        result = self.tm.retry_task(task["task_id"])
        self.assertEqual(result["file_location"], "source")

    def test_D9_retry_preserves_source_location(self):
        task = self._create_task(status="FAILED", file_location="source")
        result = self.tm.retry_task(task["task_id"])
        self.assertEqual(result["file_location"], "source")

    def test_D10_retry_all_failed(self):
        for i in range(3):
            self._create_task(
                status="FAILED",
                source_path=f"{self.source_dir}/fail_{i}.mkv",
                source_filename=f"fail_{i}.mkv",
            )
        self._create_task(
            status="SUCCESS",
            source_path=f"{self.source_dir}/ok.mkv",
            source_filename="ok.mkv",
        )
        retried = self.tm.retry_all_failed()
        self.assertEqual(len(retried), 3)
        for t in retried:
            updated = db_module.get_task(self.conn, t["task_id"])
            self.assertEqual(updated["status"], "PENDING")

    def test_D11_retry_all_includes_skipped(self):
        self._create_task(
            status="FAILED",
            source_path=f"{self.source_dir}/fail.mkv",
            source_filename="fail.mkv",
        )
        self._create_task(
            status="SKIPPED",
            source_path=f"{self.source_dir}/skip.mkv",
            source_filename="skip.mkv",
        )
        retried = self.tm.retry_all_failed()
        self.assertEqual(len(retried), 2)


# ============================================================
# E. 忽略流程: FAILED/CONFIRMING → SKIPPED
# ============================================================
class TestEIgnoreFlow(BaseTestCase):
    """E. 忽略流程: FAILED/CONFIRMING → SKIPPED"""

    def test_E1_ignore_failed(self):
        source_path = self._create_source_file("IgnoreFail.2024.mkv")
        task = self._create_task(
            status="FAILED",
            source_path=source_path,
            file_location="source",
        )
        db_module.update_task(self.conn, task["task_id"],
                              status="SKIPPED", skip_reason="用户忽略",
                              file_location="quarantine")
        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "SKIPPED")
        self.assertEqual(updated["skip_reason"], "用户忽略")

    def test_E2_ignore_confirming(self):
        source_path = self._create_source_file("IgnoreConfirm.2024.mkv")
        task = self._create_task(
            status="CONFIRMING",
            source_path=source_path,
            file_location="temp",
        )
        db_module.update_task(self.conn, task["task_id"],
                              status="SKIPPED", skip_reason="用户忽略",
                              file_location="quarantine")
        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "SKIPPED")

    def test_E3_cannot_ignore_success(self):
        task = self._create_task(status="SUCCESS")
        current = task.get("status", "")
        self.assertNotIn(current, ("FAILED", "CONFIRMING"))

    def test_E4_cannot_ignore_pending(self):
        task = self._create_task(status="PENDING")
        current = task.get("status", "")
        self.assertNotIn(current, ("FAILED", "CONFIRMING"))

    def test_E5_cannot_ignore_skipped(self):
        task = self._create_task(status="SKIPPED")
        current = task.get("status", "")
        self.assertNotIn(current, ("FAILED", "CONFIRMING"))

    def test_E6_ignore_failed_with_quarantine(self):
        source_path = self._create_source_file("IgnoreQ.2024.mkv")
        task = self._create_task(
            status="FAILED",
            source_path=source_path,
            file_location="source",
        )
        self.tm.move_to_quarantine(
            task_id=task["task_id"],
            source_path=source_path,
            subtitle_paths=[],
            quarantine_dir=self.quarantine_dir,
        )
        db_module.update_task(self.conn, task["task_id"],
                              status="SKIPPED", skip_reason="用户忽略")
        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "SKIPPED")
        self.assertEqual(updated["file_location"], "quarantine")
        self.assertTrue(os.path.exists(
            os.path.join(self.quarantine_dir, "IgnoreQ.2024.mkv")))


# ============================================================
# F. 人工确认流程: CONFIRMING → SUCCESS
# ============================================================
class TestFConfirmFlow(BaseTestCase):
    """F. 人工确认流程: CONFIRMING → SUCCESS"""

    @patch('pipeline.LLMScraper')
    @patch('pipeline.FileCopier')
    def test_F1_manual_review_creates_confirming(self, MockCopier, MockScraper):
        source_path = self._create_source_file("ConfirmMovie.2024.mkv")

        copier_instance = MagicMock()
        copier_instance.copy_to_temp.return_value = [
            os.path.join(self.temp_dir, "ConfirmMovie.2024.mkv"),
        ]
        MockCopier.return_value = copier_instance

        scraper_instance = MagicMock()
        scraper_instance.scrape.return_value = self._mock_scrape_result(
            title_cn="确认电影"
        )
        MockScraper.return_value = scraper_instance

        pipeline = self._make_pipeline(manual_review=True)
        pipeline.copier = copier_instance
        pipeline.scraper = scraper_instance

        task = self.tm.create_task(
            video_path=source_path,
            video_file="ConfirmMovie.2024.mkv",
            file_size_mb=100.0,
        )

        result = pipeline.process_one(task)
        self.assertTrue(result)

        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "CONFIRMING")
        self.assertEqual(updated["confirm_status"], "PENDING")
        self.assertEqual(updated["file_location"], "temp")

    @patch('pipeline.LLMScraper')
    @patch('pipeline.FileCopier')
    def test_F2_confirm_to_success(self, MockCopier, MockScraper):
        source_path = self._create_source_file("ConfirmOk.2024.mkv")
        temp_video = os.path.join(self.temp_dir, "ConfirmOk.2024.mkv")
        with open(temp_video, 'w') as f:
            f.write("temp video")

        copier_instance = MagicMock()
        MockCopier.return_value = copier_instance

        scraper_instance = MagicMock()
        MockScraper.return_value = scraper_instance

        pipeline = self._make_pipeline(manual_review=False)
        pipeline.copier = copier_instance
        pipeline.scraper = scraper_instance

        task = self._create_task(
            status="CONFIRMING",
            source_path=source_path,
            file_location="temp",
            video_path=temp_video,
            confirm_status="PENDING",
            scrape_result=self._mock_scrape_result(title_cn="确认成功"),
            scrape_dimensions={"media_type": "movie", "documentary": "false"},
            import_path=os.path.join(self.import_dir, "movies"),
            classify_result=os.path.join(self.import_dir, "movies"),
        )

        with patch.object(pipeline, '_step_import_from_confirm'):
            result = pipeline.confirm_task(task["task_id"])

        self.assertTrue(result)

        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "SUCCESS")
        self.assertEqual(updated["import_success"], 1)
        self.assertEqual(updated["file_location"], "import")

    @patch('pipeline.LLMScraper')
    @patch('pipeline.FileCopier')
    def test_F3_confirm_non_confirming_fails(self, MockCopier, MockScraper):
        task = self._create_task(status="PENDING")

        pipeline = self._make_pipeline()
        pipeline.copier = MagicMock()
        pipeline.scraper = MagicMock()

        with self.assertRaises(PipelineError):
            pipeline.confirm_task(task["task_id"])

    @patch('pipeline.LLMScraper')
    @patch('pipeline.FileCopier')
    def test_F4_confirm_all(self, MockCopier, MockScraper):
        confirming_ids = []
        for i in range(3):
            source_path = self._create_source_file(f"BatchConfirm_{i}.2024.mkv")
            task = self._create_task(
                status="CONFIRMING",
                source_path=source_path,
                file_location="temp",
                confirm_status="PENDING",
                scrape_result=self._mock_scrape_result(),
                scrape_dimensions={"media_type": "movie", "documentary": "false"},
                import_path=os.path.join(self.import_dir, "movies"),
                classify_result=os.path.join(self.import_dir, "movies"),
            )
            confirming_ids.append(task["task_id"])

        pipeline = self._make_pipeline()
        pipeline.copier = MagicMock()
        pipeline.scraper = MagicMock()

        with patch.object(pipeline, '_step_import_from_confirm'):
            for tid in confirming_ids:
                pipeline.confirm_task(tid)

        for tid in confirming_ids:
            updated = db_module.get_task(self.conn, tid)
            self.assertEqual(updated["status"], "SUCCESS")


# ============================================================
# G. 修改分类流程: CONFIRMING → reclassify → SUCCESS
# ============================================================
class TestGReclassifyFlow(BaseTestCase):
    """G. 修改分类流程: CONFIRMING → reclassify → SUCCESS"""

    @patch('pipeline.LLMScraper')
    @patch('pipeline.FileCopier')
    def test_G1_reclassify_to_success(self, MockCopier, MockScraper):
        source_path = self._create_source_file("Reclassify.2024.mkv")
        temp_video = os.path.join(self.temp_dir, "Reclassify.2024.mkv")
        with open(temp_video, 'w') as f:
            f.write("temp video")

        copier_instance = MagicMock()
        MockCopier.return_value = copier_instance

        scraper_instance = MagicMock()
        MockScraper.return_value = scraper_instance

        pipeline = self._make_pipeline()
        pipeline.copier = copier_instance
        pipeline.scraper = scraper_instance

        task = self._create_task(
            status="CONFIRMING",
            source_path=source_path,
            file_location="temp",
            confirm_status="PENDING",
            video_path=temp_video,
            scrape_result=self._mock_scrape_result(
                title_cn="重分类电影",
                dimensions={"media_type": "movie", "documentary": "false"},
            ),
            scrape_dimensions={"media_type": "movie", "documentary": "false"},
            import_path=os.path.join(self.import_dir, "movies"),
            classify_result=os.path.join(self.import_dir, "movies"),
        )

        with patch.object(pipeline, '_step_import'):
            with patch.object(pipeline, '_step_dedup'):
                result = pipeline.reclassify_task(
                    task["task_id"],
                    {"media_type": "tv", "documentary": "false"}
                )

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["import_success"], 1)

    @patch('pipeline.LLMScraper')
    @patch('pipeline.FileCopier')
    def test_G2_reclassify_no_matching_rule(self, MockCopier, MockScraper):
        source_path = self._create_source_file("NoRuleReclassify.2024.mkv")

        pipeline = self._make_pipeline()
        pipeline.copier = MagicMock()
        pipeline.scraper = MagicMock()

        task = self._create_task(
            status="CONFIRMING",
            source_path=source_path,
            file_location="temp",
            scrape_result=self._mock_scrape_result(
                dimensions={"media_type": "unknown"},
            ),
            scrape_dimensions={"media_type": "unknown"},
        )

        with self.assertRaises(PipelineError) as ctx:
            pipeline.reclassify_task(
                task["task_id"],
                {"media_type": "unknown"}
            )
        self.assertIn("重新分类失败", str(ctx.exception))

    @patch('pipeline.LLMScraper')
    @patch('pipeline.FileCopier')
    def test_G3_reclassify_skipped_by_dedup(self, MockCopier, MockScraper):
        source_path = self._create_source_file("ReclassifySkip.2024.mkv")

        pipeline = self._make_pipeline()
        pipeline.copier = MagicMock()
        pipeline.scraper = MagicMock()

        task = self._create_task(
            status="CONFIRMING",
            source_path=source_path,
            file_location="temp",
            scrape_result=self._mock_scrape_result(),
            scrape_dimensions={"media_type": "movie", "documentary": "false"},
        )

        with patch.object(pipeline, '_step_dedup') as mock_dedup:
            mock_dedup.side_effect = PipelineSkipError("同名文件已存在")
            result = pipeline.reclassify_task(
                task["task_id"],
                {"media_type": "movie", "documentary": "false"}
            )

        self.assertEqual(result["status"], "SKIPPED")


# ============================================================
# H. 删除任务
# ============================================================
class TestHDeleteTask(BaseTestCase):
    """H. 删除任务: 仅删DB记录，不删文件"""

    def test_H1_delete_pending_task(self):
        task = self._create_task(status="PENDING")
        result = db_module.delete_task(self.conn, task["task_id"])
        self.assertTrue(result)
        self.assertIsNone(db_module.get_task(self.conn, task["task_id"]))

    def test_H2_delete_success_task(self):
        task = self._create_task(status="SUCCESS")
        db_module.delete_task(self.conn, task["task_id"])
        self.assertIsNone(db_module.get_task(self.conn, task["task_id"]))

    def test_H3_delete_failed_task(self):
        task = self._create_task(status="FAILED")
        db_module.delete_task(self.conn, task["task_id"])
        self.assertIsNone(db_module.get_task(self.conn, task["task_id"]))

    def test_H4_delete_confirming_task(self):
        task = self._create_task(status="CONFIRMING")
        db_module.delete_task(self.conn, task["task_id"])
        self.assertIsNone(db_module.get_task(self.conn, task["task_id"]))

    def test_H5_delete_skipped_task(self):
        task = self._create_task(status="SKIPPED")
        db_module.delete_task(self.conn, task["task_id"])
        self.assertIsNone(db_module.get_task(self.conn, task["task_id"]))

    def test_H6_delete_task_preserves_file(self):
        source_path = self._create_source_file("PreservedFile.2024.mkv")
        task = self._create_task(
            status="SUCCESS",
            source_path=source_path,
        )
        db_module.delete_task(self.conn, task["task_id"])
        self.assertTrue(os.path.exists(source_path))

    def test_H7_delete_task_removes_subtitles(self):
        task = self._create_task(status="PENDING")
        db_module.create_subtitles(self.conn, task["task_id"], [
            "/test/movie.zh.srt",
            "/test/movie.en.srt",
        ])
        subs = db_module.get_subtitles_by_task(self.conn, task["task_id"])
        self.assertEqual(len(subs), 2)

        db_module.delete_task(self.conn, task["task_id"])
        subs_after = db_module.get_subtitles_by_task(self.conn, task["task_id"])
        self.assertEqual(len(subs_after), 0)

    def test_H8_clear_tasks_by_status(self):
        for i in range(3):
            self._create_task(
                status="SUCCESS",
                source_path=f"{self.source_dir}/ok_{i}.mkv",
                source_filename=f"ok_{i}.mkv",
            )
        self._create_task(
            status="FAILED",
            source_path=f"{self.source_dir}/fail.mkv",
            source_filename="fail.mkv",
        )
        db_module.clear_tasks(self.conn, status="SUCCESS")
        remaining = db_module.count_all_tasks(self.conn)
        self.assertEqual(remaining, 1)

    def test_H9_clear_all_tasks(self):
        for i in range(5):
            self._create_task(
                status="PENDING",
                source_path=f"{self.source_dir}/all_{i}.mkv",
                source_filename=f"all_{i}.mkv",
            )
        db_module.clear_tasks(self.conn)
        remaining = db_module.count_all_tasks(self.conn)
        self.assertEqual(remaining, 0)


# ============================================================
# I. 状态验证 & DB 迁移
# ============================================================
class TestIStatusValidation(BaseTestCase):
    """I. 状态验证: VALID_STATUSES / 旧状态迁移 / 旧API已移除"""

    def test_I1_valid_statuses_count(self):
        self.assertEqual(len(VALID_STATUSES), 6)

    def test_I2_valid_statuses_values(self):
        expected = ["PENDING", "PROCESSING", "SUCCESS", "FAILED", "SKIPPED", "CONFIRMING"]
        self.assertEqual(VALID_STATUSES, expected)

    def test_I3_no_old_statuses_in_valid(self):
        old_statuses = ["NEEDS_REVIEW", "ROLLBACK", "DUPLICATE_REVIEW"]
        for s in old_statuses:
            self.assertNotIn(s, VALID_STATUSES)

    def test_I4_migration_needs_review_to_failed(self):
        task = db_module.create_task(self.conn,
                                     source_path="/test/migrate_nr.mkv",
                                     source_filename="migrate_nr.mkv",
                                     file_size_mb=100.0)
        self.conn.execute("UPDATE tasks SET status='NEEDS_REVIEW' WHERE task_id=?",
                          (task["task_id"],))
        self.conn.commit()

        db_module._migrate_schema(self.conn)

        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "FAILED")

    def test_I5_migration_rollback_to_failed(self):
        task = db_module.create_task(self.conn,
                                     source_path="/test/migrate_rb.mkv",
                                     source_filename="migrate_rb.mkv",
                                     file_size_mb=100.0)
        self.conn.execute("UPDATE tasks SET status='ROLLBACK' WHERE task_id=?",
                          (task["task_id"],))
        self.conn.commit()

        db_module._migrate_schema(self.conn)

        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "FAILED")

    def test_I6_migration_duplicate_review_to_skipped(self):
        task = db_module.create_task(self.conn,
                                     source_path="/test/migrate_dr.mkv",
                                     source_filename="migrate_dr.mkv",
                                     file_size_mb=100.0)
        self.conn.execute("UPDATE tasks SET status='DUPLICATE_REVIEW' WHERE task_id=?",
                          (task["task_id"],))
        self.conn.commit()

        db_module._migrate_schema(self.conn)

        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "SKIPPED")

    def test_I7_migration_failed_source_to_quarantine(self):
        task = db_module.create_task(self.conn,
                                     source_path="/test/migrate_fl.mkv",
                                     source_filename="migrate_fl.mkv",
                                     file_size_mb=100.0)
        self.conn.execute(
            "UPDATE tasks SET status='FAILED', file_location='source', import_success=0 WHERE task_id=?",
            (task["task_id"],))
        self.conn.commit()

        db_module._migrate_schema(self.conn)

        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["file_location"], "quarantine")

    def test_I8_migration_skipped_source_to_quarantine(self):
        task = db_module.create_task(self.conn,
                                     source_path="/test/migrate_sk.mkv",
                                     source_filename="migrate_sk.mkv",
                                     file_size_mb=100.0)
        self.conn.execute(
            "UPDATE tasks SET status='SKIPPED', file_location='source' WHERE task_id=?",
            (task["task_id"],))
        self.conn.commit()

        db_module._migrate_schema(self.conn)

        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["file_location"], "quarantine")

    def test_I9_count_by_status_excludes_old(self):
        counts = db_module.count_by_status(self.conn)
        for old_status in ["NEEDS_REVIEW", "ROLLBACK", "DUPLICATE_REVIEW"]:
            self.assertNotIn(old_status, counts)

    def test_I10_list_tasks_rejects_old_status(self):
        rows, total, _ = db_module.list_tasks(self.conn, page=1, page_size=20,
                                               status="NEEDS_REVIEW")
        self.assertEqual(total, 0)

    def test_I11_rollback_api_removed(self):
        self.assertFalse(hasattr(PipelineRunner, 'rollback_task'))

    def test_I12_duplicate_review_api_removed(self):
        self.assertFalse(hasattr(PipelineRunner, 'process_duplicate_review'))


# ============================================================
# J. 改名 API
# ============================================================
class TestJRenameFlow(BaseTestCase):
    """J. 改名 API: 修改文件名并更新DB"""

    def test_J1_rename_import_file(self):
        import_dir = os.path.join(self.import_dir, "movies")
        os.makedirs(import_dir, exist_ok=True)
        old_path = os.path.join(import_dir, "OldName.2024.mkv")
        with open(old_path, 'w') as f:
            f.write("video content")

        task = self._create_task(
            status="SUCCESS",
            file_location="import",
            import_video_path=old_path,
            final_filename="OldName.2024.mkv",
        )

        new_filename = "NewName.2024.mkv"
        new_path = os.path.join(import_dir, new_filename)
        os.rename(old_path, new_path)

        db_module.update_task(self.conn, task["task_id"],
                              source_filename=new_filename,
                              import_video_path=new_path,
                              final_filename=new_filename)

        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["source_filename"], new_filename)
        self.assertEqual(updated["import_video_path"], new_path)
        self.assertTrue(os.path.exists(new_path))

    def test_J2_rename_quarantine_file(self):
        old_path = os.path.join(self.quarantine_dir, "OldQ.2024.mkv")
        with open(old_path, 'w') as f:
            f.write("quarantine content")

        task = self._create_task(
            status="FAILED",
            file_location="quarantine",
            source_path=old_path,
        )

        new_filename = "NewQ.2024.mkv"
        new_path = os.path.join(self.quarantine_dir, new_filename)
        os.rename(old_path, new_path)

        db_module.update_task(self.conn, task["task_id"],
                              source_filename=new_filename,
                              source_path=new_path)

        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["source_filename"], new_filename)
        self.assertTrue(os.path.exists(new_path))
        self.assertFalse(os.path.exists(old_path))


# ============================================================
# K. 队列控制
# ============================================================
class TestKQueueControl(BaseTestCase):
    """K. 队列控制: 暂停/恢复"""

    def test_K1_pipeline_pause_resume(self):
        pipeline = self._make_pipeline()
        self.assertFalse(pipeline.is_paused())

        pipeline.pause()
        self.assertTrue(pipeline.is_paused())

        pipeline.resume()
        self.assertFalse(pipeline.is_paused())

    def test_K2_has_active_tasks(self):
        self._create_task(status="PENDING")
        self.assertTrue(self.tm.has_active_tasks())

    def test_K3_no_active_tasks(self):
        self._create_task(status="SUCCESS")
        self._create_task(status="FAILED")
        self.assertFalse(self.tm.has_active_tasks())

    def test_K4_get_next_pending(self):
        task = self._create_task(status="PENDING")
        next_task = self.tm.get_next_pending()
        self.assertIsNotNone(next_task)
        self.assertEqual(next_task["task_id"], task["task_id"])

    def test_K5_no_next_pending_when_all_done(self):
        self._create_task(status="SUCCESS")
        next_task = self.tm.get_next_pending()
        self.assertIsNone(next_task)


# ============================================================
# L. 完整状态流转路径
# ============================================================
class TestLFullStateTransitions(BaseTestCase):
    """L. 完整状态流转路径验证"""

    def test_L1_pending_to_processing(self):
        task = self._create_task(status="PENDING")
        db_module.update_task(self.conn, task["task_id"], status="PROCESSING")
        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "PROCESSING")

    def test_L2_processing_to_success(self):
        task = self._create_task(status="PROCESSING")
        db_module.update_task(self.conn, task["task_id"],
                              status="SUCCESS", import_success=1,
                              file_location="import")
        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "SUCCESS")
        self.assertEqual(updated["import_success"], 1)

    def test_L3_processing_to_failed(self):
        task = self._create_task(status="PROCESSING")
        db_module.update_task(self.conn, task["task_id"],
                              status="FAILED", error_message="测试失败",
                              file_location="quarantine")
        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "FAILED")

    def test_L4_processing_to_skipped(self):
        task = self._create_task(status="PROCESSING")
        db_module.update_task(self.conn, task["task_id"],
                              status="SKIPPED", skip_reason="去重跳过",
                              file_location="quarantine")
        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "SKIPPED")

    def test_L5_processing_to_confirming(self):
        task = self._create_task(status="PROCESSING")
        db_module.update_task(self.conn, task["task_id"],
                              status="CONFIRMING", confirm_status="PENDING",
                              file_location="temp")
        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "CONFIRMING")

    def test_L6_confirming_to_success(self):
        task = self._create_task(status="CONFIRMING")
        db_module.update_task(self.conn, task["task_id"],
                              status="SUCCESS", import_success=1,
                              file_location="import", confirm_status="CONFIRMED")
        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "SUCCESS")

    def test_L7_confirming_to_skipped_via_ignore(self):
        task = self._create_task(status="CONFIRMING")
        db_module.update_task(self.conn, task["task_id"],
                              status="SKIPPED", skip_reason="用户忽略",
                              file_location="quarantine")
        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "SKIPPED")

    def test_L8_failed_to_pending_via_retry(self):
        task = self._create_task(status="FAILED")
        result = self.tm.retry_task(task["task_id"])
        self.assertEqual(result["status"], "PENDING")

    def test_L9_skipped_to_pending_via_retry(self):
        task = self._create_task(status="SKIPPED")
        result = self.tm.retry_task(task["task_id"])
        self.assertEqual(result["status"], "PENDING")

    def test_L10_failed_to_skipped_via_ignore(self):
        task = self._create_task(status="FAILED")
        db_module.update_task(self.conn, task["task_id"],
                              status="SKIPPED", skip_reason="用户忽略")
        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["status"], "SKIPPED")

    def test_L11_all_six_statuses_in_db(self):
        statuses_created = set()
        for s in VALID_STATUSES:
            task = self._create_task(
                status=s,
                source_path=f"{self.source_dir}/status_{s}.mkv",
                source_filename=f"status_{s}.mkv",
            )
            statuses_created.add(task["status"])
        self.assertEqual(statuses_created, set(VALID_STATUSES))

    def test_L12_count_by_status_all_keys(self):
        for s in VALID_STATUSES:
            self._create_task(
                status=s,
                source_path=f"{self.source_dir}/count_{s}.mkv",
                source_filename=f"count_{s}.mkv",
            )
        counts = db_module.count_by_status(self.conn)
        for s in VALID_STATUSES:
            self.assertIn(s, counts)
            self.assertGreaterEqual(counts[s], 1)


# ============================================================
# M. 隔离区相关
# ============================================================
class TestMQuarantine(BaseTestCase):
    """M. 隔离区相关: 文件移动/重试/路径更新"""

    def test_M1_move_to_quarantine(self):
        source_path = self._create_source_file("QuarantineMove.2024.mkv")
        task = self._create_task(
            status="FAILED",
            source_path=source_path,
        )
        self.tm.move_to_quarantine(
            task_id=task["task_id"],
            source_path=source_path,
            subtitle_paths=[],
            quarantine_dir=self.quarantine_dir,
        )
        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["file_location"], "quarantine")
        self.assertTrue(updated["source_path"].startswith(self.quarantine_dir))
        self.assertTrue(os.path.exists(
            os.path.join(self.quarantine_dir, "QuarantineMove.2024.mkv")))
        self.assertFalse(os.path.exists(source_path))

    def test_M2_move_to_quarantine_with_subtitles(self):
        source_path = self._create_source_file("WithSubs.2024.mkv")
        sub_path = os.path.join(self.source_dir, "WithSubs.2024.zh.srt")
        with open(sub_path, 'w') as f:
            f.write("subtitle content")

        task = self._create_task(
            status="FAILED",
            source_path=source_path,
        )

        self.tm.move_to_quarantine(
            task_id=task["task_id"],
            source_path=source_path,
            subtitle_paths=[sub_path],
            quarantine_dir=self.quarantine_dir,
        )

        self.assertTrue(os.path.exists(
            os.path.join(self.quarantine_dir, "WithSubs.2024.zh.srt")))
        self.assertFalse(os.path.exists(sub_path))

    def test_M3_retry_from_quarantine_resets_location_to_source(self):
        source_path = self._create_source_file("RetryQuarantine.2024.mkv")
        task = self._create_task(
            status="FAILED",
            source_path=source_path,
            file_location="quarantine",
        )
        result = self.tm.retry_task(task["task_id"])
        self.assertEqual(result["status"], "PENDING")
        self.assertEqual(result["file_location"], "source")

    def test_M4_quarantine_dir_auto_created(self):
        new_q_dir = os.path.join(self.tmpdir, "auto_quarantine")
        self.assertFalse(os.path.exists(new_q_dir))

        source_path = self._create_source_file("AutoQ.2024.mkv")
        task = self._create_task(status="FAILED", source_path=source_path)

        self.tm.move_to_quarantine(
            task_id=task["task_id"],
            source_path=source_path,
            subtitle_paths=[],
            quarantine_dir=new_q_dir,
        )

        self.assertTrue(os.path.isdir(new_q_dir))


# ============================================================
# N. file_location 枚举验证
# ============================================================
class TestNFileLocation(BaseTestCase):
    """N. file_location 枚举验证"""

    def test_N1_success_location_is_import(self):
        task = self._create_task(status="SUCCESS", file_location="import",
                                 import_success=1)
        self.assertEqual(task["file_location"], "import")

    def test_N2_failed_location_is_quarantine(self):
        task = self._create_task(status="FAILED", file_location="quarantine")
        self.assertEqual(task["file_location"], "quarantine")

    def test_N3_skipped_location_is_quarantine(self):
        task = self._create_task(status="SKIPPED", file_location="quarantine")
        self.assertEqual(task["file_location"], "quarantine")

    def test_N4_confirming_location_is_temp(self):
        task = self._create_task(status="CONFIRMING", file_location="temp")
        self.assertEqual(task["file_location"], "temp")

    def test_N5_pending_location_is_source(self):
        task = self._create_task(status="PENDING", file_location="source")
        self.assertEqual(task["file_location"], "source")

    def test_N6_processing_location_is_temp(self):
        task = self._create_task(status="PROCESSING", file_location="temp")
        self.assertEqual(task["file_location"], "temp")


# ============================================================
# O. 配置验证
# ============================================================
class TestOConfigValidation(BaseTestCase):
    """O. 配置验证: max_auto_retries 已移除 / duplicate_handling.enabled 已移除"""

    def test_O1_no_max_auto_retries_in_default_config(self):
        sp = self.config.get("source_policy", {})
        self.assertNotIn("max_auto_retries", sp)

    def test_O2_no_duplicate_handling_enabled(self):
        dh = self.config.get("duplicate_handling", {})
        self.assertNotIn("enabled", dh)

    def test_O3_duplicate_handling_strategy_exists(self):
        dh = self.config.get("duplicate_handling", {})
        self.assertIn("strategy", dh)

    def test_O4_quarantine_dir_in_source_policy(self):
        sp = self.config.get("source_policy", {})
        self.assertIn("quarantine_dir", sp)


# ============================================================
# P. 边界场景
# ============================================================
class TestPEdgeCases(BaseTestCase):
    """P. 边界场景"""

    def test_P1_create_duplicate_source_path(self):
        sp = f"{self.source_dir}/dup_path.mkv"
        task1 = db_module.create_task(self.conn, source_path=sp,
                                      source_filename="dup_path.mkv",
                                      file_size_mb=100.0)
        task2 = db_module.create_task(self.conn, source_path=sp,
                                      source_filename="dup_path.mkv",
                                      file_size_mb=200.0)
        self.assertNotEqual(task1["task_id"], task2["task_id"])

    def test_P2_empty_error_message_on_retry(self):
        task = self._create_task(status="FAILED", error_message="some error")
        result = self.tm.retry_task(task["task_id"])
        self.assertEqual(result["error_message"], "")

    def test_P3_retry_increments_count(self):
        task = self._create_task(status="FAILED", retry_count=0)
        result1 = self.tm.retry_task(task["task_id"])
        self.assertEqual(result1["retry_count"], 1)

        db_module.update_task(self.conn, task["task_id"], status="FAILED")
        result2 = self.tm.retry_task(task["task_id"])
        self.assertEqual(result2["retry_count"], 2)

    def test_P4_task_created_with_timestamp(self):
        task = self._create_task(status="PENDING")
        self.assertIsNotNone(task["created_at"])
        self.assertIsNotNone(task["last_seen_at"])

    def test_P5_scrape_result_json_roundtrip(self):
        task = self._create_task(status="SUCCESS")
        scrape = self._mock_scrape_result(title_cn="JSON测试")
        db_module.update_task(self.conn, task["task_id"],
                              scrape_result=scrape,
                              scrape_dimensions=scrape.get("dimensions", {}))
        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["scrape_result"]["title_cn"], "JSON测试")

    def test_P6_list_tasks_exclude_completed(self):
        self._create_task(status="PENDING")
        self._create_task(status="SUCCESS")
        self._create_task(status="FAILED")

        active = self.tm.list_tasks(exclude_completed=True, limit=100)
        for t in active:
            self.assertIn(t["status"], ("PENDING", "PROCESSING", "FAILED", "CONFIRMING"))

    def test_P7_check_source_duplicate_new_file(self):
        result = self.tm.check_source_duplicate(f"{self.source_dir}/brand_new.mkv")
        self.assertFalse(result["exists"])
        self.assertEqual(result["action"], "CREATE")

    def test_P8_check_source_duplicate_processing_file(self):
        self._create_task(
            status="PROCESSING",
            source_path=f"{self.source_dir}/processing.mkv",
            source_filename="processing.mkv",
        )
        result = self.tm.check_source_duplicate(f"{self.source_dir}/processing.mkv")
        self.assertTrue(result["exists"])
        self.assertEqual(result["action"], "SKIP")

    def test_P9_check_source_duplicate_confirming_file(self):
        self._create_task(
            status="CONFIRMING",
            source_path=f"{self.source_dir}/confirming.mkv",
            source_filename="confirming.mkv",
        )
        result = self.tm.check_source_duplicate(f"{self.source_dir}/confirming.mkv")
        self.assertTrue(result["exists"])
        self.assertEqual(result["action"], "SKIP")

    def test_P10_subtitle_operations(self):
        task = self._create_task(status="PENDING")
        subs = db_module.create_subtitles(self.conn, task["task_id"], [
            "/test/movie.zh.srt",
            "/test/movie.en.srt",
        ])
        self.assertEqual(len(subs), 2)

        all_subs = db_module.get_subtitles_by_task(self.conn, task["task_id"])
        self.assertEqual(len(all_subs), 2)

        db_module.update_subtitle(self.conn, all_subs[0]["id"],
                                  status="SUCCESS", lang="zh")
        updated_sub = db_module.get_subtitles_by_task(self.conn, task["task_id"])
        success_count = sum(1 for s in updated_sub if s["status"] == "SUCCESS")
        self.assertEqual(success_count, 1)


# ============================================================
# Q. 隔离区同名文件冲突
# ============================================================
class TestQQuarantineConflict(BaseTestCase):
    """Q. 隔离区同名文件冲突: 多次处理同名文件失败/跳过时的行为"""

    def test_Q1_resolve_dest_path_no_conflict(self):
        dest = TaskManager._resolve_dest_path(self.quarantine_dir, "Movie.2024.mkv")
        self.assertEqual(dest, os.path.join(self.quarantine_dir, "Movie.2024.mkv"))

    def test_Q2_resolve_dest_path_one_conflict(self):
        existing = os.path.join(self.quarantine_dir, "Movie.2024.mkv")
        with open(existing, 'w') as f:
            f.write("first")
        dest = TaskManager._resolve_dest_path(self.quarantine_dir, "Movie.2024.mkv")
        self.assertEqual(dest, os.path.join(self.quarantine_dir, "Movie.2024_1.mkv"))

    def test_Q3_resolve_dest_path_multiple_conflicts(self):
        for suffix in ["", "_1", "_2"]:
            path = os.path.join(self.quarantine_dir, f"Movie.2024{suffix}.mkv")
            with open(path, 'w') as f:
                f.write(f"file{suffix}")
        dest = TaskManager._resolve_dest_path(self.quarantine_dir, "Movie.2024.mkv")
        self.assertEqual(dest, os.path.join(self.quarantine_dir, "Movie.2024_3.mkv"))

    def test_Q4_resolve_dest_path_different_ext_no_conflict(self):
        q_dir = os.path.join(self.tmpdir, "q4_unique")
        os.makedirs(q_dir, exist_ok=True)
        existing = os.path.join(q_dir, "Movie.2024.srt")
        with open(existing, 'w') as f:
            f.write("subtitle")
        dest = TaskManager._resolve_dest_path(q_dir, "Movie.2024.mkv")
        self.assertEqual(dest, os.path.join(q_dir, "Movie.2024.mkv"))

    def test_Q5_move_same_filename_twice_to_quarantine(self):
        source1 = self._create_source_file("SameName.2024.mkv", content="first attempt")
        task1 = self._create_task(status="FAILED", source_path=source1)
        self.tm.move_to_quarantine(
            task_id=task1["task_id"],
            source_path=source1,
            subtitle_paths=[],
            quarantine_dir=self.quarantine_dir,
        )
        updated1 = db_module.get_task(self.conn, task1["task_id"])
        self.assertEqual(updated1["file_location"], "quarantine")
        self.assertTrue(os.path.exists(
            os.path.join(self.quarantine_dir, "SameName.2024.mkv")))
        self.assertFalse(os.path.exists(source1))

        source2 = self._create_source_file("SameName.2024.mkv", content="second attempt")
        task2 = self._create_task(
            status="FAILED",
            source_path=source2,
            source_filename="SameName.2024.mkv",
        )
        self.tm.move_to_quarantine(
            task_id=task2["task_id"],
            source_path=source2,
            subtitle_paths=[],
            quarantine_dir=self.quarantine_dir,
        )
        updated2 = db_module.get_task(self.conn, task2["task_id"])
        self.assertEqual(updated2["file_location"], "quarantine")
        self.assertTrue(os.path.exists(
            os.path.join(self.quarantine_dir, "SameName.2024.mkv")))
        self.assertTrue(os.path.exists(
            os.path.join(self.quarantine_dir, "SameName.2024_1.mkv")))
        self.assertFalse(os.path.exists(source2))

        with open(os.path.join(self.quarantine_dir, "SameName.2024.mkv")) as f:
            self.assertEqual(f.read(), "first attempt")
        with open(os.path.join(self.quarantine_dir, "SameName.2024_1.mkv")) as f:
            self.assertEqual(f.read(), "second attempt")

    def test_Q6_move_same_filename_three_times(self):
        for i in range(3):
            source = self._create_source_file(
                "Triple.2024.mkv", content=f"attempt {i+1}")
            task = self._create_task(
                status="FAILED",
                source_path=source,
                source_filename="Triple.2024.mkv",
            )
            self.tm.move_to_quarantine(
                task_id=task["task_id"],
                source_path=source,
                subtitle_paths=[],
                quarantine_dir=self.quarantine_dir,
            )

        self.assertTrue(os.path.exists(
            os.path.join(self.quarantine_dir, "Triple.2024.mkv")))
        self.assertTrue(os.path.exists(
            os.path.join(self.quarantine_dir, "Triple.2024_1.mkv")))
        self.assertTrue(os.path.exists(
            os.path.join(self.quarantine_dir, "Triple.2024_2.mkv")))

    def test_Q7_move_from_quarantine_to_quarantine_noop(self):
        source = self._create_source_file("AlreadyQ.2024.mkv", content="in quarantine")
        task = self._create_task(status="FAILED", source_path=source)
        self.tm.move_to_quarantine(
            task_id=task["task_id"],
            source_path=source,
            subtitle_paths=[],
            quarantine_dir=self.quarantine_dir,
        )
        q_path = os.path.join(self.quarantine_dir, "AlreadyQ.2024.mkv")
        self.assertTrue(os.path.exists(q_path))

        updated1 = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated1["source_path"], q_path)

        self.tm.move_to_quarantine(
            task_id=task["task_id"],
            source_path=q_path,
            subtitle_paths=[],
            quarantine_dir=self.quarantine_dir,
        )

        updated2 = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated2["source_path"], q_path)
        self.assertTrue(os.path.exists(q_path))

    def test_Q8_move_subtitles_with_conflict(self):
        source = self._create_source_file("SubConflict.2024.mkv", content="video")
        sub1 = os.path.join(self.source_dir, "SubConflict.2024.zh.srt")
        with open(sub1, 'w') as f:
            f.write("first subtitle")

        task1 = self._create_task(status="FAILED", source_path=source)
        self.tm.move_to_quarantine(
            task_id=task1["task_id"],
            source_path=source,
            subtitle_paths=[sub1],
            quarantine_dir=self.quarantine_dir,
        )
        self.assertTrue(os.path.exists(
            os.path.join(self.quarantine_dir, "SubConflict.2024.zh.srt")))

        source2 = self._create_source_file("SubConflict.2024.mkv", content="video2")
        sub2 = os.path.join(self.source_dir, "SubConflict.2024.zh.srt")
        with open(sub2, 'w') as f:
            f.write("second subtitle")

        task2 = self._create_task(
            status="FAILED",
            source_path=source2,
            source_filename="SubConflict.2024.mkv",
        )
        self.tm.move_to_quarantine(
            task_id=task2["task_id"],
            source_path=source2,
            subtitle_paths=[sub2],
            quarantine_dir=self.quarantine_dir,
        )
        self.assertTrue(os.path.exists(
            os.path.join(self.quarantine_dir, "SubConflict.2024.zh.srt")))
        self.assertTrue(os.path.exists(
            os.path.join(self.quarantine_dir, "SubConflict.2024.zh_1.srt")))

    def test_Q9_db_paths_updated_after_conflict(self):
        source1 = self._create_source_file("DBPath.2024.mkv", content="first")
        task1 = self._create_task(status="FAILED", source_path=source1)
        self.tm.move_to_quarantine(
            task_id=task1["task_id"],
            source_path=source1,
            subtitle_paths=[],
            quarantine_dir=self.quarantine_dir,
        )
        t1 = db_module.get_task(self.conn, task1["task_id"])
        self.assertEqual(t1["source_path"],
                         os.path.join(self.quarantine_dir, "DBPath.2024.mkv"))
        self.assertEqual(t1["source_filename"], "DBPath.2024.mkv")

        source2 = self._create_source_file("DBPath.2024.mkv", content="second")
        task2 = self._create_task(
            status="FAILED",
            source_path=source2,
            source_filename="DBPath.2024.mkv",
        )
        self.tm.move_to_quarantine(
            task_id=task2["task_id"],
            source_path=source2,
            subtitle_paths=[],
            quarantine_dir=self.quarantine_dir,
        )
        t2 = db_module.get_task(self.conn, task2["task_id"])
        self.assertEqual(t2["source_path"],
                         os.path.join(self.quarantine_dir, "DBPath.2024_1.mkv"))
        self.assertEqual(t2["source_filename"], "DBPath.2024_1.mkv")

    def test_Q10_source_filename_synced_on_no_conflict(self):
        source = self._create_source_file("SyncTest.2024.mkv")
        task = self._create_task(status="FAILED", source_path=source)
        self.tm.move_to_quarantine(
            task_id=task["task_id"],
            source_path=source,
            subtitle_paths=[],
            quarantine_dir=self.quarantine_dir,
        )
        updated = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated["source_filename"], "SyncTest.2024.mkv")

    def test_Q11_source_filename_synced_on_multiple_conflicts(self):
        for i in range(3):
            source = self._create_source_file(
                "MultiSync.2024.mkv", content=f"attempt {i+1}")
            task = self._create_task(
                status="FAILED",
                source_path=source,
                source_filename="MultiSync.2024.mkv",
            )
            self.tm.move_to_quarantine(
                task_id=task["task_id"],
                source_path=source,
                subtitle_paths=[],
                quarantine_dir=self.quarantine_dir,
            )

        expected = ["MultiSync.2024.mkv", "MultiSync.2024_1.mkv", "MultiSync.2024_2.mkv"]
        tasks = db_module.list_tasks(self.conn, page=1, page_size=20)[0]
        for t in tasks:
            if "MultiSync" in t.get("source_filename", ""):
                self.assertIn(t["source_filename"], expected)


class TestRDeleteTaskWithFiles(BaseTestCase):
    """端到端测试删除逻辑：用实际文件验证各种 file_location 场景"""

    def _simulate_delete_task(self, task, delete_files=False):
        result = {"deleted": task["task_id"], "file_location": task.get("file_location", "source")}
        deleted_files = []
        missing_files = []
        file_location = task.get("file_location", "source")

        temp_files_to_cleanup = []
        if file_location == "temp":
            vp = task.get("video_path", "")
            if vp:
                if os.path.exists(vp):
                    temp_files_to_cleanup.append(vp)
                else:
                    missing_files.append(os.path.basename(vp))
            for sub in (task.get("subtitle_files") or []):
                sub_str = str(sub) if sub else ""
                if sub_str:
                    if os.path.exists(sub_str):
                        temp_files_to_cleanup.append(sub_str)
                    else:
                        missing_files.append(os.path.basename(sub_str))

        temp_dir = self.config.get('temp_dir', '')
        for f in temp_files_to_cleanup:
            try:
                f_abs = os.path.abspath(f)
                if temp_dir and f_abs.startswith(os.path.abspath(temp_dir) + os.sep):
                    if os.path.exists(f):
                        os.remove(f)
                        deleted_files.append(os.path.basename(f))
                    else:
                        missing_files.append(os.path.basename(f))
            except OSError:
                pass

        if delete_files:
            files_to_delete = []
            files_to_check = []

            if file_location == "import":
                ivp = task.get("import_video_path", "")
                if ivp:
                    files_to_check.append(ivp)
                for sub in (task.get("subtitle_files") or []):
                    sub_str = str(sub) if sub else ""
                    if sub_str:
                        files_to_check.append(sub_str)
            elif file_location in ("quarantine", "source"):
                sp = task.get("source_path", "")
                if sp:
                    files_to_check.append(sp)
                for sub in (task.get("subtitle_files") or []):
                    sub_str = str(sub) if sub else ""
                    if sub_str:
                        files_to_check.append(sub_str)

            for f in files_to_check:
                if os.path.exists(f):
                    files_to_delete.append(f)
                else:
                    missing_files.append(os.path.basename(f))

            source_policy = self.config.get("source_policy", {})
            import_dirs = []
            for rule in self.config.get("path_rules", []):
                tpl = rule.get("template", "")
                if tpl:
                    import_dirs.append(tpl)

            allowed_dirs = [
                self.config.get("source_dir", ""),
                self.config.get("temp_dir", ""),
                source_policy.get("quarantine_dir", ""),
            ] + import_dirs

            for f in files_to_delete:
                try:
                    f_abs = os.path.abspath(f)
                    allowed = any(
                        d and f_abs.startswith(os.path.abspath(d) + os.sep)
                        for d in allowed_dirs
                    )
                    if allowed and os.path.exists(f):
                        os.remove(f)
                        deleted_files.append(os.path.basename(f))
                except OSError:
                    pass

        db_module.delete_task(self.conn, task["task_id"])

        location_labels = {
            "source": "源文件", "quarantine": "隔离区文件",
            "import": "入库文件", "temp": "中转文件",
        }
        loc_label = location_labels.get(file_location, "文件")
        msg_parts = ["任务已删除"]
        if deleted_files:
            result["deleted_files"] = deleted_files
            msg_parts.append(f"已删除 {len(deleted_files)} 个{loc_label}")
        if missing_files and delete_files:
            result["missing_files"] = missing_files
            msg_parts.append(f"{len(missing_files)} 个文件已不存在")

        return result, "，".join(msg_parts)

    def test_R1_delete_source_task_with_files(self):
        source_path = self._create_source_file("DeleteSource.2024.mkv")
        self.assertTrue(os.path.exists(source_path))
        task = self._create_task(
            status="PENDING", source_path=source_path,
            source_filename="DeleteSource.2024.mkv", file_location="source",
        )
        result, msg = self._simulate_delete_task(task, delete_files=True)
        self.assertFalse(os.path.exists(source_path))
        self.assertIn("DeleteSource.2024.mkv", result.get("deleted_files", []))
        self.assertIsNone(db_module.get_task(self.conn, task["task_id"]))
        self.assertIn("已删除", msg)

    def test_R2_delete_source_task_without_files(self):
        source_path = self._create_source_file("KeepSource.2024.mkv")
        task = self._create_task(
            status="PENDING", source_path=source_path,
            source_filename="KeepSource.2024.mkv", file_location="source",
        )
        result, msg = self._simulate_delete_task(task, delete_files=False)
        self.assertTrue(os.path.exists(source_path))
        self.assertNotIn("deleted_files", result)
        self.assertIsNone(db_module.get_task(self.conn, task["task_id"]))

    def test_R3_delete_temp_task_cleans_temp(self):
        temp_video = os.path.join(self.temp_dir, "TempVid.2024.mkv")
        with open(temp_video, 'w') as f:
            f.write("temp video content")
        task = self._create_task(
            status="CONFIRMING",
            source_path=os.path.join(self.source_dir, "TempVid.2024.mkv"),
            source_filename="TempVid.2024.mkv",
            file_location="temp",
            video_path=temp_video,
        )
        self.assertTrue(os.path.exists(temp_video))
        result, msg = self._simulate_delete_task(task, delete_files=False)
        self.assertFalse(os.path.exists(temp_video))
        self.assertIn("TempVid.2024.mkv", result.get("deleted_files", []))
        self.assertIsNone(db_module.get_task(self.conn, task["task_id"]))

    def test_R4_delete_temp_task_with_subtitles(self):
        temp_video = os.path.join(self.temp_dir, "SubVid.2024.mkv")
        temp_sub = os.path.join(self.temp_dir, "SubVid.2024.zh.srt")
        with open(temp_video, 'w') as f:
            f.write("video")
        with open(temp_sub, 'w') as f:
            f.write("subtitle")
        task = self._create_task(
            status="CONFIRMING",
            source_path=os.path.join(self.source_dir, "SubVid.2024.mkv"),
            source_filename="SubVid.2024.mkv",
            file_location="temp",
            video_path=temp_video,
        )
        sub_task = db_module.create_subtitles(self.conn, task["task_id"], [temp_sub])
        task = db_module.get_task(self.conn, task["task_id"])

        self.assertTrue(os.path.exists(temp_video))
        self.assertTrue(os.path.exists(temp_sub))

        result, msg = self._simulate_delete_task(task, delete_files=False)
        self.assertFalse(os.path.exists(temp_video))
        self.assertFalse(os.path.exists(temp_sub))
        self.assertIn("SubVid.2024.mkv", result.get("deleted_files", []))
        self.assertIn("SubVid.2024.zh.srt", result.get("deleted_files", []))

    def test_R5_delete_import_task_with_files(self):
        import_dir = os.path.join(self.import_dir, "movies")
        os.makedirs(import_dir, exist_ok=True)
        import_video = os.path.join(import_dir, "Imported.2024.mkv")
        with open(import_video, 'w') as f:
            f.write("imported video")
        task = self._create_task(
            status="SUCCESS",
            source_path=os.path.join(self.source_dir, "Imported.2024.mkv"),
            source_filename="Imported.2024.mkv",
            file_location="import",
            import_video_path=import_video,
        )
        self.assertTrue(os.path.exists(import_video))
        result, msg = self._simulate_delete_task(task, delete_files=True)
        self.assertFalse(os.path.exists(import_video))
        self.assertIn("Imported.2024.mkv", result.get("deleted_files", []))
        self.assertIn("入库文件", msg)

    def test_R6_delete_quarantine_task_with_files(self):
        q_video = os.path.join(self.quarantine_dir, "Quarantined.2024.mkv")
        with open(q_video, 'w') as f:
            f.write("quarantined video")
        task = self._create_task(
            status="FAILED",
            source_path=q_video,
            source_filename="Quarantined.2024.mkv",
            file_location="quarantine",
        )
        self.assertTrue(os.path.exists(q_video))
        result, msg = self._simulate_delete_task(task, delete_files=True)
        self.assertFalse(os.path.exists(q_video))
        self.assertIn("Quarantined.2024.mkv", result.get("deleted_files", []))
        self.assertIn("隔离区文件", msg)

    def test_R7_delete_task_file_already_missing(self):
        source_path = self._create_source_file("Missing.2024.mkv")
        task = self._create_task(
            status="PENDING", source_path=source_path,
            source_filename="Missing.2024.mkv", file_location="source",
        )
        os.remove(source_path)
        self.assertFalse(os.path.exists(source_path))

        result, msg = self._simulate_delete_task(task, delete_files=True)
        self.assertIn("Missing.2024.mkv", result.get("missing_files", []))
        self.assertNotIn("deleted_files", result)
        self.assertIn("已不存在", msg)
        self.assertIsNone(db_module.get_task(self.conn, task["task_id"]))

    def test_R8_delete_temp_task_video_missing(self):
        temp_video = os.path.join(self.temp_dir, "MissingTemp.2024.mkv")
        with open(temp_video, 'w') as f:
            f.write("temp")
        task = self._create_task(
            status="CONFIRMING",
            source_path=os.path.join(self.source_dir, "MissingTemp.2024.mkv"),
            source_filename="MissingTemp.2024.mkv",
            file_location="temp",
            video_path=temp_video,
        )
        os.remove(temp_video)
        self.assertFalse(os.path.exists(temp_video))

        result, msg = self._simulate_delete_task(task, delete_files=False)
        self.assertNotIn("deleted_files", result)
        self.assertNotIn("missing_files", result)
        self.assertIsNone(db_module.get_task(self.conn, task["task_id"]))

    def test_R9_delete_import_task_with_subtitles_and_missing_sub(self):
        import_dir = os.path.join(self.import_dir, "movies")
        os.makedirs(import_dir, exist_ok=True)
        import_video = os.path.join(import_dir, "SubImport.2024.mkv")
        import_sub = os.path.join(import_dir, "SubImport.2024.zh.srt")
        with open(import_video, 'w') as f:
            f.write("video")
        with open(import_sub, 'w') as f:
            f.write("subtitle")

        task = self._create_task(
            status="SUCCESS",
            source_path=os.path.join(self.source_dir, "SubImport.2024.mkv"),
            source_filename="SubImport.2024.mkv",
            file_location="import",
            import_video_path=import_video,
        )
        db_module.create_subtitles(self.conn, task["task_id"], [import_sub])
        os.remove(import_sub)

        task = db_module.get_task(self.conn, task["task_id"])
        result, msg = self._simulate_delete_task(task, delete_files=True)
        self.assertFalse(os.path.exists(import_video))
        self.assertIn("SubImport.2024.mkv", result.get("deleted_files", []))
        self.assertIn("SubImport.2024.zh.srt", result.get("missing_files", []))
        self.assertIn("已不存在", msg)

    def test_R10_delete_multiple_tasks_sequentially(self):
        paths = []
        tasks = []
        for i in range(3):
            sp = self._create_source_file(f"Batch{i}.2024.mkv", content=f"video {i}")
            paths.append(sp)
            tasks.append(self._create_task(
                status="PENDING", source_path=sp,
                source_filename=f"Batch{i}.2024.mkv", file_location="source",
            ))

        for i, task in enumerate(tasks):
            result, msg = self._simulate_delete_task(task, delete_files=True)
            self.assertFalse(os.path.exists(paths[i]))
            self.assertIsNone(db_module.get_task(self.conn, task["task_id"]))

        all_tasks = db_module.list_tasks(self.conn, page=1, page_size=50)[0]
        self.assertEqual(len(all_tasks), 0)

    def test_R11_delete_source_task_with_subtitle_files(self):
        source_video = self._create_source_file("SubSource.2024.mkv")
        source_sub = os.path.join(self.source_dir, "SubSource.2024.zh.srt")
        with open(source_sub, 'w') as f:
            f.write("subtitle content")

        task = self._create_task(
            status="PENDING", source_path=source_video,
            source_filename="SubSource.2024.mkv", file_location="source",
        )
        db_module.create_subtitles(self.conn, task["task_id"], [source_sub])
        task = db_module.get_task(self.conn, task["task_id"])

        self.assertTrue(os.path.exists(source_video))
        self.assertTrue(os.path.exists(source_sub))

        result, msg = self._simulate_delete_task(task, delete_files=True)
        self.assertFalse(os.path.exists(source_video))
        self.assertFalse(os.path.exists(source_sub))
        self.assertIn("SubSource.2024.mkv", result.get("deleted_files", []))
        self.assertIn("SubSource.2024.zh.srt", result.get("deleted_files", []))

    def test_R12_delete_import_task_subtitle_missing_video_exists(self):
        import_dir = os.path.join(self.import_dir, "movies")
        os.makedirs(import_dir, exist_ok=True)
        import_video = os.path.join(import_dir, "Mixed.2024.mkv")
        import_sub = os.path.join(import_dir, "Mixed.2024.zh.srt")
        with open(import_video, 'w') as f:
            f.write("video")
        with open(import_sub, 'w') as f:
            f.write("subtitle")

        task = self._create_task(
            status="SUCCESS",
            source_path=os.path.join(self.source_dir, "Mixed.2024.mkv"),
            source_filename="Mixed.2024.mkv",
            file_location="import",
            import_video_path=import_video,
        )
        db_module.create_subtitles(self.conn, task["task_id"], [import_sub])
        os.remove(import_video)

        task = db_module.get_task(self.conn, task["task_id"])
        result, msg = self._simulate_delete_task(task, delete_files=True)
        self.assertIn("Mixed.2024.mkv", result.get("missing_files", []))
        self.assertIn("Mixed.2024.zh.srt", result.get("deleted_files", []))

    def test_R13_delete_task_db_subtitles_also_deleted(self):
        source_path = self._create_source_file("SubDB.2024.mkv")
        source_sub = os.path.join(self.source_dir, "SubDB.2024.zh.srt")
        with open(source_sub, 'w') as f:
            f.write("subtitle")

        task = self._create_task(
            status="PENDING", source_path=source_path,
            source_filename="SubDB.2024.mkv", file_location="source",
        )
        db_module.create_subtitles(self.conn, task["task_id"], [source_sub])
        subs_before = db_module.get_subtitles_by_task(self.conn, task["task_id"])
        self.assertEqual(len(subs_before), 1)

        self._simulate_delete_task(db_module.get_task(self.conn, task["task_id"]),
                                   delete_files=True)
        subs_after = db_module.get_subtitles_by_task(self.conn, task["task_id"])
        self.assertEqual(len(subs_after), 0)


class TestSSubtitleIntegration(BaseTestCase):
    """字幕全场景集成测试：字幕结合视频在各种流程中的处理"""

    def test_S1_move_to_quarantine_updates_subtitle_db_paths(self):
        source_video = self._create_source_file("QuarantineSub.2024.mkv")
        source_sub = os.path.join(self.source_dir, "QuarantineSub.2024.zh.srt")
        with open(source_sub, 'w') as f:
            f.write("subtitle content")

        task = self._create_task(
            status="FAILED",
            source_path=source_video,
            source_filename="QuarantineSub.2024.mkv",
            file_location="source",
        )
        db_module.create_subtitles(self.conn, task["task_id"], [source_sub])
        task = db_module.get_task(self.conn, task["task_id"])

        self.assertTrue(os.path.exists(source_video))
        self.assertTrue(os.path.exists(source_sub))

        self.tm.move_to_quarantine(
            task_id=task["task_id"],
            source_path=source_video,
            subtitle_paths=[source_sub],
            quarantine_dir=self.quarantine_dir,
        )

        updated_task = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(updated_task["file_location"], "quarantine")
        self.assertTrue(updated_task["source_path"].startswith(self.quarantine_dir))

        subs = db_module.get_subtitles_by_task(self.conn, task["task_id"])
        self.assertEqual(len(subs), 1)
        self.assertTrue(subs[0]["target_path"].startswith(self.quarantine_dir))
        self.assertFalse(os.path.exists(source_sub))

    def test_S2_retry_from_quarantine_subtitle_paths_are_correct(self):
        source_video = self._create_source_file("RetrySub.2024.mkv")
        source_sub = os.path.join(self.source_dir, "RetrySub.2024.zh.srt")
        with open(source_sub, 'w') as f:
            f.write("subtitle content")

        task = self._create_task(
            status="FAILED",
            source_path=source_video,
            source_filename="RetrySub.2024.mkv",
            file_location="source",
        )
        db_module.create_subtitles(self.conn, task["task_id"], [source_sub])
        task = db_module.get_task(self.conn, task["task_id"])

        self.tm.move_to_quarantine(
            task_id=task["task_id"],
            source_path=source_video,
            subtitle_paths=[source_sub],
            quarantine_dir=self.quarantine_dir,
        )

        quarantined_task = db_module.get_task(self.conn, task["task_id"])
        sub_files_before = quarantined_task["subtitle_files"]
        self.assertTrue(len(sub_files_before) > 0)
        self.assertTrue(sub_files_before[0].startswith(self.quarantine_dir))

        self.tm.retry_task(task["task_id"])

        retried_task = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(retried_task["status"], "PENDING")
        self.assertEqual(retried_task["file_location"], "source")
        self.assertTrue(retried_task["source_path"].startswith(self.quarantine_dir))

        sub_files_after = retried_task["subtitle_files"]
        self.assertTrue(len(sub_files_after) > 0)
        self.assertTrue(sub_files_after[0].startswith(self.quarantine_dir),
                        f"字幕路径应在隔离区，实际: {sub_files_after[0]}")

    def test_S3_ignore_from_temp_with_quarantine_subtitles_moved(self):
        temp_video = os.path.join(self.temp_dir, "IgnoreTemp.2024.mkv")
        temp_sub = os.path.join(self.temp_dir, "IgnoreTemp.2024.zh.srt")
        with open(temp_video, 'w') as f:
            f.write("temp video")
        with open(temp_sub, 'w') as f:
            f.write("temp subtitle")

        task = self._create_task(
            status="CONFIRMING",
            source_path=os.path.join(self.source_dir, "IgnoreTemp.2024.mkv"),
            source_filename="IgnoreTemp.2024.mkv",
            file_location="temp",
            video_path=temp_video,
        )
        db_module.create_subtitles(self.conn, task["task_id"], [temp_sub])
        task = db_module.get_task(self.conn, task["task_id"])

        self.assertTrue(os.path.exists(temp_video))
        self.assertTrue(os.path.exists(temp_sub))

        shutil.move(temp_video,
            os.path.join(self.quarantine_dir, os.path.basename(temp_video)))
        dest_video = os.path.join(self.quarantine_dir, os.path.basename(temp_video))
        shutil.move(temp_sub,
            os.path.join(self.quarantine_dir, os.path.basename(temp_sub)))
        dest_sub = os.path.join(self.quarantine_dir, os.path.basename(temp_sub))

        subs = db_module.get_subtitles_by_task(self.conn, task["task_id"])
        for sub in subs:
            sub_basename = os.path.basename(sub.get("source_path", "") or sub.get("target_path", ""))
            if sub_basename == os.path.basename(temp_sub):
                db_module.update_subtitle(self.conn, sub["id"], target_path=dest_sub)

        db_module.update_task(self.conn, task["task_id"],
            status="SKIPPED", skip_reason="用户忽略",
            source_path=dest_video,
            source_filename=os.path.basename(dest_video),
            file_location="quarantine", video_path="")

        ignored_task = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(ignored_task["status"], "SKIPPED")
        self.assertEqual(ignored_task["file_location"], "quarantine")
        self.assertFalse(os.path.exists(temp_video))
        self.assertFalse(os.path.exists(temp_sub))

        subs = db_module.get_subtitles_by_task(self.conn, task["task_id"])
        self.assertEqual(len(subs), 1)
        self.assertTrue(subs[0]["target_path"].startswith(self.quarantine_dir),
                        f"字幕路径应在隔离区，实际: {subs[0]['target_path']}")

    def test_S4_ignore_from_temp_without_quarantine_files_deleted(self):
        temp_video = os.path.join(self.temp_dir, "IgnoreNoQ.2024.mkv")
        temp_sub = os.path.join(self.temp_dir, "IgnoreNoQ.2024.zh.srt")
        with open(temp_video, 'w') as f:
            f.write("temp video")
        with open(temp_sub, 'w') as f:
            f.write("temp subtitle")

        task = self._create_task(
            status="CONFIRMING",
            source_path=os.path.join(self.source_dir, "IgnoreNoQ.2024.mkv"),
            source_filename="IgnoreNoQ.2024.mkv",
            file_location="temp",
            video_path=temp_video,
        )
        db_module.create_subtitles(self.conn, task["task_id"], [temp_sub])
        task = db_module.get_task(self.conn, task["task_id"])

        self.assertTrue(os.path.exists(temp_video))
        self.assertTrue(os.path.exists(temp_sub))

        if os.path.exists(temp_video):
            os.remove(temp_video)
        for sub in task.get("subtitle_files", []):
            if sub and os.path.exists(sub):
                os.remove(sub)

        db_module.update_subtitles_by_task(self.conn, task["task_id"],
                                          status="FAILED", target_path="")
        db_module.update_task(self.conn, task["task_id"],
            status="SKIPPED", skip_reason="用户忽略",
            file_location="source")

        ignored_task = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(ignored_task["status"], "SKIPPED")
        self.assertEqual(ignored_task["file_location"], "source")
        self.assertFalse(os.path.exists(temp_video))
        self.assertFalse(os.path.exists(temp_sub))

        subs = db_module.get_subtitles_by_task(self.conn, task["task_id"])
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0]["status"], "FAILED")
        self.assertEqual(subs[0]["target_path"], "")

    def test_S5_failure_cleanup_cleans_temp_subtitles(self):
        temp_video = os.path.join(self.temp_dir, "FailCleanup.2024.mkv")
        temp_sub = os.path.join(self.temp_dir, "FailCleanup.2024.zh.srt")
        with open(temp_video, 'w') as f:
            f.write("temp video")
        with open(temp_sub, 'w') as f:
            f.write("temp subtitle")

        task_dict = {
            "task_id": "fail_cleanup_test",
            "source_filename": "FailCleanup.2024.mkv",
            "subtitle_files": [temp_sub],
            "file_location": "temp",
        }

        pipeline = self._make_pipeline()
        pipeline._cleanup_temp_on_failure(task_dict, temp_video)

        self.assertFalse(os.path.exists(temp_video))
        self.assertFalse(os.path.exists(temp_sub))

    def test_S6_confirm_task_subtitle_paths_point_to_temp(self):
        temp_video = os.path.join(self.temp_dir, "ConfirmSub.2024.mkv")
        temp_sub = os.path.join(self.temp_dir, "ConfirmSub.2024.zh.srt")
        with open(temp_video, 'w') as f:
            f.write("temp video")
        with open(temp_sub, 'w') as f:
            f.write("temp subtitle")

        task = self._create_task(
            status="CONFIRMING",
            source_path=os.path.join(self.source_dir, "ConfirmSub.2024.mkv"),
            source_filename="ConfirmSub.2024.mkv",
            file_location="temp",
            video_path=temp_video,
            scrape_result={
                "title_cn": "确认测试",
                "title_en": "ConfirmTest",
                "year": "2024",
                "type": "movie",
                "confidence": 0.5,
                "dimensions": {"media_type": "movie", "documentary": "false"},
            },
        )
        db_module.create_subtitles(self.conn, task["task_id"], [temp_sub])

        task = db_module.get_task(self.conn, task["task_id"])
        sub_files = task["subtitle_files"]
        self.assertEqual(len(sub_files), 1)
        self.assertTrue(sub_files[0].startswith(self.temp_dir),
                        f"字幕路径应在 temp 目录，实际: {sub_files[0]}")

    def test_S7_retry_from_quarantine_no_subtitle_files_in_source(self):
        source_video = self._create_source_file("RetryNoSub.2024.mkv")
        source_sub = os.path.join(self.source_dir, "RetryNoSub.2024.zh.srt")
        with open(source_sub, 'w') as f:
            f.write("subtitle")

        task = self._create_task(
            status="FAILED",
            source_path=source_video,
            source_filename="RetryNoSub.2024.mkv",
            file_location="source",
        )
        db_module.create_subtitles(self.conn, task["task_id"], [source_sub])

        self.tm.move_to_quarantine(
            task_id=task["task_id"],
            source_path=source_video,
            subtitle_paths=[source_sub],
            quarantine_dir=self.quarantine_dir,
        )

        quarantined_task = db_module.get_task(self.conn, task["task_id"])
        original_sub_path = source_sub
        self.assertFalse(os.path.exists(original_sub_path))

        self.tm.retry_task(task["task_id"])
        retried_task = db_module.get_task(self.conn, task["task_id"])

        self.assertTrue(retried_task["source_path"].startswith(self.quarantine_dir))
        self.assertTrue(retried_task["subtitle_files"][0].startswith(self.quarantine_dir))
        self.assertFalse(os.path.exists(original_sub_path))

    def test_S8_ignore_from_source_quarantine_subtitle_paths_updated(self):
        source_video = self._create_source_file("IgnoreSource.2024.mkv")
        source_sub = os.path.join(self.source_dir, "IgnoreSource.2024.zh.srt")
        with open(source_sub, 'w') as f:
            f.write("subtitle")

        task = self._create_task(
            status="FAILED",
            source_path=source_video,
            source_filename="IgnoreSource.2024.mkv",
            file_location="source",
        )
        db_module.create_subtitles(self.conn, task["task_id"], [source_sub])

        self.tm.move_to_quarantine(
            task_id=task["task_id"],
            source_path=source_video,
            subtitle_paths=[source_sub],
            quarantine_dir=self.quarantine_dir,
        )
        db_module.update_task(self.conn, task["task_id"],
            status="SKIPPED", skip_reason="用户忽略",
            error_message=f"已移入隔离区: {self.quarantine_dir}")

        ignored_task = db_module.get_task(self.conn, task["task_id"])
        self.assertEqual(ignored_task["status"], "SKIPPED")

        subs = db_module.get_subtitles_by_task(self.conn, task["task_id"])
        self.assertEqual(len(subs), 1)
        self.assertTrue(subs[0]["target_path"].startswith(self.quarantine_dir),
                        f"字幕路径应在隔离区，实际: {subs[0]['target_path']}")
        self.assertFalse(os.path.exists(source_sub))

    def test_S9_update_subtitle_allows_target_path(self):
        source_video = self._create_source_file("UpdateSub.2024.mkv")
        source_sub = os.path.join(self.source_dir, "UpdateSub.2024.zh.srt")
        with open(source_sub, 'w') as f:
            f.write("subtitle")

        task = self._create_task(
            status="PENDING",
            source_path=source_video,
            source_filename="UpdateSub.2024.mkv",
        )
        db_module.create_subtitles(self.conn, task["task_id"], [source_sub])
        subs = db_module.get_subtitles_by_task(self.conn, task["task_id"])
        self.assertEqual(len(subs), 1)
        sub_id = subs[0]["id"]

        new_path = os.path.join(self.quarantine_dir, "UpdateSub.2024.zh.srt")
        db_module.update_subtitle(self.conn, sub_id, target_path=new_path)

        updated = db_module.get_subtitles_by_task(self.conn, task["task_id"])
        self.assertEqual(updated[0]["target_path"], new_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
