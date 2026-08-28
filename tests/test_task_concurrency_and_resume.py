"""Phase 2 S2/S3 行为级测试：CAS 并发守护 / 断点续跑 / retry-all 收敛 / import 幂等。

验证目标（proposal 2026-08-23-state-machine-redesign.md 验收标准 3/4/5）：
- 并发 confirm 只成功一次（CAS）；
- retry 保留 temp checkpoint 且续跑跳过 copy；
- retry_all_failed 默认不复活 SKIPPED/CANCELLED；
- import 目标同指纹幂等成功。
"""
import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.core.db import init_db
from media_importer.core.db.task_repo import (
    claim_next_pending,
    compare_and_update_task,
    create_task,
    update_task,
)
from media_importer.core.task_manager import TaskManager


class _Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.conn = init_db(os.path.join(self.dir, "tasks.db"))
        self.tm = TaskManager.__new__(TaskManager)
        self.tm.conn = self.conn

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def _new_task(self, **fields):
        t = create_task(self.conn, source_path=f"/src/{fields.get('task_id', 'x')}.mkv",
                        source_filename="x.mkv", file_size_mb=1.0)
        update_task(self.conn, t["task_id"], **fields)
        return t["task_id"]


class TestConcurrentConfirmCAS(_Base):
    """并发双 confirm：CAS 只成功一次。"""

    def test_concurrent_claim_only_one_wins(self):
        tid = self._new_task(status="PENDING", stage="AWAIT_REVIEW")
        results = []
        barrier = threading.Barrier(2)

        def claim():
            barrier.wait()
            # 真实语义 = confirm.py 的 confirm_start claim（AWAIT_REVIEW→RUNNING）
            r = compare_and_update_task(
                self.conn, tid,
                expect_status="PENDING", expect_stage="AWAIT_REVIEW",
                confirm_status="CONFIRMED", stage="RUNNING",
            )
            results.append(r)

        t1 = threading.Thread(target=claim)
        t2 = threading.Thread(target=claim)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # 恰好一个成功，另一个 None
        winners = [r for r in results if r is not None]
        self.assertEqual(len(winners), 1, f"应恰有一个 CAS 胜者: {results}")
        self.assertEqual(winners[0]["confirm_status"], "CONFIRMED")
        self.assertEqual(winners[0]["stage"], "RUNNING")


class TestConcurrentQueuedClaim(_Base):
    """并发批处理领取：一个排队任务只能被一个执行器领取。"""

    def test_concurrent_claim_only_one_runner_wins(self):
        tid = self._new_task(status="PENDING", stage="QUEUED")
        results = []
        barrier = threading.Barrier(2)

        def claim():
            barrier.wait()
            results.append(claim_next_pending(self.conn))

        threads = [threading.Thread(target=claim) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        winners = [result for result in results if result is not None]
        self.assertEqual([result["task_id"] for result in winners], [tid])
        self.assertEqual(winners[0]["stage"], "RUNNING")

    def test_each_task_is_claimed_once(self):
        task_ids = {
            self._new_task(status="PENDING", stage="QUEUED")
            for _ in range(2)
        }
        claimed_ids = {
            claim_next_pending(self.conn)["task_id"],
            claim_next_pending(self.conn)["task_id"],
        }
        self.assertEqual(claimed_ids, task_ids)
        self.assertIsNone(claim_next_pending(self.conn))


class TestRetryAllConvergence(_Base):
    """D2 决策：retry_all 默认仅 FAILED，不复活 SKIPPED/CANCELLED。"""

    def test_default_only_failed(self):
        f = self._new_task(status="FAILED", stage="DONE")
        s = self._new_task(status="SKIPPED", stage="DONE")
        c = self._new_task(status="CANCELLED", stage="DONE")

        retried = self.tm.retry_all_failed()
        retried_ids = {t["task_id"] for t in retried}

        self.assertIn(f, retried_ids)
        self.assertNotIn(s, retried_ids)
        self.assertNotIn(c, retried_ids)

    def test_explicit_include_skipped(self):
        s = self._new_task(status="SKIPPED", stage="DONE")
        retried = self.tm.retry_all_failed(include_skipped=True)
        self.assertIn(s, {t["task_id"] for t in retried})

    def test_cancelled_never_resurrected_without_flag(self):
        c = self._new_task(status="CANCELLED", stage="DONE")
        retried = self.tm.retry_all_failed(include_skipped=True)
        self.assertNotIn(c, {t["task_id"] for t in retried})


class TestRetryCheckpoint(_Base):
    """S2：retry 保留 temp checkpoint（文件存在时）。"""

    def test_retry_keeps_existing_temp(self):
        temp_file = os.path.join(self.dir, "movie.mkv")
        with open(temp_file, "w") as f:
            f.write("x" * 1024)

        tid = self._new_task(status="FAILED", stage="DONE",
                             video_path=temp_file, file_location="temp",
                             retry_count=0)

        result = self.tm.retry_task(tid, resume=True)
        self.assertIsNotNone(result)
        self.assertEqual(result["stage"], "QUEUED")
        self.assertEqual(result["file_location"], "temp")
        self.assertEqual(result["video_path"], temp_file)  # checkpoint 保留

    def test_retry_clears_missing_temp(self):
        tid = self._new_task(status="FAILED", stage="DONE",
                             video_path="/nonexistent/m.mkv",
                             file_location="temp", retry_count=0)

        result = self.tm.retry_task(tid, resume=True)
        self.assertIsNotNone(result)
        self.assertEqual(result["file_location"], "source")
        self.assertEqual(result["video_path"], "")

    def test_retry_api_default_resumes(self):
        """API 层 retry 默认 resume=True（大文件不重拷）。"""
        temp_file = os.path.join(self.dir, "movie2.mkv")
        with open(temp_file, "w") as f:
            f.write("y" * 2048)
        tid = self._new_task(status="FAILED", stage="DONE",
                             video_path=temp_file, file_location="temp")
        result = self.tm.retry_task(tid)  # 默认 resume=True
        self.assertEqual(result["file_location"], "temp")


class TestImportIdempotent(unittest.TestCase):
    """S3：import 目标同指纹 → 幂等成功（不报错）。"""

    def test_same_fingerprint_idempotent(self):
        from media_importer.features.import_flow.services.file_operations import move_to_import

        d = tempfile.mkdtemp()
        try:
            src = os.path.join(d, "src.mkv")
            dest_dir = os.path.join(d, "media", "movies")
            os.makedirs(dest_dir, exist_ok=True)
            with open(src, "wb") as f:
                f.write(b"v" * 4096)
            # 预置同名同内容目标
            dest = os.path.join(dest_dir, "src.mkv")
            shutil.copyfile(src, dest)
            stat = os.stat(src)
            os.utime(dest, (stat.st_atime, stat.st_mtime))  # 对齐 mtime

            result = move_to_import(
                src, [], dest_dir,
                {"media_type": "movie", "title_cn": "src", "title_en": "src",
                 "year": 2020, "resolution": "1080p", "quality": "bluray"},
                {"movie": "{title_cn}.{ext}", "tv": "{title_cn}.{ext}",
                 "subtitle": "{title_cn}.{ext}", "raw": {}},
                allowed_base_dirs=[os.path.join(d, "media")],
            )
            self.assertTrue(result.get("idempotent"))
            self.assertEqual(result["video"], dest)
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
