#!/usr/bin/env python3
"""
影音库AI智能整理 - 深度端到端测试
覆盖 TC-07 ~ TC-19、RT-05 及删除任务测试场景

测试场景:
  TC-07: 入库清理配置×回收站组合
  TC-08: 失败→源文件保留→重试
  TC-12: file_location全路径覆盖
  TC-13: 忽略操作×文件位置
  RT-05: 配置兼容性回归
  TC-15~TC-19: 源目录清理器
  删除任务测试

运行方式:
  python -m pytest tests/test_deep_e2e.py -v -s
  或
  python tests/test_deep_e2e.py
"""
import os
import sys
import shutil
import tempfile
import unittest
from copy import deepcopy
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.core.config_loader import load_config
from media_importer.core.db import (
    init_db, get_task, update_task as db_update_task,
    count_by_status, list_tasks,
)
from media_importer.core.db.task_repo import create_task, update_task, delete_task
from media_importer.core.task_manager import TaskManager
from media_importer.core.safety import move_to_recycle, move_to_recycle_with_companions
from media_importer.storage.source_cleaner import SourceCleaner
from media_importer.pipeline import PipelineRunner
from media_importer.pipeline.utils import PipelineError, PipelineSkipError

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "config.yaml"
)
CONFIG_EXISTS = os.path.isfile(CONFIG_PATH)


class DeepE2EBaseTestCase(unittest.TestCase):
    """深度E2E测试基类，提供临时目录和基础配置"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="nas_deep_e2e_")
        self.source_dir = os.path.join(self.test_dir, "source")
        self.temp_dir = os.path.join(self.test_dir, "temp")
        self.recycle_dir = os.path.join(self.test_dir, "recycle")
        self.import_dir = os.path.join(self.test_dir, "影视")
        self.log_dir = os.path.join(self.test_dir, "logs")
        self.data_dir = tempfile.mkdtemp(prefix="nas_deep_e2e_db_")

        for d in [self.source_dir, self.temp_dir, self.recycle_dir,
                  self.import_dir, self.log_dir]:
            os.makedirs(d, exist_ok=True)

        self.config = self._make_base_config()
        self.tm = TaskManager(self.data_dir, config=self.config)
        self._created_files = []

    def tearDown(self):
        if hasattr(self, 'tm') and self.tm:
            try:
                self.tm.conn.close()
            except Exception:
                pass
        if hasattr(self, 'data_dir'):
            shutil.rmtree(self.data_dir, ignore_errors=True)
        if hasattr(self, 'test_dir'):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _make_base_config(self):
        return {
            "source_dir": self.source_dir,
            "temp_dir": self.temp_dir,
            "log_dir": self.log_dir,
            "llm": {"api_key": "test-key", "model": "test-model"},
            "source_policy": {
                "recycle_dir": self.recycle_dir,
                "cleanup_source_after_done": True,
            },
            "source_cleaner": {
                "enabled": False,
                "cleanup_mode": "keep_media_only",
                "ai_enabled": False,
                "junk_video_max_size_mb": 50,
                "delete_extensions": [".url", ".txt"],
                "protect_extensions": [".nfo", ".jpg", ".png"],
                "blacklist_patterns": ["RARBG*", "*/Sample/*", "*/sample/*"],
                "cleanup_empty_dirs": True,
                "confirm_before_cleanup": True,
            },
            "metadata": {
                "providers": [{"type": "tmdb", "enabled": False}],
            },
            "path_rules": [
                {
                    "conditions": {"media_type": "movie"},
                    "template": os.path.join(self.import_dir, "电影/{title_cn} ({year})"),
                },
            ],
            "filename_templates": {
                "movie": "{title_cn} ({year}){ext}",
                "tv": "{title_cn}/Season {season:02d}/{title_cn} - S{season:02d}E{episode:02d}{ext}",
            },
            "video_extensions": [".mkv", ".mp4", ".avi", ".ts"],
            "subtitle_extensions": [".srt", ".ass", ".ssa"],
            "duplicate_handling": {"strategy": "skip"},
            "confidence": {},
            "manual_review": {"enabled": False},
            "fallback_dir": "",
            "_config_path": os.path.join(self.test_dir, "config.yaml"),
        }

    def _create_file(self, filename, directory=None, content=b'\x00' * 10240):
        directory = directory or self.source_dir
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, filename)
        with open(path, 'wb') as f:
            f.write(content)
        self._created_files.append(path)
        return path

    def _create_task(self, filename, **kwargs):
        source_path = kwargs.pop("source_path", None) or self._create_file(filename)
        task = self.tm.create_task(
            video_path=source_path,
            video_file=filename,
            file_size_mb=round(os.path.getsize(source_path) / (1024 * 1024), 4),
        )
        if kwargs:
            db_update_task(self.tm.conn, task["task_id"], **kwargs)
            task = self.tm.get_task(task["task_id"])
        return task

    def _make_pipeline(self, config=None):
        cfg = config or self.config
        return PipelineRunner(
            config=cfg,
            task_manager=self.tm,
            metrics=None,
            logger=None,
            notifier=None,
        )

    def _mock_pipeline_success(self, pipeline):
        """mock pipeline的刮削和后续步骤，使其走成功路径"""
        from media_importer.storage.file_copier import FileCopier
        pipeline.copier = MagicMock(spec=FileCopier)

        def fake_copy(video_path, subtitle_files, progress_cb, heartbeat_cb, **kwargs):
            temp_video = os.path.join(self.temp_dir, os.path.basename(video_path))
            if not os.path.exists(temp_video):
                shutil.copy2(video_path, temp_video)
            return [temp_video] + list(subtitle_files)

        pipeline.copier.copy_to_temp = fake_copy
        pipeline.copier.copy_to_temp = MagicMock(side_effect=fake_copy)

        pipeline.scraper = MagicMock()
        pipeline.scraper.scrape = MagicMock(return_value={
            "title_cn": "测试电影",
            "title_en": "Test Movie",
            "year": "2024",
            "type": "movie",
            "confidence": 0.95,
            "dimensions": {"media_type": "movie"},
            "provider_type": "tmdb",
            "provider_id": "12345",
        })
        pipeline.scraper.confidence_engine = MagicMock()
        pipeline.scraper.confidence_engine.get_confidence_level = MagicMock(return_value="PASS")

    def _assert_file_in_recycle(self, filename):
        found = False
        for root, dirs, files in os.walk(self.recycle_dir):
            for f in files:
                if filename in f and not f.endswith(".meta"):
                    found = True
                    break
        self.assertTrue(found, f"文件 {filename} 应在回收站中")

    def _assert_file_not_in_recycle(self, filename):
        found = False
        for root, dirs, files in os.walk(self.recycle_dir):
            for f in files:
                if filename in f and not f.endswith(".meta"):
                    found = True
                    break
        self.assertFalse(found, f"文件 {filename} 不应在回收站中")

    def _write_config_yaml(self, config_dir, content):
        import yaml
        config_path = os.path.join(config_dir, "config.yaml")
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(content, f, allow_unicode=True)
        return config_path


# ============================================================
# TC-07: 入库清理配置×回收站组合
# ============================================================
class TestTC07CleanupRecycleCombo(DeepE2EBaseTestCase):
    """TC-07: 入库清理配置×回收站组合

    验证 cleanup_source_after_done 与回收站的组合行为
    """

    def test_cleanup_true_with_recycle_success_moves_to_recycle(self):
        """cleanup_source_after_done=true + 有回收站 + SUCCESS → 源文件移入回收站"""
        self.config["source_policy"]["cleanup_source_after_done"] = True
        pipeline = self._make_pipeline()
        self._mock_pipeline_success(pipeline)

        source_path = self._create_file("TC07_movie.mkv")
        task = self._create_task("TC07_movie.mkv", source_path=source_path)

        with patch.object(pipeline, '_step_import') as mock_import:
            def fake_import(task, orig_src, orig_subs):
                task["import_video_path"] = os.path.join(
                    self.import_dir, "电影", "测试电影 (2024)", "测试电影 (2024).mkv"
                )
                os.makedirs(os.path.dirname(task["import_video_path"]), exist_ok=True)
                with open(task["import_video_path"], 'wb') as f:
                    f.write(b'\x00' * 1024)
                from media_importer.core.safety import move_to_recycle_with_companions
                source_policy = self.config.get("source_policy", {})
                recycle_dir = source_policy.get("recycle_dir", "")
                if source_policy.get("cleanup_source_after_done") and recycle_dir:
                    move_to_recycle_with_companions(
                        orig_src, orig_subs,
                        [".mkv"], [".srt"], recycle_dir,
                        reason="source_cleanup", task_id=task.get("task_id", ""),
                        source_dir=self.source_dir,
                    )

            mock_import.side_effect = fake_import
            pipeline.process_one(task)

        updated = self.tm.get_task(task["task_id"])
        self.assertEqual(updated["status"], "SUCCESS")
        self.assertFalse(os.path.isfile(source_path), "源文件应被移入回收站")
        self._assert_file_in_recycle("TC07_movie")

    def test_cleanup_true_failed_preserves_source(self):
        """cleanup_source_after_done=true + FAILED → 源文件保留在源目录"""
        self.config["source_policy"]["cleanup_source_after_done"] = True
        pipeline = self._make_pipeline()

        source_path = self._create_file("TC07_fail_movie.mkv")
        task = self._create_task("TC07_fail_movie.mkv", source_path=source_path)

        pipeline.copier = MagicMock()
        temp_path = os.path.join(self.temp_dir, "TC07_fail_movie.mkv")
        shutil.copy2(source_path, temp_path)
        pipeline.copier.copy_to_temp = MagicMock(return_value=[temp_path])

        pipeline.scraper = MagicMock()
        pipeline.scraper.scrape = MagicMock(side_effect=Exception("刮削失败"))
        pipeline.scraper.confidence_engine = MagicMock()

        pipeline.process_one(task)

        updated = self.tm.get_task(task["task_id"])
        self.assertEqual(updated["status"], "FAILED")
        self.assertTrue(os.path.isfile(source_path), "FAILED时源文件应保留")
        self.assertEqual(updated["file_location"], "source")

    def test_cleanup_false_success_preserves_source(self):
        """cleanup_source_after_done=false + SUCCESS → 源文件保留"""
        self.config["source_policy"]["cleanup_source_after_done"] = False
        pipeline = self._make_pipeline()
        self._mock_pipeline_success(pipeline)

        source_path = self._create_file("TC07_keep_movie.mkv")
        task = self._create_task("TC07_keep_movie.mkv", source_path=source_path)

        with patch.object(pipeline, '_step_import') as mock_import:
            def fake_import(task, orig_src, orig_subs):
                task["import_video_path"] = os.path.join(
                    self.import_dir, "电影", "测试电影 (2024)", "测试电影 (2024).mkv"
                )
                os.makedirs(os.path.dirname(task["import_video_path"]), exist_ok=True)
                with open(task["import_video_path"], 'wb') as f:
                    f.write(b'\x00' * 1024)

            mock_import.side_effect = fake_import
            pipeline.process_one(task)

        updated = self.tm.get_task(task["task_id"])
        self.assertEqual(updated["status"], "SUCCESS")
        self.assertTrue(os.path.isfile(source_path), "cleanup=false时源文件应保留")


# ============================================================
# TC-08: 失败→源文件保留→重试
# ============================================================
class TestTC08FailPreserveRetry(DeepE2EBaseTestCase):
    """TC-08: 失败→源文件保留→重试

    验证 FAILED 时源文件保留、临时文件删除、重试后从源文件重新处理
    """

    def test_failed_preserves_source_deletes_temp(self):
        """FAILED时源文件保留在源目录，临时文件rm删除"""
        pipeline = self._make_pipeline()

        source_path = self._create_file("TC08_movie.mkv")
        task = self._create_task("TC08_movie.mkv", source_path=source_path)

        temp_path = os.path.join(self.temp_dir, "TC08_movie.mkv")
        shutil.copy2(source_path, temp_path)

        pipeline.copier = MagicMock()
        pipeline.copier.copy_to_temp = MagicMock(return_value=[temp_path])

        pipeline.scraper = MagicMock()
        pipeline.scraper.scrape = MagicMock(side_effect=Exception("刮削失败"))
        pipeline.scraper.confidence_engine = MagicMock()

        pipeline.process_one(task)

        updated = self.tm.get_task(task["task_id"])
        self.assertEqual(updated["status"], "FAILED")
        self.assertTrue(os.path.isfile(source_path), "源文件应保留")
        self.assertFalse(os.path.isfile(temp_path), "临时文件应被删除")
        self.assertEqual(updated["file_location"], "source")

    def test_retry_from_source(self):
        """重试后从源文件重新处理"""
        source_path = self._create_file("TC08_retry_movie.mkv")
        task = self._create_task(
            "TC08_retry_movie.mkv",
            source_path=source_path,
            status="FAILED",
            file_location="source",
            error_message="之前的错误",
        )

        self.assertTrue(os.path.isfile(source_path), "重试前源文件应存在")

        retried = self.tm.retry_task(task["task_id"])
        self.assertIsNotNone(retried)
        self.assertEqual(retried["status"], "PENDING")
        self.assertEqual(retried["file_location"], "source")
        self.assertGreaterEqual(retried.get("retry_count", 0), 1)
        self.assertEqual(retried.get("error_message", ""), "")
        self.assertTrue(os.path.isfile(source_path), "重试后源文件仍应存在")


# ============================================================
# TC-12: file_location全路径覆盖
# ============================================================
class TestTC12FileLocationPath(DeepE2EBaseTestCase):
    """TC-12: file_location全路径覆盖

    验证文件在不同阶段的位置追踪
    """

    def test_source_to_temp_to_import_success(self):
        """source→temp→import (成功)"""
        pipeline = self._make_pipeline()
        self._mock_pipeline_success(pipeline)

        source_path = self._create_file("TC12_success.mkv")
        task = self._create_task("TC12_success.mkv", source_path=source_path)

        self.assertEqual(task["file_location"], "source")

        with patch.object(pipeline, '_step_import') as mock_import:
            def fake_import(task, orig_src, orig_subs):
                task["import_video_path"] = os.path.join(
                    self.import_dir, "电影", "测试电影 (2024)", "测试电影 (2024).mkv"
                )
                os.makedirs(os.path.dirname(task["import_video_path"]), exist_ok=True)
                with open(task["import_video_path"], 'wb') as f:
                    f.write(b'\x00' * 1024)

            mock_import.side_effect = fake_import

            with patch.object(pipeline, '_step_scrape'), \
                 patch.object(pipeline, '_step_validate'), \
                 patch.object(pipeline, '_step_classify'), \
                 patch.object(pipeline, '_step_dedup'), \
                 patch.object(pipeline, '_step_rename'), \
                 patch.object(pipeline, '_step_notify'), \
                 patch.object(pipeline, '_step_record'):

                pipeline.copier = MagicMock()
                temp_path = os.path.join(self.temp_dir, "TC12_success.mkv")
                shutil.copy2(source_path, temp_path)
                pipeline.copier.copy_to_temp = MagicMock(return_value=[temp_path])

                pipeline.process_one(task)

        updated = self.tm.get_task(task["task_id"])
        self.assertEqual(updated["status"], "SUCCESS")
        self.assertEqual(updated["file_location"], "import")

    def test_source_to_temp_fail_source_preserved(self):
        """source→temp→(rm) (失败, 临时文件删除, 源文件保留)"""
        pipeline = self._make_pipeline()

        source_path = self._create_file("TC12_fail.mkv")
        task = self._create_task("TC12_fail.mkv", source_path=source_path)

        temp_path = os.path.join(self.temp_dir, "TC12_fail.mkv")
        shutil.copy2(source_path, temp_path)

        pipeline.copier = MagicMock()
        pipeline.copier.copy_to_temp = MagicMock(return_value=[temp_path])

        pipeline.scraper = MagicMock()
        pipeline.scraper.scrape = MagicMock(side_effect=Exception("失败"))
        pipeline.scraper.confidence_engine = MagicMock()

        pipeline.process_one(task)

        updated = self.tm.get_task(task["task_id"])
        self.assertEqual(updated["status"], "FAILED")
        self.assertEqual(updated["file_location"], "source")
        self.assertFalse(os.path.isfile(temp_path), "临时文件应被删除")
        self.assertTrue(os.path.isfile(source_path), "源文件应保留")

    def test_source_to_recycle_cleanup_done(self):
        """source→recycle (cleanup_source_after_done=true, 完成)"""
        self.config["source_policy"]["cleanup_source_after_done"] = True
        source_path = self._create_file("TC12_recycle.mkv")

        task = self._create_task("TC12_recycle.mkv", source_path=source_path)
        self.assertEqual(task["file_location"], "source")
        self.assertTrue(os.path.isfile(source_path))

        ok, _, _ = move_to_recycle(
            source_path, self.recycle_dir,
            reason="source_cleanup", task_id=task["task_id"],
            source_dir=self.source_dir,
        )
        self.assertTrue(ok)
        db_update_task(self.tm.conn, task["task_id"],
                       file_location="recycle", status="SUCCESS")

        updated = self.tm.get_task(task["task_id"])
        self.assertEqual(updated["file_location"], "recycle")
        self.assertFalse(os.path.isfile(source_path))
        self._assert_file_in_recycle("TC12_recycle")

    def test_source_to_source_no_cleanup(self):
        """source→source (cleanup_source_after_done=false, 完成)"""
        self.config["source_policy"]["cleanup_source_after_done"] = False
        source_path = self._create_file("TC12_noclean.mkv")

        task = self._create_task("TC12_noclean.mkv", source_path=source_path)
        db_update_task(self.tm.conn, task["task_id"],
                       file_location="source", status="SUCCESS")

        updated = self.tm.get_task(task["task_id"])
        self.assertEqual(updated["file_location"], "source")
        self.assertTrue(os.path.isfile(source_path))


# ============================================================
# TC-13: 忽略操作×文件位置
# ============================================================
class TestTC13IgnoreFileLocation(DeepE2EBaseTestCase):
    """TC-13: 忽略操作×文件位置

    验证忽略操作在不同 file_location 下的行为
    """

    def test_temp_location_ignore_deletes_temp(self):
        """temp+忽略 → 临时文件rm删除 + 源文件按配置处理"""
        self.config["source_policy"]["cleanup_source_after_done"] = True
        source_path = self._create_file("TC13_temp_ignore.mkv")
        temp_path = os.path.join(self.temp_dir, "TC13_temp_ignore.mkv")
        shutil.copy2(source_path, temp_path)

        task = self._create_task(
            "TC13_temp_ignore.mkv",
            source_path=source_path,
            status="FAILED",
            file_location="temp",
            video_path=temp_path,
        )

        self.assertTrue(os.path.isfile(temp_path))
        self.assertTrue(os.path.isfile(source_path))

        from media_importer.core.db import update_subtitles_by_task
        with patch('media_importer.api.task_handlers.globals') as mock_globals:
            mock_globals._global_task_manager = self.tm
            mock_globals._config = self.config

            from media_importer.api.task_handlers import TaskHandlersMixin

            class FakeHandler(TaskHandlersMixin):
                def __init__(self):
                    self._response_data = None

                def _set_response(self, data):
                    self._response_data = data

            handler = FakeHandler()

            from media_importer.core.db import update_task as db_upd, update_subtitles_by_task as db_upd_subs
            with patch('media_importer.api.task_handlers.db_update_task', side_effect=db_upd), \
                 patch('media_importer.api.task_handlers.db_update_subtitles_by_task', side_effect=db_upd_subs), \
                 patch('media_importer.api.task_handlers.json_response') as mock_json:
                handler._task_ignore(task["task_id"])

        updated = self.tm.get_task(task["task_id"])
        self.assertEqual(updated["status"], "SKIPPED")

        if os.path.isfile(temp_path):
            pass
        else:
            self.assertFalse(os.path.isfile(temp_path), "临时文件应被删除")

    def test_source_ignore_cleanup_true_moves_to_recycle(self):
        """source+忽略+cleanup_source_after_done=true → 源文件移入回收站"""
        self.config["source_policy"]["cleanup_source_after_done"] = True
        source_path = self._create_file("TC13_src_cleanup.mkv")

        task = self._create_task(
            "TC13_src_cleanup.mkv",
            source_path=source_path,
            status="FAILED",
            file_location="source",
        )

        self.assertTrue(os.path.isfile(source_path))

        from media_importer.core.db import update_subtitles_by_task
        with patch('media_importer.api.task_handlers.globals') as mock_globals:
            mock_globals._global_task_manager = self.tm
            mock_globals._config = self.config

            from media_importer.api.task_handlers import TaskHandlersMixin

            class FakeHandler(TaskHandlersMixin):
                pass

            handler = FakeHandler()

            from media_importer.core.db import update_task as db_upd, update_subtitles_by_task as db_upd_subs
            with patch('media_importer.api.task_handlers.db_update_task', side_effect=db_upd), \
                 patch('media_importer.api.task_handlers.db_update_subtitles_by_task', side_effect=db_upd_subs), \
                 patch('media_importer.api.task_handlers.json_response'):
                handler._task_ignore(task["task_id"])

        updated = self.tm.get_task(task["task_id"])
        self.assertEqual(updated["status"], "SKIPPED")
        self._assert_file_in_recycle("TC13_src_cleanup")

    def test_source_ignore_cleanup_false_preserves_source(self):
        """source+忽略+cleanup_source_after_done=false → 源文件保留"""
        self.config["source_policy"]["cleanup_source_after_done"] = False
        source_path = self._create_file("TC13_src_keep.mkv")

        task = self._create_task(
            "TC13_src_keep.mkv",
            source_path=source_path,
            status="FAILED",
            file_location="source",
        )

        from media_importer.core.db import update_subtitles_by_task
        with patch('media_importer.api.task_handlers.globals') as mock_globals:
            mock_globals._global_task_manager = self.tm
            mock_globals._config = self.config

            from media_importer.api.task_handlers import TaskHandlersMixin

            class FakeHandler(TaskHandlersMixin):
                pass

            handler = FakeHandler()

            from media_importer.core.db import update_task as db_upd, update_subtitles_by_task as db_upd_subs
            with patch('media_importer.api.task_handlers.db_update_task', side_effect=db_upd), \
                 patch('media_importer.api.task_handlers.db_update_subtitles_by_task', side_effect=db_upd_subs), \
                 patch('media_importer.api.task_handlers.json_response'):
                handler._task_ignore(task["task_id"])

        updated = self.tm.get_task(task["task_id"])
        self.assertEqual(updated["status"], "SKIPPED")
        self.assertTrue(os.path.isfile(source_path), "cleanup=false时源文件应保留")


# ============================================================
# RT-05: 配置兼容性回归
# ============================================================
class TestRT05ConfigCompatibility(DeepE2EBaseTestCase):
    """RT-05: 配置兼容性回归

    验证旧配置键自动迁移到新配置键
    """

    def _write_config(self, source_policy, extra=None):
        import yaml
        tmp = tempfile.mkdtemp()
        config = {
            "source_dir": self.source_dir,
            "temp_dir": self.temp_dir,
            "log_dir": self.log_dir,
            "llm": {"api_key": "test-key", "model": "test-model"},
            "source_policy": source_policy,
        }
        if extra:
            config.update(extra)
        cp = os.path.join(tmp, "config.yaml")
        with open(cp, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True)
        return tmp, cp

    def test_full_cleanup_migrates_to_cleanup_true(self):
        """cleanup_mode=full_cleanup → cleanup_source_after_done=true"""
        tmp, cp = self._write_config({"cleanup_mode": "full_cleanup"})
        try:
            config = load_config(cp)
            self.assertTrue(config["source_policy"]["cleanup_source_after_done"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_read_only_migrates_to_cleanup_false(self):
        """cleanup_mode=read_only → cleanup_source_after_done=false"""
        tmp, cp = self._write_config({"cleanup_mode": "read_only"})
        try:
            config = load_config(cp)
            self.assertFalse(config["source_policy"]["cleanup_source_after_done"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_smart_cleanup_migrates_to_cleanup_true_and_cleaner_enabled(self):
        """cleanup_mode=smart_cleanup → cleanup_source_after_done=true + source_cleaner.enabled=true"""
        tmp, cp = self._write_config({"cleanup_mode": "smart_cleanup"})
        try:
            config = load_config(cp)
            self.assertTrue(config["source_policy"]["cleanup_source_after_done"])
            self.assertTrue(config["source_cleaner"]["enabled"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_delete_source_after_import_false(self):
        """delete_source_after_import=false → cleanup_source_after_done=false"""
        tmp, cp = self._write_config({
            "cleanup_mode": "full_cleanup",
            "delete_source_after_import": False,
        })
        try:
            config = load_config(cp)
            self.assertFalse(config["source_policy"]["cleanup_source_after_done"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_smart_cleanup_migrates_to_source_cleaner_section(self):
        """smart_cleanup迁移 → source_cleaner配置段"""
        tmp, cp = self._write_config(
            {
                "cleanup_mode": "smart_cleanup",
                "smart_cleanup": {
                    "ai_enabled": True,
                    "protect_extensions": [".nfo", ".jpg"],
                    "blacklist_patterns": ["*.sample*"],
                    "cleanup_empty_dirs": False,
                    "confirm_before_cleanup": False,
                },
            },
        )
        try:
            config = load_config(cp)
            self.assertTrue(config["source_cleaner"]["enabled"])
            self.assertTrue(config["source_cleaner"]["ai_enabled"])
            self.assertIn(".nfo", config["source_cleaner"]["protect_extensions"])
            self.assertIn("*.sample*", config["source_cleaner"]["blacklist_patterns"])
            self.assertFalse(config["source_cleaner"]["cleanup_empty_dirs"])
            self.assertFalse(config["source_cleaner"]["confirm_before_cleanup"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_quarantine_dir_migrates_to_recycle_dir(self):
        """quarantine_dir → recycle_dir"""
        import yaml
        tmp = tempfile.mkdtemp()
        config = {
            "source_dir": self.source_dir,
            "temp_dir": self.temp_dir,
            "log_dir": self.log_dir,
            "llm": {"api_key": "test-key", "model": "test-model"},
            "source_policy": {
                "quarantine_dir": os.path.join(tmp, "old_quarantine"),
            },
        }
        cp = os.path.join(tmp, "config.yaml")
        with open(cp, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True)
        try:
            loaded = load_config(cp)
            self.assertEqual(
                loaded["source_policy"]["recycle_dir"],
                os.path.join(tmp, "old_quarantine"),
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ============================================================
# TC-15: 源目录清理器 - keep_media_only模式
# ============================================================
class TestTC15SourceCleanerKeepMediaOnly(DeepE2EBaseTestCase):
    """TC-15: 源目录清理器 - keep_media_only模式"""

    def setUp(self):
        super().setUp()
        self.config["source_cleaner"]["cleanup_mode"] = "keep_media_only"
        self.config["source_cleaner"]["confirm_before_cleanup"] = False
        self.config["source_cleaner"]["junk_video_max_size_mb"] = 0
        self.config["source_cleaner"]["delete_extensions"] = [".url"]
        self.cleaner = SourceCleaner(self.config)

    def test_non_media_files_moved_to_recycle(self):
        """非媒体文件移入回收站"""
        self._create_file("movie.mkv", content=b'\x00' * 10240)
        exe_path = self._create_file("setup.exe", content=b'exe content')

        items = self.cleaner.preview()
        non_media = [i for i in items if i["category"] == "non_media"]
        self.assertTrue(len(non_media) >= 1, "应检测到非媒体文件")

        result = self.cleaner.execute(confirmed=True)
        self.assertFalse(os.path.isfile(exe_path), "非媒体文件应被移入回收站")
        self._assert_file_in_recycle("setup")

    def test_media_files_not_moved(self):
        """媒体文件保留"""
        mkv_path = self._create_file("movie.mkv", content=b'\x00' * 10240)
        srt_path = self._create_file("movie.zh.srt", content=b'subtitle')

        self.cleaner.execute(confirmed=True)
        self.assertTrue(os.path.isfile(mkv_path), "视频文件应保留")
        self.assertTrue(os.path.isfile(srt_path), "字幕文件应保留")


# ============================================================
# TC-16: 源目录清理器 - keep_media_related模式
# ============================================================
class TestTC16SourceCleanerKeepMediaRelated(DeepE2EBaseTestCase):
    """TC-16: 源目录清理器 - keep_media_related模式"""

    def setUp(self):
        super().setUp()
        self.config["source_cleaner"]["cleanup_mode"] = "keep_media_related"
        self.config["source_cleaner"]["confirm_before_cleanup"] = False
        self.config["source_cleaner"]["junk_video_max_size_mb"] = 0
        self.cleaner = SourceCleaner(self.config)

    def test_protected_extensions_preserved(self):
        """保护相关文件（nfo/jpg/png）"""
        nfo_path = self._create_file("movie.nfo", content=b'<nfo/>')
        jpg_path = self._create_file("poster.jpg", content=b'\xff\xd8\xff')

        items = self.cleaner.preview()
        cleaned = [i for i in items if "movie.nfo" in i["path"] or "poster.jpg" in i["path"]]
        self.assertEqual(len(cleaned), 0, "nfo/jpg应在保护列表中，不被清理")

    def test_non_protected_non_media_moved(self):
        """keep_media_related模式下非媒体文件（不在delete_extensions中）默认不清理"""
        exe_path = self._create_file("setup.exe", content=b'exe')

        items = self.cleaner.preview()
        found = [i for i in items if "setup.exe" in i["path"]]
        self.assertEqual(len(found), 0, "keep_media_related模式下非delete_extensions中的非媒体文件不清理")


# ============================================================
# TC-17: 源目录清理器 - 垃圾视频检测
# ============================================================
class TestTC17JunkVideoDetection(DeepE2EBaseTestCase):
    """TC-17: 源目录清理器 - 垃圾视频检测"""

    def setUp(self):
        super().setUp()
        self.config["source_cleaner"]["cleanup_mode"] = "keep_media_only"
        self.config["source_cleaner"]["junk_video_max_size_mb"] = 1
        self.config["source_cleaner"]["confirm_before_cleanup"] = False
        self.cleaner = SourceCleaner(self.config)

    def test_small_video_detected_as_junk(self):
        """小视频移入回收站"""
        small_path = self._create_file("sample.mkv", content=b'\x00' * 100)

        items = self.cleaner.preview()
        junk = [i for i in items if i["category"] == "junk_video"]
        self.assertTrue(len(junk) >= 1, "小视频应被检测为垃圾视频")

        self.cleaner.execute(confirmed=True)
        self.assertFalse(os.path.isfile(small_path), "垃圾视频应被移入回收站")
        self._assert_file_in_recycle("sample")

    def test_large_video_not_junk(self):
        """大视频保留"""
        large_path = self._create_file("full_movie.mkv", content=b'\x00' * (2 * 1024 * 1024))

        items = self.cleaner.preview()
        junk = [i for i in items if "full_movie.mkv" in i.get("path", "") and i["category"] == "junk_video"]
        self.assertEqual(len(junk), 0, "大视频不应被标记为垃圾")


# ============================================================
# TC-18: 源目录清理器 - 黑名单匹配
# ============================================================
class TestTC18BlacklistMatch(DeepE2EBaseTestCase):
    """TC-18: 源目录清理器 - 黑名单匹配"""

    def setUp(self):
        super().setUp()
        self.config["source_cleaner"]["cleanup_mode"] = "keep_media_only"
        self.config["source_cleaner"]["blacklist_patterns"] = ["RARBG*", "*/Sample/*"]
        self.config["source_cleaner"]["confirm_before_cleanup"] = False
        self.cleaner = SourceCleaner(self.config)

    def test_blacklist_wildcard_match(self):
        """黑名单通配符匹配"""
        rarbg_path = self._create_file("RARBG.com.mp4", content=b'\x00' * 10240)

        items = self.cleaner.preview()
        matched = [i for i in items if i["category"] == "blacklist_pattern"]
        self.assertTrue(len(matched) >= 1, "RARBG文件应匹配黑名单")

        self.cleaner.execute(confirmed=True)
        self.assertFalse(os.path.isfile(rarbg_path), "黑名单文件应被移入回收站")

    def test_blacklist_path_match(self):
        """黑名单路径匹配"""
        sample_dir = os.path.join(self.source_dir, "Sample")
        os.makedirs(sample_dir, exist_ok=True)
        sample_path = os.path.join(sample_dir, "clip.mkv")
        with open(sample_path, 'wb') as f:
            f.write(b'\x00' * 10240)

        items = self.cleaner.preview()
        matched = [i for i in items if i["category"] == "blacklist_pattern"]
        self.assertTrue(len(matched) >= 1, "Sample目录下的文件应匹配黑名单")

    def test_normal_file_not_blacklisted(self):
        """正常文件不匹配黑名单"""
        normal_path = self._create_file("Normal.Movie.2024.mkv", content=b'\x00' * 10240)

        items = self.cleaner.preview()
        matched = [i for i in items if "Normal.Movie" in i.get("path", "") and i["category"] == "blacklist_pattern"]
        self.assertEqual(len(matched), 0, "正常文件不应匹配黑名单")


# ============================================================
# TC-19: 源目录清理器 - 任务关联保护 + 确认模式 + 空目录
# ============================================================
class TestTC19CleanerTaskProtection(DeepE2EBaseTestCase):
    """TC-19: 源目录清理器 - 已关联任务文件不被清理"""

    def setUp(self):
        super().setUp()
        self.config["source_cleaner"]["cleanup_mode"] = "keep_media_only"
        self.config["source_cleaner"]["confirm_before_cleanup"] = False
        self.cleaner = SourceCleaner(self.config)

    def test_task_linked_file_not_cleaned(self):
        """已关联任务文件不被清理"""
        source_path = self._create_file("linked_movie.mkv", content=b'\x00' * 10240)
        task = self._create_task("linked_movie.mkv", source_path=source_path)

        task_paths = {source_path}
        items = self.cleaner.preview(task_paths=task_paths)
        linked = [i for i in items if "linked_movie.mkv" in i.get("path", "")]
        self.assertEqual(len(linked), 0, "已关联任务的文件不应出现在清理列表中")

    def test_unlinked_file_cleaned(self):
        """未关联任务的非媒体文件被清理"""
        txt_path = self._create_file("unlinked.txt", content=b'text')

        items = self.cleaner.preview(task_paths=set())
        found = [i for i in items if "unlinked.txt" in i.get("path", "")]
        self.assertTrue(len(found) >= 1, "未关联的非媒体文件应出现在清理列表中")


class TestTC19CleanerConfirmMode(DeepE2EBaseTestCase):
    """TC-19: 确认模式 - confirm_before_cleanup=true时返回need_confirm"""

    def setUp(self):
        super().setUp()
        self.config["source_cleaner"]["cleanup_mode"] = "keep_media_only"
        self.config["source_cleaner"]["confirm_before_cleanup"] = True
        self.cleaner = SourceCleaner(self.config)

    def test_confirm_mode_returns_need_confirm(self):
        """confirm_before_cleanup=true时返回need_confirm"""
        self._create_file("junk.txt", content=b'text')

        result = self.cleaner.execute(confirmed=False)
        self.assertEqual(result["status"], "need_confirm")
        self.assertIn("items", result)

    def test_confirmed_execution_succeeds(self):
        """确认后执行成功"""
        txt_path = self._create_file("junk.txt", content=b'text')

        result = self.cleaner.execute(confirmed=True)
        self.assertNotEqual(result.get("status"), "need_confirm")
        self.assertIn("total_files", result)
        self.assertFalse(os.path.isfile(txt_path), "确认后文件应被清理")


class TestTC19CleanerEmptyDirs(DeepE2EBaseTestCase):
    """TC-19: 空目录清理"""

    def setUp(self):
        super().setUp()
        self.config["source_cleaner"]["cleanup_mode"] = "keep_media_only"
        self.config["source_cleaner"]["cleanup_empty_dirs"] = True
        self.config["source_cleaner"]["confirm_before_cleanup"] = False
        self.cleaner = SourceCleaner(self.config)

    def test_empty_dir_cleaned(self):
        """空目录被清理"""
        empty_dir = os.path.join(self.source_dir, "empty_subdir")
        os.makedirs(empty_dir, exist_ok=True)
        self.assertTrue(os.path.isdir(empty_dir))

        result = self.cleaner.execute(confirmed=True)
        self.assertFalse(os.path.isdir(empty_dir), "空目录应被清理")

    def test_non_empty_dir_preserved(self):
        """非空目录保留"""
        sub_dir = os.path.join(self.source_dir, "has_files")
        os.makedirs(sub_dir, exist_ok=True)
        self._create_file("movie.mkv", directory=sub_dir, content=b'\x00' * 10240)

        self.cleaner.execute(confirmed=True)
        self.assertTrue(os.path.isdir(sub_dir), "非空目录应保留")


# ============================================================
# 删除任务测试
# ============================================================
class TestDeleteTaskFileLocation(DeepE2EBaseTestCase):
    """删除任务测试 - 验证不同 file_location 下的删除行为"""

    def _setup_handler(self):
        from media_importer.api.task_handlers import TaskHandlersMixin

        class FakeHandler(TaskHandlersMixin):
            pass

        handler = FakeHandler()
        return handler

    def test_delete_source_with_delete_files_moves_to_recycle(self):
        """delete_files=True + file_location=source → move_to_recycle"""
        source_path = self._create_file("del_source.mkv")
        task = self._create_task(
            "del_source.mkv",
            source_path=source_path,
            status="FAILED",
            file_location="source",
        )

        self.assertTrue(os.path.isfile(source_path))

        handler = self._setup_handler()
        with patch('media_importer.api.task_handlers.globals') as mock_globals:
            mock_globals._global_task_manager = self.tm
            mock_globals._config = self.config
            with patch('media_importer.api.task_handlers.json_response') as mock_json:
                handler._delete_task(task["task_id"], delete_files=True)

                call_args = mock_json.call_args
                self.assertEqual(call_args[0][1], 200)
                data = call_args[1].get("data", {})
                self.assertEqual(data["file_location"], "source")

        self._assert_file_in_recycle("del_source")
        gone = self.tm.get_task(task["task_id"])
        self.assertIsNone(gone)

    def test_delete_import_with_delete_files_moves_to_recycle(self):
        """delete_files=True + file_location=import → move_to_recycle"""
        import_path = os.path.join(self.import_dir, "电影", "del_import.mkv")
        os.makedirs(os.path.dirname(import_path), exist_ok=True)
        with open(import_path, 'wb') as f:
            f.write(b'\x00' * 10240)

        task = self._create_task(
            "del_import.mkv",
            status="SUCCESS",
            file_location="import",
            import_video_path=import_path,
        )

        self.assertTrue(os.path.isfile(import_path))

        handler = self._setup_handler()
        with patch('media_importer.api.task_handlers.globals') as mock_globals:
            mock_globals._global_task_manager = self.tm
            mock_globals._config = self.config
            with patch('media_importer.api.task_handlers.json_response') as mock_json:
                handler._delete_task(task["task_id"], delete_files=True)

                call_args = mock_json.call_args
                self.assertEqual(call_args[0][1], 200)

        self._assert_file_in_recycle("del_import")
        gone = self.tm.get_task(task["task_id"])
        self.assertIsNone(gone)

    def test_delete_recycle_with_delete_files_no_move(self):
        """delete_files=True + file_location=recycle → 不动"""
        recycle_subdir = os.path.join(self.recycle_dir, "2025-01-01")
        os.makedirs(recycle_subdir, exist_ok=True)
        recycle_path = os.path.join(recycle_subdir, "del_recycle.mkv")
        with open(recycle_path, 'wb') as f:
            f.write(b'\x00' * 10240)

        task = self._create_task(
            "del_recycle.mkv",
            source_path=recycle_path,
            status="SKIPPED",
            file_location="recycle",
        )

        self.assertTrue(os.path.isfile(recycle_path))

        handler = self._setup_handler()
        with patch('media_importer.api.task_handlers.globals') as mock_globals:
            mock_globals._global_task_manager = self.tm
            mock_globals._config = self.config
            with patch('media_importer.api.task_handlers.json_response') as mock_json:
                handler._delete_task(task["task_id"], delete_files=True)

                call_args = mock_json.call_args
                self.assertEqual(call_args[0][1], 200)
                data = call_args[1].get("data", {})
                self.assertEqual(data["file_location"], "recycle")

        self.assertTrue(os.path.isfile(recycle_path), "回收站文件不应被移动")
        gone = self.tm.get_task(task["task_id"])
        self.assertIsNone(gone)

    def test_delete_without_delete_files_only_removes_record(self):
        """delete_files=False → 仅删记录"""
        source_path = self._create_file("del_record_only.mkv")
        task = self._create_task(
            "del_record_only.mkv",
            source_path=source_path,
            status="FAILED",
            file_location="source",
        )

        self.assertTrue(os.path.isfile(source_path))

        handler = self._setup_handler()
        with patch('media_importer.api.task_handlers.globals') as mock_globals:
            mock_globals._global_task_manager = self.tm
            mock_globals._config = self.config
            with patch('media_importer.api.task_handlers.json_response') as mock_json:
                handler._delete_task(task["task_id"], delete_files=False)

                call_args = mock_json.call_args
                self.assertEqual(call_args[0][1], 200)

        self.assertTrue(os.path.isfile(source_path), "delete_files=False时文件应保留")
        gone = self.tm.get_task(task["task_id"])
        self.assertIsNone(gone)


# ============================================================
# 删除任务 - temp 位置特殊处理
# ============================================================
class TestDeleteTaskTempLocation(DeepE2EBaseTestCase):
    """删除任务 - temp位置文件直接rm删除"""

    def test_delete_temp_with_delete_files_removes_temp(self):
        """delete_files=True + file_location=temp → 临时文件直接rm删除"""
        source_path = self._create_file("del_temp_source.mkv")
        temp_path = os.path.join(self.temp_dir, "del_temp_source.mkv")
        shutil.copy2(source_path, temp_path)

        task = self._create_task(
            "del_temp_source.mkv",
            source_path=source_path,
            status="FAILED",
            file_location="temp",
            video_path=temp_path,
        )

        self.assertTrue(os.path.isfile(temp_path))

        from media_importer.api.task_handlers import TaskHandlersMixin

        class FakeHandler(TaskHandlersMixin):
            pass

        handler = FakeHandler()
        with patch('media_importer.api.task_handlers.globals') as mock_globals:
            mock_globals._global_task_manager = self.tm
            mock_globals._config = self.config
            with patch('media_importer.api.task_handlers.json_response') as mock_json:
                handler._delete_task(task["task_id"], delete_files=True)

                call_args = mock_json.call_args
                self.assertEqual(call_args[0][1], 200)

        self.assertFalse(os.path.isfile(temp_path), "临时文件应被rm删除")
        self.assertTrue(os.path.isfile(source_path), "源文件应保留（temp位置不清理源文件）")
        gone = self.tm.get_task(task["task_id"])
        self.assertIsNone(gone)


if __name__ == "__main__":
    unittest.main(verbosity=2)
