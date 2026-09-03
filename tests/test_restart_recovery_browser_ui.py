"""真实浏览器验收：无中心中转与三类中断恢复结果。"""

from __future__ import annotations

import shutil
import socket
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from media_importer.api.handler import start_server
from media_importer.core.task_manager import TaskManager
from media_importer.features.configuration import load_config
from media_importer.infrastructure.db import get_task, update_task
from media_importer.infrastructure.filesystem import hash_file

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIR = ROOT / "output" / "playwright"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(port: int, timeout: float = 10) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/health",
                timeout=2,
            ) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("中断恢复浏览器验收服务未启动")


def _write(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _card(page: Page, task_id: str):
    return page.locator(f'article.task-card[data-task-row="{task_id}"]')


class TestRestartRecoveryBrowserUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="restart_recovery_browser_"))
        cls.paths = {
            name: cls.tmpdir / name
            for name in ("source", "recycle", "logs", "resources", "library", "data")
        }
        for path in cls.paths.values():
            path.mkdir(parents=True, exist_ok=True)

        cls.config_path = cls.tmpdir / "config.yaml"
        cls.config_path.write_text(
            f"""source_dir: {cls.paths['source']}
log_dir: {cls.paths['logs']}
resource_dir: {cls.paths['resources']}
library_roots:
  - id: main
    name: 主片库
    path: {cls.paths['library']}
    enabled: true
default_library_root_id: main
fallback_library_root_id: main
fallback_dir: 待整理
source_policy:
  mode: preserve_all
  disposal_mode: local_recycle
  recycle_dir: {cls.paths['recycle']}
file_watcher:
  enabled: false
metadata:
  providers: []
""",
            encoding="utf-8",
        )
        cls.config = load_config(str(cls.config_path))
        cls.config["_data_dir"] = str(cls.paths["data"])
        cls.manager = TaskManager(str(cls.paths["data"]), config={})

        cls.precommit_id = cls._seed_bundle(
            "提交前中断.2024.mkv",
            source_payload=b"precommit-source",
            target_payload=b"precommit-source",
            state="STAGING",
            target_location="stage",
        )
        cls.committed_id = cls._seed_bundle(
            "完整提交后中断.2024.mkv",
            source_payload=b"committed-source",
            target_payload=b"committed-source",
            state="COMMITTED",
            target_location="dest",
        )
        cls.ambiguous_id = cls._seed_bundle(
            "片库现场需检查.2024.mkv",
            source_payload=b"expected-source",
            target_payload=b"changed-target",
            state="COMMITTED",
            target_location="dest",
        )

        cls.port = _free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.server = threading.Thread(
            target=start_server,
            args=("127.0.0.1", cls.port, cls.config),
            daemon=True,
        )
        cls.server.start()
        _wait_for_server(cls.port)
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def _seed_bundle(
        cls,
        filename: str,
        *,
        source_payload: bytes,
        target_payload: bytes,
        state: str,
        target_location: str,
    ) -> str:
        source = _write(cls.paths["source"] / filename, source_payload)
        task = cls.manager.create_task(str(source), filename, [])
        task_id = task["task_id"]
        destination = cls.paths["library"] / "电影" / filename
        stage = Path(f"{destination}.{task_id}.1.bundle.tmp")
        selected = stage if target_location == "stage" else destination
        _write(selected, target_payload)
        manifest = [{
            "kind": "video",
            "source_path": str(source),
            "stage_path": str(stage),
            "dest_path": str(destination),
            "fingerprint": hash_file(str(source)),
            "transfer_mode": "copy",
            "state": target_location,
        }]
        update_task(
            cls.manager.conn,
            task_id,
            status="PENDING",
            stage="RUNNING",
            file_location="source",
            bundle_state=state,
            bundle_manifest=manifest,
            bundle_committed=1 if state == "COMMITTED" else 0,
        )
        return task_id

    @classmethod
    def tearDownClass(cls):
        cls.manager.conn.close()
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_customer_sees_safe_restart_results_and_no_staging_setting(self):
        precommit = get_task(self.manager.conn, self.precommit_id)
        committed = get_task(self.manager.conn, self.committed_id)
        ambiguous = get_task(self.manager.conn, self.ambiguous_id)
        self.assertEqual((precommit["status"], precommit["bundle_state"]), ("FAILED", "ROLLED_BACK"))
        self.assertEqual((committed["status"], committed["bundle_state"]), ("SUCCESS", "COMMITTED_RECOVERED"))
        self.assertEqual((ambiguous["status"], ambiguous["bundle_state"]), ("FAILED", "RECOVERY_REQUIRED"))
        self.assertTrue(Path(precommit["source_path"]).is_file())
        self.assertTrue(Path(committed["source_path"]).is_file())

        page_errors: list[str] = []
        bad_responses: list[str] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on(
                "response",
                lambda response: bad_responses.append(f"{response.status} {response.url}")
                if response.status >= 500
                else None,
            )
            try:
                page.goto(self.base_url)
                page.wait_for_load_state("networkidle")
                page.locator(".bottom-nav [data-nav='tasks']").click()
                page.wait_for_selector("article.task-card")

                precommit_card = _card(page, self.precommit_id)
                self.assertIn("来源文件保持不变", precommit_card.inner_text())
                self.assertIn("重新刮削", precommit_card.inner_text())
                precommit_card.get_by_role("button", name="查看详情").click()
                self.assertIn("片库临时内容已清理", page.locator(".cinema-modal").last.inner_text())
                page.locator(".cinema-modal").last.get_by_text(
                    "关闭", exact=True
                ).click()

                committed_card = _card(page, self.committed_id)
                self.assertIn("已完成", committed_card.inner_text())
                committed_card.get_by_role("button", name="查看详情").click()
                committed_modal = page.locator(".cinema-modal").last
                self.assertIn("来源已保留", committed_modal.inner_text())
                self.assertIn("为安全起见已保留来源内容", committed_modal.inner_text())
                page.screenshot(
                    path=str(SCREENSHOT_DIR / "restart-recovery-committed-desktop.png"),
                    full_page=False,
                )
                committed_modal.get_by_text("关闭", exact=True).click()

                page.set_viewport_size({"width": 390, "height": 844})
                ambiguous_card = _card(page, self.ambiguous_id)
                ambiguous_card.get_by_role("button", name="查看详情").click()
                ambiguous_modal = page.locator(".cinema-modal").last
                self.assertIn("请人工检查后处理", ambiguous_modal.inner_text())
                overflow = page.evaluate(
                    """() => ({
                      page: document.documentElement.scrollWidth - window.innerWidth,
                      modal: document.querySelector('.cinema-modal').scrollWidth
                        - document.querySelector('.cinema-modal').clientWidth,
                    })"""
                )
                self.assertLessEqual(overflow["page"], 0)
                self.assertLessEqual(overflow["modal"], 0)
                page.screenshot(
                    path=str(SCREENSHOT_DIR / "restart-recovery-review-mobile.png"),
                    full_page=False,
                )
                ambiguous_modal.get_by_text("关闭", exact=True).click()

                page.locator(".bottom-nav [data-nav='config']").click()
                page.evaluate("setConfigStage('storage')")
                page.wait_for_selector(
                    "#storage-readiness-grid .storage-readiness-card"
                )
                self.assertEqual(page.get_by_text("本地中转", exact=True).count(), 0)
                self.assertEqual(page.locator('[data-fnos-auth-role="temp"]').count(), 0)
                page.screenshot(
                    path=str(SCREENSHOT_DIR / "storage-without-staging-mobile.png"),
                    full_page=False,
                )
            finally:
                browser.close()

        self.assertEqual(page_errors, [])
        self.assertEqual(bad_responses, [])


if __name__ == "__main__":
    unittest.main()
