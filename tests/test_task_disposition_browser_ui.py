"""Real-browser acceptance for task exit, source handling, and record deletion."""

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
from media_importer.features.tasks import complete_requested_stop
from media_importer.infrastructure.db import update_task

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
    raise RuntimeError("任务退出浏览器验收服务未在预期时间内启动")


def _write(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _card(page: Page, task_id: str):
    return page.locator(f'article.task-card[data-task-row="{task_id}"]')


def _wait_card_text(page: Page, task_id: str, text: str) -> None:
    page.wait_for_function(
        """([taskId, expected]) => {
          const card = document.querySelector(`[data-task-row="${taskId}"]`);
          return card && card.textContent.includes(expected);
        }""",
        arg=[task_id, text],
    )


class TestTaskDispositionCustomerBrowserUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="task_disposition_browser_"))
        cls.paths = {
            name: cls.tmpdir / name
            for name in (
                "source",
                "temp",
                "recycle",
                "logs",
                "resources",
                "library",
                "data",
            )
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
video_extensions:
  - .mkv
subtitle_extensions:
  - .srt
path_rules:
  - name: 电影规则
    conditions:
      media_type: movie
    library_root_id: main
    template: 电影/{{title_cn}} ({{year}})
filename_templates:
  movie: "{{title_cn}}.{{year}}.{{ext}}"
  subtitle: "{{video_filename}}.{{lang}}.{{ext}}"
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

        cls.queued_video = _write(
            cls.paths["source"] / "排队保留.2024.mkv",
            b"queued-source-must-stay",
        )
        queued = cls.manager.create_task(
            str(cls.queued_video),
            cls.queued_video.name,
            [],
        )
        update_task(
            cls.manager.conn,
            queued["task_id"],
            status="PENDING",
            stage="QUEUED",
        )
        cls.queued_id = queued["task_id"]

        cls.review_video = _write(
            cls.paths["source"] / "待确认回收.2024.mkv",
            b"review-video",
        )
        cls.review_subtitle = _write(
            cls.paths["source"] / "待确认回收.2024.zh.srt",
            b"review-subtitle",
        )
        cls.review_unrelated = _write(
            cls.paths["source"] / "待确认回收.说明.txt",
            b"unrelated-must-stay",
        )
        review = cls.manager.create_task(
            str(cls.review_video),
            cls.review_video.name,
            [str(cls.review_subtitle)],
        )
        update_task(
            cls.manager.conn,
            review["task_id"],
            status="PENDING",
            stage="AWAIT_REVIEW",
            scrape_title_cn="待确认回收",
            scrape_year="2024",
            scrape_result={
                "title_cn": "待确认回收",
                "year": 2024,
                "media_type": "movie",
                "dimensions": {"media_type": "movie"},
            },
            scrape_dimensions={"media_type": "movie"},
        )
        cls.review_id = review["task_id"]

        cls.failed_video = _write(
            cls.paths["source"] / "失败但保留.2024.mkv",
            b"failed-source-must-stay",
        )
        failed = cls.manager.create_task(
            str(cls.failed_video),
            cls.failed_video.name,
            [],
        )
        update_task(
            cls.manager.conn,
            failed["task_id"],
            status="FAILED",
            stage="DONE",
            error_message="模拟网络失败",
        )
        cls.failed_id = failed["task_id"]

        cls.running_video = _write(
            cls.paths["source"] / "运行中安全停止.2024.mkv",
            b"running-source-must-stay",
        )
        running = cls.manager.create_task(
            str(cls.running_video),
            cls.running_video.name,
            [],
        )
        update_task(
            cls.manager.conn,
            running["task_id"],
            status="PENDING",
            stage="RUNNING",
            step_name="import_transfer",
            percentage=84,
            bytes_copied=42 * 1024 * 1024,
            total_bytes=100 * 1024 * 1024,
            scrape_title_cn="运行中安全停止",
            scrape_year="2024",
            scrape_result={
                "title_cn": "运行中安全停止",
                "year": 2024,
                "media_type": "movie",
            },
        )
        cls.running_id = running["task_id"]

        conflict_dir = cls.paths["library"] / "电影" / "重复资源 (2024)"
        cls.conflict_target = _write(
            conflict_dir / "重复资源.2024.mkv",
            b"library-version-must-stay",
        )
        cls.conflict_source = _write(
            cls.paths["source"] / "重复资源.2024.mkv",
            b"incoming-version-to-recycle",
        )
        conflict = cls.manager.create_task(
            str(cls.conflict_source),
            cls.conflict_source.name,
            [],
        )
        update_task(
            cls.manager.conn,
            conflict["task_id"],
            status="PENDING",
            stage="AWAIT_REVIEW",
            file_location="source",
            video_path=str(cls.conflict_source),
            import_path=str(conflict_dir),
            final_filename=cls.conflict_target.name,
            scrape_title_cn="重复资源",
            scrape_year="2024",
            scrape_result={
                "title_cn": "重复资源",
                "year": 2024,
                "media_type": "movie",
                "dimensions": {"media_type": "movie"},
            },
            scrape_dimensions={"media_type": "movie"},
            dedup_result={
                "is_duplicate": True,
                "status": "awaiting_user",
                "conflict_type": "target_path",
                "existing_path": str(cls.conflict_target),
                "existing_file": cls.conflict_target.name,
                "existing_size": cls.conflict_target.stat().st_size,
                "replace_allowed": True,
                "suggested_filename": "重复资源.2024_保留1.mkv",
                "message": "目标片库已有同名影片",
            },
        )
        cls.conflict_id = conflict["task_id"]

        cls.completed_video = _write(
            cls.paths["library"] / "电影" / "已完成 (2023)" / "已完成.2023.mkv",
            b"completed-library-file-must-stay",
        )
        completed = cls.manager.create_task(
            str(cls.completed_video),
            cls.completed_video.name,
            [],
        )
        update_task(
            cls.manager.conn,
            completed["task_id"],
            status="SUCCESS",
            stage="DONE",
            import_success=1,
            file_location="import",
            video_path=str(cls.completed_video),
            import_video_path=str(cls.completed_video),
            import_path=str(cls.completed_video.parent),
            scrape_title_cn="已完成",
            scrape_year="2023",
            scrape_result={
                "title_cn": "已完成",
                "year": 2023,
                "media_type": "movie",
            },
        )
        cls.completed_id = completed["task_id"]

        cls.port = _free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.server = threading.Thread(
            target=start_server,
            args=("127.0.0.1", cls.port, cls.config),
            daemon=True,
        )
        cls.server.start()
        _wait_for_server(cls.port)
        # Startup correctly marks stale RUNNING rows as failed. Re-enter the
        # running fixture only after that recovery pass so this case represents
        # a task owned by the current live process.
        update_task(
            cls.manager.conn,
            cls.running_id,
            status="PENDING",
            stage="RUNNING",
            error_message="",
            step_name="import_transfer",
            percentage=84,
            bytes_copied=42 * 1024 * 1024,
            total_bytes=100 * 1024 * 1024,
        )
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.manager.conn.close()
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_customer_can_end_every_non_success_path_without_touching_library(self):
        page_errors: list[str] = []
        bad_responses: list[str] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on(
                "response",
                lambda response: bad_responses.append(
                    f"{response.status} {response.url}"
                )
                if response.status >= 500
                else None,
            )
            try:
                page.goto(self.base_url)
                page.wait_for_load_state("networkidle")
                page.locator(".bottom-nav [data-nav='tasks']").click()
                page.wait_for_selector("article.task-card")

                # Queued: end the task and explicitly keep the source in place.
                _card(page, self.queued_id).get_by_role(
                    "button", name="结束处理"
                ).click()
                modal = page.locator(".cinema-modal").last
                self.assertIn("目标片库受保护", modal.inner_text())
                modal.get_by_text("保留新资源", exact=True).click()
                modal.get_by_role("button", name="确认处理").click()
                _wait_card_text(page, self.queued_id, "已取消")
                self.assertEqual(
                    self.queued_video.read_bytes(),
                    b"queued-source-must-stay",
                )

                # Awaiting review: recycle only this task's video and subtitle.
                _card(page, self.review_id).get_by_role(
                    "button", name="不再处理"
                ).click()
                page.locator(".cinema-modal").last.get_by_role(
                    "button", name="确认处理"
                ).click()
                _wait_card_text(page, self.review_id, "已跳过")
                self.assertFalse(self.review_video.exists())
                self.assertFalse(self.review_subtitle.exists())
                self.assertEqual(
                    self.review_unrelated.read_bytes(),
                    b"unrelated-must-stay",
                )

                # Running: show honest target-write progress, request a safe stop,
                # then let the worker finish the stop at its cooperative checkpoint.
                running_card = _card(page, self.running_id)
                self.assertIn("写入目标片库", running_card.inner_text())
                self.assertIn("42.0 MB / 100.0 MB", running_card.inner_text())
                running_card.get_by_role("button", name="停止任务").click()
                running_modal = page.locator(".cinema-modal").last
                running_modal.get_by_text("保留新资源", exact=True).click()
                running_modal.get_by_role(
                    "button", name="安全停止并处理"
                ).click()
                _wait_card_text(page, self.running_id, "正在停止")
                stopped = complete_requested_stop(
                    self.manager,
                    self.config,
                    self.running_id,
                )
                self.assertEqual(stopped.code, 200)
                page.get_by_role("button", name="刷新任务列表").click()
                _wait_card_text(page, self.running_id, "已取消")
                self.assertEqual(
                    self.running_video.read_bytes(),
                    b"running-source-must-stay",
                )

                # Duplicate: keep the existing library version and recycle only
                # the newly-added resource.
                _card(page, self.conflict_id).get_by_role(
                    "button", name="处理片库冲突"
                ).click()
                conflict_modal = page.locator(".cinema-modal").last
                self.assertIn("片库现有文件未发生任何改动", conflict_modal.inner_text())
                conflict_modal.get_by_role(
                    "button", name="保留片库，回收新资源"
                ).click()
                _wait_card_text(page, self.conflict_id, "已跳过")
                self.assertEqual(
                    self.conflict_target.read_bytes(),
                    b"library-version-must-stay",
                )
                self.assertFalse(self.conflict_source.exists())

                # Failed: the mobile dialog must fit, then keep source and finish.
                page.set_viewport_size({"width": 390, "height": 844})
                _card(page, self.failed_id).get_by_role(
                    "button", name="不再处理"
                ).click()
                mobile_modal = page.locator(".cinema-modal").last
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
                    path=str(
                        SCREENSHOT_DIR / "task-disposition-customer-mobile.png"
                    ),
                    full_page=False,
                )
                mobile_modal.get_by_text("保留新资源", exact=True).click()
                mobile_modal.get_by_role("button", name="确认处理").click()
                _wait_card_text(page, self.failed_id, "已跳过")
                self.assertEqual(
                    self.failed_video.read_bytes(),
                    b"failed-source-must-stay",
                )
                page.set_viewport_size({"width": 1440, "height": 1000})

                # Success: deleting history is record-only and leaves the library file.
                _card(page, self.completed_id).get_by_role(
                    "button", name="删除记录"
                ).click()
                record_modal = page.locator(".cinema-modal").last
                self.assertIn(
                    "来源文件和目标片库文件都不会改动",
                    record_modal.inner_text(),
                )
                record_modal.get_by_role("button", name="确认").click()
                page.wait_for_function(
                    "taskId => !document.querySelector(`[data-task-row=\"${taskId}\"]`)",
                    arg=self.completed_id,
                )
                self.assertEqual(
                    self.completed_video.read_bytes(),
                    b"completed-library-file-must-stay",
                )

                page.screenshot(
                    path=str(SCREENSHOT_DIR / "task-disposition-customer-final.png"),
                    full_page=True,
                )
                self.assertEqual(page_errors, [])
                self.assertEqual(bad_responses, [])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
