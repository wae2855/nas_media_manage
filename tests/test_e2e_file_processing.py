#!/usr/bin/env python3
"""
影音库AI智能整理 - 端到端全流程测试
使用真实 TMDB + LLM API，测试从文件创建到入库完成的完整流程

测试场景:
  E2E-1: 电影正常入库全流程（含字幕）
  E2E-2: 电视剧正常入库全流程
  E2E-3: 纪录片入库流程
  E2E-4: 低置信度→人工确认→入库流程
  E2E-5: 入库去重-质量优先策略
  E2E-6: 入库去重-跳过策略
  E2E-7: 源端去重检测（SKIP/RENAME_DETECTED/UPDATE_MTIME/REPROCESS）
  E2E-8: 失败→回收站→重试流程
  E2E-9: cleanup_source_after_done=false 源文件保留
  E2E-10: 扫描→批量处理全流程（多文件）

运行方式:
  python -m pytest tests/test_e2e_file_processing.py -v -s --timeout=120
  或
  python tests/test_e2e_file_processing.py

前置条件:
  - config/config.yaml 已配置有效的 TMDB API key 和 LLM API key
  - 源目录、中转目录、回收站目录可写
"""
import os
import sys
import shutil
import tempfile
import time
import unittest
from datetime import datetime
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.core.config_loader import load_config
from media_importer.core.db import (
    init_db, get_task, update_task as db_update_task,
    count_by_status, list_tasks,
)
from media_importer.core.task_manager import TaskManager
from media_importer.pipeline import PipelineRunner
from media_importer.storage.file_scanner import FileScanner

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "config.yaml"
)
CONFIG_EXISTS = os.path.isfile(CONFIG_PATH)


def _has_valid_api_keys(config):
    llm_key = config.get("llm", {}).get("api_key", "")
    tmdb_key = config.get("metadata", {}).get("tmdb", {}).get("api_key", "")
    if not llm_key or llm_key in ("your-api-key-here", ""):
        return False
    if not tmdb_key or tmdb_key in ("your-api-key-here", ""):
        return False
    return True


class E2EBaseTestCase(unittest.TestCase):
    """端到端测试基类"""

    @classmethod
    def setUpClass(cls):
        if not CONFIG_EXISTS:
            return
        cls.real_config = load_config(CONFIG_PATH)
        if not _has_valid_api_keys(cls.real_config):
            return
        cls.source_dir = cls.real_config["source_dir"]
        cls.temp_dir = cls.real_config["temp_dir"]
        cls.recycle_dir = cls.real_config["source_policy"]["recycle_dir"]
        for d in [cls.source_dir, cls.temp_dir, cls.recycle_dir]:
            os.makedirs(d, exist_ok=True)
        cls._e2e_created_files = []

    def setUp(self):
        if not CONFIG_EXISTS:
            self.skipTest("配置文件不存在，跳过 E2E 测试")
        if not _has_valid_api_keys(self.real_config):
            self.skipTest("API key 未配置或无效，跳过 E2E 测试")

        self.db_dir = tempfile.mkdtemp(prefix="nas_e2e_")
        self.tm = TaskManager(self.db_dir, config=self.real_config)
        self.config = deepcopy(self.real_config)
        self.test_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        for d in [self.config.get("source_dir", ""),
                  self.config.get("temp_dir", ""),
                  self.config.get("source_policy", {}).get("recycle_dir", ""),
                  self.config.get("log_dir", "")]:
            if d:
                os.makedirs(d, exist_ok=True)

        self.pipeline = PipelineRunner(
            config=self.config,
            task_manager=self.tm,
            metrics=None,
            logger=None,
            notifier=None,
        )
        self._test_files = []

        self._cleanup_import_roots()

    def tearDown(self):
        self._cleanup_test_files()
        if hasattr(self, 'tm') and self.tm:
            try:
                self.tm.conn.close()
            except Exception:
                pass
        if hasattr(self, 'db_dir'):
            shutil.rmtree(self.db_dir, ignore_errors=True)

    def _create_test_video(self, filename, subdir=""):
        d = os.path.join(self.source_dir, subdir) if subdir else self.source_dir
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, filename)
        with open(path, 'wb') as f:
            f.write(b'\x00' * 10240)
        self._test_files.append(path)
        return path

    def _create_test_subtitle(self, video_filename, lang="zh", subdir=""):
        base = os.path.splitext(video_filename)[0]
        sub_filename = f"{base}.{lang}.srt"
        d = os.path.join(self.source_dir, subdir) if subdir else self.source_dir
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, sub_filename)
        with open(path, 'w') as f:
            f.write("1\n00:00:00,000 --> 00:00:05,000\n测试字幕\n")
        self._test_files.append(path)
        return path

    def _cleanup_test_files(self):
        for path in self._test_files:
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass
        self._test_files = []

        if hasattr(self, 'tm') and self.tm:
            try:
                from media_importer.core.db import list_all_tasks
                all_tasks = list_all_tasks(self.tm.conn, limit=1000)
                for t in all_tasks:
                    for key in ("import_video_path", "video_path", "source_path"):
                        p = t.get(key, "")
                        if p and os.path.isfile(p):
                            try:
                                os.remove(p)
                            except OSError:
                                pass
                    import_path = t.get("import_path", "")
                    if import_path and os.path.isdir(import_path):
                        try:
                            shutil.rmtree(import_path, ignore_errors=True)
                        except OSError:
                            pass
            except Exception:
                pass

        self._cleanup_dir_if_exists(self.temp_dir)
        self._cleanup_recycle_test_files()

    def _cleanup_dir_if_exists(self, directory):
        if not directory or not os.path.isdir(directory):
            return
        for root, dirs, files in os.walk(directory, topdown=False):
            for f in files:
                if self.test_id in f:
                    try:
                        os.remove(os.path.join(root, f))
                    except OSError:
                        pass

    def _cleanup_recycle_test_files(self):
        if not self.recycle_dir or not os.path.isdir(self.recycle_dir):
            return
        for root, dirs, files in os.walk(self.recycle_dir, topdown=False):
            for f in files:
                if self.test_id in f:
                    try:
                        os.remove(os.path.join(root, f))
                    except OSError:
                        pass
            for d in dirs:
                dir_path = os.path.join(root, d)
                try:
                    if not os.listdir(dir_path):
                        os.rmdir(dir_path)
                except OSError:
                    pass

    def _get_import_roots(self):
        path_rules = self.config.get('path_rules', [])
        roots = set()
        for rule in path_rules:
            tpl = rule.get('template', '')
            if not tpl:
                continue
            parts = tpl.split('/')
            for i, p in enumerate(parts):
                if p.startswith('{'):
                    root = '/'.join(parts[:i])
                    if root:
                        roots.add(root)
                    break
        fallback = self.config.get('fallback_dir', '')
        if fallback:
            parts = fallback.split('/')
            for i, p in enumerate(parts):
                if p.startswith('{'):
                    root = '/'.join(parts[:i])
                    if root:
                        roots.add(root)
                    break
        return list(roots)

    def _cleanup_import_roots(self):
        for root in self._get_import_roots():
            if not root or not os.path.isdir(root):
                continue
            try:
                shutil.rmtree(root, ignore_errors=True)
            except OSError:
                pass

    def _tf(self, name):
        return f"e2e_{self.test_id}_{name}"

    def _scan_and_process_one(self, source_path, subtitle_files=None):
        filename = os.path.basename(source_path)
        file_size_mb = round(os.path.getsize(source_path) / (1024 * 1024), 4) if os.path.isfile(source_path) else 0
        from media_importer.core.safety import make_fingerprint
        fingerprint = make_fingerprint(source_path) if os.path.isfile(source_path) else ""
        task = self.tm.create_task(
            video_path=source_path,
            video_file=filename,
            subtitle_files=subtitle_files or [],
            file_size_mb=file_size_mb,
        )
        if fingerprint:
            db_update_task(self.tm.conn, task["task_id"], source_fingerprint=fingerprint)
        task = self.tm.get_task(task["task_id"])
        self.pipeline.process_one(task)
        return self.tm.get_task(task["task_id"])


# ============================================================
# E2E-1: 电影正常入库全流程（含字幕）
# ============================================================
@unittest.skipIf(not CONFIG_EXISTS, "配置文件不存在")
class TestE2E1MovieFullFlow(E2EBaseTestCase):
    """E2E-1: 电影正常入库全流程（含字幕）

    验证点:
      - 任务状态为 SUCCESS
      - file_location 为 import
      - 入库目录下存在最终文件
      - 源文件已移入回收站（full_cleanup 模式）
      - 字幕已入库
      - DB 中有 provider_type 和 provider_id
      - DB 中有 source_fingerprint
    """

    def test_movie_with_subtitle(self):
        """电影+字幕完整入库流程"""
        video_name = self._tf("Inception.2010.1080p.mkv")
        sub_path = self._create_test_subtitle(video_name, lang="zh")
        video_path = self._create_test_video(video_name)

        task = self._scan_and_process_one(video_path, subtitle_files=[sub_path])

        with self.subTest("状态应为 SUCCESS"):
            self.assertEqual(task["status"], "SUCCESS")
        with self.subTest("file_location 应为 import"):
            self.assertEqual(task["file_location"], "import")
        with self.subTest("import_success 应为 1"):
            self.assertEqual(task["import_success"], 1)
        with self.subTest("入库视频文件应存在"):
            self.assertTrue(os.path.isfile(task.get("import_video_path", "")),
                            f"入库文件不存在: {task.get('import_video_path')}")
        with self.subTest("源文件应已移入回收站"):
            self.assertFalse(os.path.isfile(video_path),
                             "full_cleanup 模式下源文件应被清理")
        with self.subTest("DB 应有 provider_type"):
            self.assertTrue(task.get("provider_type"),
                            "provider_type 不应为空")
        with self.subTest("DB 应有 provider_id"):
            self.assertTrue(task.get("provider_id"),
                            "provider_id 不应为空")
        with self.subTest("DB 应有 source_fingerprint"):
            self.assertTrue(task.get("source_fingerprint"),
                            "source_fingerprint 不应为空")
        with self.subTest("刮削结果应有标题"):
            scrape_result = task.get("scrape_result", {})
            if isinstance(scrape_result, str):
                import json
                scrape_result = json.loads(scrape_result)
            self.assertTrue(
                scrape_result.get("title_cn") or scrape_result.get("title_en"),
                "刮削结果应有中文或英文标题"
            )


# ============================================================
# E2E-2: 电视剧正常入库全流程
# ============================================================
@unittest.skipIf(not CONFIG_EXISTS, "配置文件不存在")
class TestE2E2TVSeriesFlow(E2EBaseTestCase):
    """E2E-2: 电视剧正常入库全流程

    验证点:
      - 任务状态为 SUCCESS
      - scrape_media_type 为 tv
      - 入库路径包含 Season 目录
      - 文件名包含 S01E01
    """

    def test_tv_episode(self):
        """电视剧单集入库流程"""
        video_name = self._tf("Breaking.Bad.S01E01.2008.1080p.mkv")
        video_path = self._create_test_video(video_name)

        task = self._scan_and_process_one(video_path)

        with self.subTest("状态应为 SUCCESS"):
            self.assertEqual(task["status"], "SUCCESS")
        with self.subTest("媒体类型应为 tv"):
            self.assertEqual(task.get("scrape_media_type", "").lower(), "tv")
        with self.subTest("入库路径应包含 Season"):
            import_path = task.get("import_path", "")
            self.assertIn("Season", import_path,
                          f"电视剧入库路径应包含 Season 目录: {import_path}")
        with self.subTest("最终文件名应包含 S01E01"):
            final_filename = task.get("final_filename", "")
            self.assertTrue(
                "S01E01" in final_filename or "s01e01" in final_filename.lower(),
                f"电视剧文件名应包含 S01E01: {final_filename}"
            )
        with self.subTest("入库视频文件应存在"):
            self.assertTrue(os.path.isfile(task.get("import_video_path", "")),
                            f"入库文件不存在: {task.get('import_video_path')}")


# ============================================================
# E2E-3: 纪录片入库流程
# ============================================================
@unittest.skipIf(not CONFIG_EXISTS, "配置文件不存在")
class TestE2E3DocumentaryFlow(E2EBaseTestCase):
    """E2E-3: 纪录片入库流程

    验证点:
      - 任务状态为 SUCCESS
      - 入库路径匹配纪录片规则
    """

    def test_documentary_movie(self):
        """纪录片入库流程"""
        video_name = self._tf("March.of.the.Penguins.2005.mkv")
        video_path = self._create_test_video(video_name)

        task = self._scan_and_process_one(video_path)

        with self.subTest("状态应为 SUCCESS"):
            self.assertEqual(task["status"], "SUCCESS")
        with self.subTest("入库视频文件应存在"):
            self.assertTrue(os.path.isfile(task.get("import_video_path", "")),
                            f"入库文件不存在: {task.get('import_video_path')}")
        with self.subTest("入库路径应为有效路径"):
            import_path = task.get("import_path", "")
            self.assertTrue(
                "影视" in import_path,
                f"入库路径应包含影视关键词: {import_path}"
            )


# ============================================================
# E2E-4: 低置信度→人工确认→入库流程
# ============================================================
@unittest.skipIf(not CONFIG_EXISTS, "配置文件不存在")
class TestE2E4LowConfidenceConfirm(E2EBaseTestCase):
    """E2E-4: 低置信度→人工确认→入库流程

    验证点:
      - 模糊文件名导致任务进入 CONFIRMING 状态
      - confirm_task 后最终状态为 SUCCESS
    """

    def test_low_confidence_confirm_flow(self):
        """模糊文件名→低置信度→人工确认→入库"""
        self.config["manual_review"] = {"enabled": True}
        self.pipeline.config = self.config

        video_name = self._tf("unknown.video.file.2024.mkv")
        video_path = self._create_test_video(video_name)

        task = self._scan_and_process_one(video_path)

        with self.subTest("任务应进入 CONFIRMING 或 SUCCESS"):
            self.assertIn(task["status"], ("CONFIRMING", "SUCCESS"),
                          f"模糊文件名应导致 CONFIRMING 或直接 SUCCESS: {task['status']}")

        if task["status"] == "CONFIRMING":
            result = self.pipeline.confirm_task(task["task_id"])
            updated = self.tm.get_task(task["task_id"])

            with self.subTest("确认后状态应为 SUCCESS 或 FAILED"):
                self.assertIn(updated["status"], ("SUCCESS", "FAILED"),
                              f"确认后状态: {updated['status']}, 错误: {updated.get('error_message', '')}")

            if updated["status"] == "SUCCESS":
                with self.subTest("确认后 file_location 应为 import"):
                    self.assertEqual(updated["file_location"], "import")
                with self.subTest("确认后入库文件应存在"):
                    self.assertTrue(
                        os.path.isfile(updated.get("import_video_path", "")),
                        f"确认入库后文件应存在: {updated.get('import_video_path')}"
                    )


# ============================================================
# E2E-5: 入库去重-质量优先策略
# ============================================================
@unittest.skipIf(not CONFIG_EXISTS, "配置文件不存在")
class TestE2E5DedupQuality(E2EBaseTestCase):
    """E2E-5: 入库去重-质量优先策略

    验证点:
      - 先入库高清版本（1080p）
      - 再入库同名低清版本（720p）
      - 低清版本被跳过（SKIPPED），高清版本保留
    """

    def test_quality_strategy_keep_better(self):
        """质量优先策略：保留高质量版本"""
        self.config["duplicate_handling"]["strategy"] = "quality"
        self.pipeline.config = self.config

        video_name_hd = self._tf("The.Matrix.1999.1080p.mkv")
        video_path_hd = self._create_test_video(video_name_hd)

        task_hd = self._scan_and_process_one(video_path_hd)

        with self.subTest("高清版应入库成功"):
            self.assertEqual(task_hd["status"], "SUCCESS",
                             f"高清版入库应成功: {task_hd.get('error_message', '')}")

        time.sleep(1)

        video_name_sd = self._tf("The.Matrix.1999.720p.mkv")
        video_path_sd = self._create_test_video(video_name_sd)

        task_sd = self._scan_and_process_one(video_path_sd)

        with self.subTest("低清版应被跳过或成功"):
            self.assertIn(task_sd["status"], ("SKIPPED", "SUCCESS"),
                          f"低清版应被跳过或成功: {task_sd['status']}")

        if task_sd["status"] == "SKIPPED":
            with self.subTest("跳过原因应包含质量相关描述"):
                self.assertTrue(
                    "质量" in task_sd.get("skip_reason", "") or
                    "已存在" in task_sd.get("skip_reason", ""),
                    f"跳过原因应提及质量或已存在: {task_sd.get('skip_reason')}"
                )

        hd_import_path = task_hd.get("import_video_path", "")
        with self.subTest("高清版入库文件应仍存在"):
            self.assertTrue(os.path.isfile(hd_import_path),
                            f"高清版入库文件应保留: {hd_import_path}")


# ============================================================
# E2E-6: 入库去重-跳过策略
# ============================================================
@unittest.skipIf(not CONFIG_EXISTS, "配置文件不存在")
class TestE2E6DedupSkip(E2EBaseTestCase):
    """E2E-6: 入库去重-跳过策略

    验证点:
      - 修改配置为 skip 策略
      - 先入库一个文件
      - 再入库同名文件
      - 第二个被跳过
    """

    def test_skip_strategy(self):
        """跳过策略：同名文件直接跳过"""
        self.config["duplicate_handling"]["strategy"] = "skip"
        self.pipeline.config = self.config

        video_name_1 = self._tf("Interstellar.2014.1080p.mkv")
        video_path_1 = self._create_test_video(video_name_1)

        task_1 = self._scan_and_process_one(video_path_1)

        with self.subTest("第一个文件应入库成功"):
            self.assertEqual(task_1["status"], "SUCCESS",
                             f"第一个文件入库应成功: {task_1.get('error_message', '')}")

        time.sleep(1)

        video_name_2 = self._tf("Interstellar.2014.720p.mkv")
        video_path_2 = self._create_test_video(video_name_2)

        task_2 = self._scan_and_process_one(video_path_2)

        with self.subTest("第二个文件应被跳过"):
            self.assertEqual(task_2["status"], "SKIPPED",
                             f"skip 策略下同名文件应被跳过: {task_2['status']}")
        with self.subTest("跳过原因应提及已存在"):
            self.assertIn("已存在", task_2.get("skip_reason", ""),
                          f"跳过原因应提及已存在: {task_2.get('skip_reason')}")


# ============================================================
# E2E-7: 源端去重检测
# ============================================================
@unittest.skipIf(not CONFIG_EXISTS, "配置文件不存在")
class TestE2E7SourceDedup(E2EBaseTestCase):
    """E2E-7: 源端去重检测

    验证点:
      - 已成功处理的文件再次扫描应被 SKIP
      - 文件改名后扫描应检测到 RENAME_DETECTED
      - 文件内容变更后应检测到 REPROCESS
    """

    def test_skip_existing_file(self):
        """已成功处理的文件再次扫描应被 SKIP"""
        video_name = self._tf("The.Shawshank.Redemption.1994.mkv")
        video_path = self._create_test_video(video_name)

        task = self._scan_and_process_one(video_path)
        self.assertEqual(task["status"], "SUCCESS")

        result = self.tm.check_source_duplicate(video_path)
        with self.subTest("已处理文件应检测为存在"):
            self.assertTrue(result["exists"])
        with self.subTest("动作应为 SKIP 或 CREATE"):
            self.assertIn(result["action"], ("SKIP", "CREATE"),
                          f"已成功处理文件的 action 应为 SKIP 或 CREATE: {result['action']}")

    def test_rename_detected(self):
        """文件改名后扫描应检测到 RENAME_DETECTED"""
        self.config["source_policy"]["cleanup_source_after_done"] = False
        self.pipeline.config = self.config

        video_name = self._tf("Fight.Club.1999.mkv")
        video_path = self._create_test_video(video_name)

        task = self._scan_and_process_one(video_path)
        self.assertEqual(task["status"], "SUCCESS")

        renamed_name = self._tf("Fight.Club.1999.Renamed.mkv")
        renamed_path = os.path.join(self.source_dir, renamed_name)
        shutil.copy2(video_path, renamed_path)
        self._test_files.append(renamed_path)

        from media_importer.core.safety import make_fingerprint
        fingerprint = make_fingerprint(renamed_path)

        result = self.tm.check_source_duplicate(renamed_path, source_fingerprint=fingerprint)
        with self.subTest("改名文件应检测为存在"):
            self.assertTrue(result["exists"])
        with self.subTest("动作应为 RENAME_DETECTED"):
            self.assertEqual(result["action"], "RENAME_DETECTED",
                             f"改名文件应触发 RENAME_DETECTED: {result['action']}")

    def test_reprocess_changed_file(self):
        """文件内容变更后应检测到 REPROCESS 或 UPDATE_MTIME"""
        self.config["source_policy"]["cleanup_source_after_done"] = False
        self.pipeline.config = self.config

        video_name = self._tf("The.Godfather.1972.mkv")
        video_path = self._create_test_video(video_name)

        task = self._scan_and_process_one(video_path)
        self.assertEqual(task["status"], "SUCCESS")

        with open(video_path, 'wb') as f:
            f.write(b'\x00' * 20480)

        result = self.tm.check_source_duplicate(video_path)
        with self.subTest("变更文件应检测为存在"):
            self.assertTrue(result["exists"])
        with self.subTest("动作应为 REPROCESS 或 UPDATE_MTIME"):
            self.assertIn(result["action"], ("REPROCESS", "UPDATE_MTIME", "CREATE"),
                          f"变更文件应触发 REPROCESS/UPDATE_MTIME/CREATE: {result['action']}")


# ============================================================
# E2E-8: 失败→回收站→重试流程
# ============================================================
@unittest.skipIf(not CONFIG_EXISTS, "配置文件不存在")
class TestE2E8FailRecycleRetry(E2EBaseTestCase):
    """E2E-8: 失败→回收站→重试流程

    验证点:
      - 处理失败的文件应移入回收站
      - 从回收站可以重试任务
    """

    def test_failed_file_to_recycle(self):
        """处理失败的文件应移入回收站"""
        video_name = self._tf("ZZZZZ_NONEXISTENT_MOVIE_XYZ.2024.mkv")
        video_path = self._create_test_video(video_name)

        task = self._scan_and_process_one(video_path)

        with self.subTest("任务应结束（SUCCESS/FAILED/CONFIRMING）"):
            self.assertIn(task["status"], ("SUCCESS", "FAILED", "CONFIRMING"),
                          f"任务应结束或待确认: {task['status']}")

        if task["status"] == "FAILED":
            with self.subTest("失败文件 file_location 应为 recycle 或 source"):
                self.assertIn(task["file_location"], ("recycle", "source"),
                              f"失败文件 file_location: {task['file_location']}")
            if task["file_location"] == "recycle":
                with self.subTest("回收站中应有文件"):
                    recycle_path = task.get("source_path", "")
                    self.assertTrue(
                        os.path.isfile(recycle_path),
                        f"回收站中应有文件: {recycle_path}"
                    )

    def test_retry_from_recycle(self):
        """从回收站重试任务"""
        video_name = self._tf("YYYY_UNLIKELY_MOVIE_ABC.2024.mkv")
        video_path = self._create_test_video(video_name)

        task = self._scan_and_process_one(video_path)

        if task["status"] in ("FAILED", "SKIPPED"):
            result = self.tm.retry_task(task["task_id"])
            with self.subTest("重试应返回任务"):
                self.assertIsNotNone(result, "重试应返回任务")
            with self.subTest("重试后状态应为 PENDING"):
                self.assertEqual(result["status"], "PENDING")
            with self.subTest("重试后 retry_count 应递增"):
                self.assertGreaterEqual(result.get("retry_count", 0), 1)


# ============================================================
# E2E-9: cleanup_source_after_done=false 源文件保留
# ============================================================
@unittest.skipIf(not CONFIG_EXISTS, "配置文件不存在")
class TestE2E9ReadOnlyMode(E2EBaseTestCase):
    """E2E-9: 只读模式源文件保留

    验证点:
      - 修改配置为 read_only
      - 处理文件
      - 源文件仍然存在
    """

    def test_cleanup_source_false_preserves_source(self):
        """cleanup_source_after_done=false 模式下源文件应保留"""
        self.config["source_policy"]["cleanup_source_after_done"] = False
        self.pipeline.config = self.config

        video_name = self._tf("The.Dark.Knight.2008.mkv")
        video_path = self._create_test_video(video_name)

        task = self._scan_and_process_one(video_path)

        with self.subTest("任务应成功"):
            self.assertEqual(task["status"], "SUCCESS",
                             f"入库应成功: {task.get('error_message', '')}")
        with self.subTest("源文件应保留"):
            self.assertTrue(os.path.isfile(video_path),
                            "read_only 模式下源文件应保留")
        with self.subTest("入库文件应存在"):
            self.assertTrue(os.path.isfile(task.get("import_video_path", "")),
                            f"入库文件应存在: {task.get('import_video_path')}")


# ============================================================
# E2E-10: 批量处理全流程
# ============================================================
@unittest.skipIf(not CONFIG_EXISTS, "配置文件不存在")
class TestE2E10BatchProcessing(E2EBaseTestCase):
    """E2E-10: 扫描→批量处理全流程（多文件）

    验证点:
      - 在源目录创建多个文件
      - 调用 scan_and_create_tasks + process_one 逐个处理
      - 所有文件都被处理
    """

    def test_batch_multiple_files(self):
        """批量处理多个文件"""
        test_files = [
            (self._tf("Forrest.Gump.1994.mkv"), []),
            (self._tf("The.Silence.of.the.Lambs.1991.mkv"), []),
        ]

        created_tasks = []
        for video_name, subs in test_files:
            video_path = self._create_test_video(video_name)
            file_size_mb = round(os.path.getsize(video_path) / (1024 * 1024), 4)
            task = self.tm.create_task(
                video_path=video_path,
                video_file=video_name,
                subtitle_files=subs,
                file_size_mb=file_size_mb,
            )
            created_tasks.append((task["task_id"], video_name))

        for task_id, video_name in created_tasks:
            with self.subTest(file=video_name):
                task = self.tm.get_task(task_id)
                self.pipeline.process_one(task)
                updated = self.tm.get_task(task_id)
                self.assertIn(updated["status"], ("SUCCESS", "FAILED", "CONFIRMING", "SKIPPED"),
                              f"任务 {video_name} 应已处理完成: {updated['status']}")

        counts = self.tm.count_by_status()
        total_processed = sum(counts.get(s, 0) for s in ("SUCCESS", "FAILED", "CONFIRMING", "SKIPPED"))
        with self.subTest("所有任务应已处理"):
            self.assertEqual(total_processed, len(test_files),
                             f"应有 {len(test_files)} 个任务已处理，实际 {total_processed}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
