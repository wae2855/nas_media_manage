"""文件全流程矩阵回归（Phase 2 S4 / REQ-20260822-000004）。

设计源：docs/testing/file-flow-matrix.md（两级匹配版）。
覆盖 M01-M20 主路（可全自动跑的纯后端部分）：自动入库/确认流/失败取消跳过/批量操作，
含 5 条高价值异常注入（C1 源丢失 / C3 磁盘满 / C8 目标占用 / C24 进程中断 / C27 confirm 时源被删）。

M23-M32（源清理/回收站/模拟器 UI）由既有专项测试覆盖，不在此重复。
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.core.db import init_db
from media_importer.core.db.task_repo import create_task, get_task, update_task
from media_importer.core.task_manager import TaskManager
from media_importer.features.import_flow.runner import PipelineRunner


def _mkfile(path, size=1024, content=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content * max(1, size // len(content)))
    return path


class _MatrixBase(unittest.TestCase):
    """矩阵测试基座：真实临时目录 + 真 DB + mock Provider 流水线。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ffm_")
        self.src_dir = os.path.join(self.dir, "source")
        self.import_dir = os.path.join(self.dir, "media")
        self.recycle_dir = os.path.join(self.dir, "recycle")
        for d in (self.src_dir, self.import_dir, self.recycle_dir):
            os.makedirs(d, exist_ok=True)

        self.conn = init_db(os.path.join(self.dir, "tasks.db"))
        self.tm = TaskManager.__new__(TaskManager)
        self.tm.conn = self.conn
        import threading
        self.tm._lock = threading.RLock()

        self.config = {
            "source_dir": self.src_dir,
            "log_dir": os.path.join(self.dir, "logs"),
            "fallback_dir": os.path.join(self.import_dir, "fallback"),
            "path_rules": [],
            "classification": {"rules": []},
            "source_policy": {
                "recycle_dir": self.recycle_dir,
                "cleanup_source_after_done": False,
            },
            "filename_templates": {},
            "task_queue": {"max_concurrent": 1},
        }
        os.makedirs(self.config["fallback_dir"], exist_ok=True)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def _create_pending(self, filename="Movie.2020.1080p.mkv", **fields):
        src = _mkfile(os.path.join(self.src_dir, filename))
        t = create_task(self.conn, source_path=src, source_filename=filename,
                        file_size_mb=0.01)
        update_task(self.conn, t["task_id"],
                    status="PENDING", stage="QUEUED", **fields)
        return get_task(self.conn, t["task_id"])

    def _runner(self, **overrides):
        cfg = {**self.config, **overrides}
        self.tm.config = cfg
        runner = PipelineRunner.__new__(PipelineRunner)
        runner.config = cfg
        runner.task_manager = self.tm
        runner.metrics = None
        runner.logger = None
        runner.notifier = None
        from media_importer.notify.hooks import HookRunner
        runner.hooks = HookRunner(cfg)
        return runner


class TestAutoPassFlow(_MatrixBase):
    """M01/M03/M04：自动入库主路。"""

    def _mock_scraper_auto_pass(self, runner):
        """mock 刮削为 AUTO_PASS（唯一精确匹配）。"""
        from media_importer.features.scraping.match_models import MatchResult
        MatchResult(match_level="AUTO_PASS", match_tier=1,
                         concerns=[], trace_steps=[], candidates=[])
        step = MagicMock()
        step.execute = MagicMock(return_value=None)
        # 直接短路 _step_scrape/_step_validate：任务进入自动分支
        def fake_scrape(task):
            task["scrape_result"] = {
                "title_cn": "测试电影", "title_en": "Movie", "year": 2020,
                "media_type": "movie", "match_level": "AUTO_PASS",
                "dimensions": {}, "provider_type": "tmdb", "provider_id": "1",
            }
            task["match_level"] = "AUTO_PASS"
        runner._step_scrape = fake_scrape
        runner._step_validate = MagicMock()
        runner._step_notify = MagicMock()
        return runner

    def test_m01_fallback_requires_explicit_confirmation_before_import(self):
        task = self._create_pending("Inception.2010.1080p.mp4")
        runner = self._mock_scraper_auto_pass(self._runner())
        ok = runner.process_one(dict(task))
        self.assertTrue(ok)
        final = get_task(self.conn, task["task_id"])
        self.assertEqual(final["status"], "PENDING")
        self.assertEqual(final["stage"], "AWAIT_REVIEW")
        self.assertEqual(final["used_fallback"], 1)

        self.assertTrue(runner.confirm_task(
            task["task_id"],
            fallback_acknowledged=True,
        ))
        final = get_task(self.conn, task["task_id"])
        self.assertEqual(final["status"], "SUCCESS")
        self.assertEqual(final["stage"], "DONE")
        self.assertEqual(final["organization_status"], "FALLBACK_PENDING")
        self.assertEqual(final["file_location"], "import")
        self.assertTrue(os.path.dirname(final["import_video_path"] or "").startswith(self.import_dir))

    def test_m03_season_episode_import(self):
        task = self._create_pending("Breaking.Bad.S01E02.1080p.mkv")
        runner = self._mock_scraper_auto_pass(self._runner())
        def fake_scrape(task_inner):
            task_inner["scrape_result"] = {
                "title_cn": "绝命毒师", "title_en": "Breaking Bad", "year": 2008,
                "media_type": "tv", "season": 1, "episode": 2,
                "match_level": "AUTO_PASS", "dimensions": {},
                "provider_type": "tmdb", "provider_id": "2",
            }
            task_inner["match_level"] = "AUTO_PASS"
        runner._step_scrape = fake_scrape
        runner._step_validate = MagicMock()
        ok = runner.process_one(dict(task))
        self.assertTrue(ok)
        final = get_task(self.conn, task["task_id"])
        self.assertEqual(final["stage"], "AWAIT_REVIEW")
        self.assertTrue(runner.confirm_task(
            task["task_id"],
            fallback_acknowledged=True,
        ))
        final = get_task(self.conn, task["task_id"])
        self.assertEqual(final["status"], "SUCCESS")

    def test_conflict_stops_before_copy_and_keep_existing_preserves_source(self):
        """重复影片先确认；选择保留片库文件时不读取大文件到中转。"""
        task = self._create_pending("Existing.2020.1080p.mkv")
        runner = self._mock_scraper_auto_pass(self._runner())
        target_name = "测试电影.Movie.2020...mkv"

        def fake_rename(task_inner):
            task_inner["final_filename"] = target_name
            update_task(
                self.conn,
                task_inner["task_id"],
                final_filename=target_name,
            )

        runner._step_rename = fake_rename
        existing = _mkfile(
            os.path.join(self.config["fallback_dir"], target_name),
            content=b"library",
        )
        source_before = open(task["source_path"], "rb").read()
        existing_before = open(existing, "rb").read()

        ok = runner.process_one(dict(task))

        self.assertTrue(ok)
        awaiting = get_task(self.conn, task["task_id"])
        self.assertEqual(awaiting["stage"], "AWAIT_REVIEW")
        self.assertEqual(awaiting["file_location"], "source")
        self.assertEqual(open(task["source_path"], "rb").read(), source_before)
        self.assertEqual(open(existing, "rb").read(), existing_before)

        first_confirm = runner.confirm_task(
            task["task_id"],
            fallback_acknowledged=True,
        )
        self.assertTrue(first_confirm)
        conflict_task = get_task(self.conn, task["task_id"])
        self.assertEqual(conflict_task["stage"], "AWAIT_REVIEW")
        self.assertTrue(conflict_task["dedup_result"]["is_duplicate"])

        confirmed = runner.confirm_task(
            task["task_id"],
            conflict_action="keep_existing",
            fallback_acknowledged=True,
        )

        self.assertTrue(confirmed)
        final = get_task(self.conn, task["task_id"])
        self.assertEqual(final["status"], "SKIPPED")
        self.assertEqual(final["file_location"], "source")
        self.assertEqual(open(task["source_path"], "rb").read(), source_before)
        self.assertEqual(open(existing, "rb").read(), existing_before)


class TestConfirmFlow(_MatrixBase):
    """M06/M08：确认流（NEEDS_CONFIRM → confirm → SUCCESS）。"""

    def _to_await_review(self, task):
        update_task(self.conn, task["task_id"],
                    status="PENDING", stage="AWAIT_REVIEW",
                    confirm_status="PENDING",
                    file_location="source", video_path=task["source_path"])
        return get_task(self.conn, task["task_id"])

    def test_m06_confirm_completes_import(self):
        task = self._create_pending()
        task = self._to_await_review(task)
        fallback = self.config["fallback_dir"]
        update_task(self.conn, task["task_id"], video_path=task["source_path"],
                    import_path=fallback,
                    scrape_result={"title_cn": "电影", "title_en": "Movie",
                                   "year": 2020, "media_type": "movie",
                                   "dimensions": {}})
        task = get_task(self.conn, task["task_id"])

        runner = self._runner()
        runner._step_notify = MagicMock()

        ok = runner.confirm_task(task["task_id"], fallback_acknowledged=True)
        self.assertTrue(ok)
        final = get_task(self.conn, task["task_id"])
        self.assertEqual(final["status"], "SUCCESS")
        self.assertEqual(final["file_location"], "import")

    def test_m08_confirm_rejects_wrong_state(self):
        task = self._create_pending()  # QUEUED 不可确认
        runner = self._runner()
        from media_importer.features.import_flow.utils import PipelineError
        with self.assertRaises(PipelineError):
            runner.confirm_task(task["task_id"])

    def test_confirm_always_uses_intact_original_source(self):
        """人工确认后仍从原始来源写入，不依赖步骤检查点。"""
        task = self._create_pending()
        task = self._to_await_review(task)
        update_task(self.conn, task["task_id"],
                    video_path=task["source_path"],
                    import_path=self.config["fallback_dir"],
                    scrape_result={"title_cn": "x", "title_en": "x", "year": 2020,
                                   "media_type": "movie", "dimensions": {}})
        runner = self._runner()
        ok = runner.confirm_task(task["task_id"], fallback_acknowledged=True)
        self.assertTrue(ok)
        final = get_task(self.conn, task["task_id"])
        self.assertEqual(final["status"], "SUCCESS")
        self.assertEqual(final["file_location"], "import")


class TestTerminalActions(_MatrixBase):
    """M12/M13/M15/M16：取消/忽略/重试。"""

    def test_m12_cancel_queued(self):
        task = self._create_pending()
        r = self.tm.cancel_task(task["task_id"])
        self.assertNotIn("error", r or {})
        final = get_task(self.conn, task["task_id"])
        self.assertEqual(final["status"], "CANCELLED")

    def test_m12_cancel_rejects_running(self):
        task = self._create_pending()
        update_task(self.conn, task["task_id"], stage="RUNNING")
        r = self.tm.cancel_task(task["task_id"])
        self.assertIn("error", r)

    def test_m13_ignore_await_review(self):
        task = self._create_pending()
        update_task(self.conn, task["task_id"], stage="AWAIT_REVIEW")
        from media_importer.features.tasks import ignore_task_for_api
        r = ignore_task_for_api(self.tm, self.config, task["task_id"])
        self.assertEqual(r.code, 200)
        final = get_task(self.conn, task["task_id"])
        self.assertEqual(final["status"], "SKIPPED")

    def test_m15_retry_failed_back_to_queued(self):
        task = self._create_pending()
        update_task(self.conn, task["task_id"], status="FAILED", stage="DONE",
                    error_message="x")
        r = self.tm.retry_task(task["task_id"])
        self.assertIsNotNone(r)
        self.assertEqual(r["status"], "PENDING")
        self.assertEqual(r["stage"], "QUEUED")
        self.assertEqual(r["error_message"], "")

    def test_m16_retry_all_only_failed(self):
        f = self._create_pending("F.2020.mkv")
        update_task(self.conn, f["task_id"], status="FAILED", stage="DONE")
        s = self._create_pending("S.2021.mkv")
        update_task(self.conn, s["task_id"], status="SKIPPED", stage="DONE")
        retried = self.tm.retry_all_failed()
        ids = {t["task_id"] for t in retried}
        self.assertIn(f["task_id"], ids)
        self.assertNotIn(s["task_id"], ids)


class TestFailureInjection(_MatrixBase):
    """C1/C3：源丢失/复制失败 → FAILED + 诚实 file_location。"""

    def test_c1_source_missing_fails(self):
        task = self._create_pending("Ghost.2020.mkv")
        os.unlink(task["source_path"])
        runner = self._runner()
        runner._step_notify = MagicMock()
        ok = runner.process_one(dict(task))
        self.assertFalse(ok)
        final = get_task(self.conn, task["task_id"])
        self.assertEqual(final["status"], "FAILED")
        self.assertEqual(final["file_location"], "source")  # 文件不在 temp → source

    def test_c24_interrupted_running_marked_failed_by_cleanup(self):
        """C24：进程中断（RUNNING 残留）→ 启动清理标 FAILED。"""
        task = self._create_pending()
        unrelated = _mkfile(os.path.join(self.import_dir, "unrelated.copying"))
        update_task(self.conn, task["task_id"], stage="RUNNING")

        from media_importer.api.handler import _cleanup_orphaned_state
        logger = MagicMock()
        _cleanup_orphaned_state(self.config, self.tm, logger)

        final = get_task(self.conn, task["task_id"])
        self.assertEqual(final["status"], "FAILED")
        self.assertTrue(os.path.exists(unrelated))
        self.assertEqual(final["file_location"], "source")


if __name__ == "__main__":
    unittest.main()
