"""Customer-view browser acceptance for fallback and reorganization tasks."""

from __future__ import annotations

import os
import shutil
import socket
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import Page, sync_playwright

from media_importer.api.handler import start_server
from media_importer.core.task_manager import TaskManager
from media_importer.features.configuration import load_config
from media_importer.features.tasks.organization_service import (
    create_reorganization_task_for_api,
)
from media_importer.infrastructure.db import (
    get_subtitles_by_task,
    update_subtitle,
    update_task,
)
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
            response = urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/health",
                timeout=2,
            )
            if response.status == 200:
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("浏览器验收服务未在预期时间内启动")


def _write_file(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _create_completed_fallback(
    manager: TaskManager,
    library: Path,
    *,
    title: str,
    year: int,
    with_subtitle: bool = True,
) -> tuple[dict, Path, list[Path]]:
    fallback = library / "待整理"
    video = fallback / f"{title}.{year}.mkv"
    _write_file(video, f"fallback-video:{title}".encode())
    subtitles: list[Path] = []
    if with_subtitle:
        subtitle = fallback / f"{title}.{year}.zh.srt"
        _write_file(subtitle, f"fallback-subtitle:{title}".encode())
        subtitles.append(subtitle)
    task = manager.create_task(
        str(video),
        video.name,
        [str(path) for path in subtitles],
    )
    update_task(
        manager.conn,
        task["task_id"],
        status="SUCCESS",
        stage="DONE",
        import_success=1,
        file_location="import",
        video_path=str(video),
        import_video_path=str(video),
        import_path=str(fallback),
        final_filename=video.name,
        scrape_title_cn=title,
        scrape_title_en=title,
        scrape_year=str(year),
        scrape_result={
            "title_cn": title,
            "title_en": title,
            "year": year,
            "media_type": "movie",
            "dimensions": {},
        },
        scrape_dimensions={},
    )
    for row in get_subtitles_by_task(manager.conn, task["task_id"]):
        update_subtitle(
            manager.conn,
            row["id"],
            status="SUCCESS",
            import_path=row["source_path"],
            target_path=row["source_path"],
            planned_filename=os.path.basename(row["source_path"]),
        )
    return manager.get_task(task["task_id"]), video, subtitles


def _create_pending_fallback(
    manager: TaskManager,
    source: Path,
    fallback: Path,
) -> tuple[dict, Path, Path]:
    video = source / "未匹配新片.2024.mkv"
    subtitle = source / "未匹配新片.2024.zh.srt"
    _write_file(video, b"new-unmatched-video")
    _write_file(subtitle, b"new-unmatched-subtitle")
    task = manager.create_task(str(video), video.name, [str(subtitle)])
    task = update_task(
        manager.conn,
        task["task_id"],
        status="PENDING",
        stage="AWAIT_REVIEW",
        confirm_status="PENDING",
        file_location="source",
        video_path=str(video),
        import_path=str(fallback),
        final_filename=video.name,
        scrape_title_cn="未匹配新片",
        scrape_title_en="Unmatched New Movie",
        scrape_year="2024",
        scrape_result={
            "title_cn": "未匹配新片",
            "title_en": "Unmatched New Movie",
            "year": 2024,
            "dimensions": {},
        },
        scrape_dimensions={},
        match_level="NEEDS_CONFIRM",
        match_concerns=[{
            "code": "FALLBACK_REORGANIZATION",
            "message": "当前资料未匹配正式规则",
        }],
        used_fallback=1,
    )
    return task, video, subtitle


def _task_card(page: Page, title: str, *, reorganization: bool | None = None):
    cards = page.locator("article.task-card").filter(has_text=title)
    kind_tag = page.locator(
        ".task-card-tags-above-dims",
        has_text="重新整理",
    )
    if reorganization is True:
        return cards.filter(has=kind_tag).first
    if reorganization is False:
        return cards.filter(has_not=kind_tag).first
    return cards.first


def _refresh_until(page: Page, predicate, *, attempts: int = 80) -> None:
    for _ in range(attempts):
        refresh = page.get_by_role("button", name="刷新任务列表")
        if refresh.count():
            refresh.click()
        page.wait_for_timeout(150)
        if predicate():
            return
    raise AssertionError("前端任务状态未在预期时间内刷新")


class TestTaskOrganizationCustomerBrowserUi(unittest.TestCase):
    """One complete customer journey covering every reorganization boundary."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="task_organization_browser_"))
        cls.paths = {
            name: cls.tmpdir / name
            for name in ("source", "temp", "recycle", "logs", "resources", "library", "data")
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
  - name: 正式电影规则
    conditions:
      media_type: movie
    library_root_id: main
    template: 电影/{{title_cn}} ({{year}})
filename_templates:
  movie: "{{title_cn}}.{{year}}.{{ext}}"
  subtitle: "{{video_filename}}.{{lang}}.{{ext}}"
source_policy:
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

        manager = TaskManager(str(cls.paths["data"]), config={})
        for index in range(23):
            _create_completed_fallback(
                manager,
                cls.paths["library"],
                title=f"分页稳定性样本 {index + 1:02d}",
                year=1980 + index,
                with_subtitle=False,
            )
        cls.history_parent, cls.history_video, cls.history_subtitles = (
            _create_completed_fallback(
                manager,
                cls.paths["library"],
                title="小姐",
                year=2016,
            )
        )
        cls.conflict_parent, cls.conflict_video, cls.conflict_subtitles = (
            _create_completed_fallback(
                manager,
                cls.paths["library"],
                title="花样年华",
                year=2000,
            )
        )
        cls.pending_fallback, cls.pending_source_video, cls.pending_source_subtitle = (
            _create_pending_fallback(
                manager,
                cls.paths["source"],
                cls.paths["library"] / "待整理",
            )
        )
        running_video = cls.paths["source"] / "大文件进度测试.2025.mkv"
        _write_file(running_video, b"running-progress-fixture")
        running_task = manager.create_task(str(running_video), running_video.name, [])
        update_task(
            manager.conn,
            running_task["task_id"],
            status="PENDING",
            stage="RUNNING",
            current_step=1,
            step_name="copy_transfer",
            percentage=10,
            bytes_copied=10 * 1024 * 1024,
            total_bytes=100 * 1024 * 1024,
            scrape_title_cn="大文件进度测试",
            scrape_year="2025",
            scrape_result={
                "title_cn": "大文件进度测试",
                "year": 2025,
                "media_type": "movie",
                "dimensions": {"media_type": "movie"},
            },
            scrape_dimensions={"media_type": "movie"},
        )
        cls.manager = manager
        cls.running_task_id = running_task["task_id"]

        cls.conflict_target = (
            cls.paths["library"] / "电影" / "花样年华 (2000)" / "花样年华.2000.mkv"
        )
        _write_file(cls.conflict_target, b"existing-library-version")

        # Simulate a process that crashed after committing a reorganization bundle.
        recovery_parent, recovery_video, recovery_subtitles = _create_completed_fallback(
            manager,
            cls.paths["library"],
            title="重启恢复片",
            year=2023,
        )
        update_task(
            manager.conn,
            recovery_parent["task_id"],
            used_fallback=1,
            organization_status="FALLBACK_PENDING",
        )
        recovery_child = create_reorganization_task_for_api(
            manager,
            cls.config,
            recovery_parent["task_id"],
        ).data["task"]
        recovery_target_dir = cls.paths["library"] / "电影" / "重启恢复片 (2023)"
        recovery_target_video = recovery_target_dir / recovery_video.name
        recovery_target_subtitle = recovery_target_dir / recovery_subtitles[0].name
        recovery_target_dir.mkdir(parents=True, exist_ok=True)
        os.replace(recovery_video, recovery_target_video)
        os.replace(recovery_subtitles[0], recovery_target_subtitle)
        subtitle_row = get_subtitles_by_task(manager.conn, recovery_child["task_id"])[0]
        update_subtitle(
            manager.conn,
            subtitle_row["id"],
            planned_filename=recovery_target_subtitle.name,
        )
        recovery_members = []
        for index, (kind, source_path, dest_path) in enumerate((
            ("video", recovery_video, recovery_target_video),
            ("subtitle", recovery_subtitles[0], recovery_target_subtitle),
        )):
            recovery_members.append({
                "kind": kind,
                "source_path": str(source_path),
                "stage_path": f"{dest_path}.{recovery_child['task_id']}.{index + 1}.bundle.tmp",
                "dest_path": str(dest_path),
                "fingerprint": hash_file(str(dest_path)),
                "state": "published",
            })
        update_task(
            manager.conn,
            recovery_child["task_id"],
            status="PENDING",
            stage="RUNNING",
            import_path=str(recovery_target_dir),
            final_filename=recovery_target_video.name,
            used_fallback=0,
            bundle_state="COMMITTED",
            bundle_manifest=recovery_members,
            bundle_committed=1,
        )
        cls.recovery_parent_id = recovery_parent["task_id"]
        cls.recovery_child_id = recovery_child["task_id"]

        cls.search_requests: list[dict] = []

        def fake_search(
            config,
            query,
            *,
            year=None,
            media_type=None,
            language=None,
            limit=20,
        ):
            cls.search_requests.append({
                "query": query,
                "year": year,
                "media_type": media_type,
                "language": language,
                "limit": limit,
            })
            return [
                {
                    "id": str(1000 + index),
                    "title": "小姐" if index == 0 else f"小姐候选 {index + 1}",
                    "original_title": "The Handmaiden" if index == 0 else "Candidate",
                    "year": 2016 + index,
                    "media_type": "movie",
                    "overview": "用于本地浏览器验收的 Provider 候选。",
                    "provider_type": "browser-test",
                    "poster_url": "",
                    "vote_average": 8.1,
                }
                for index in range(min(12, limit))
            ]

        def fake_load_candidate(
            config,
            conn,
            *,
            provider_type,
            item_id,
            media_type,
            language=None,
        ):
            return {
                "scrape_result": {
                    "title_cn": "小姐",
                    "title_en": "The Handmaiden",
                    "original_title": "아가씨",
                    "year": 2016,
                    "media_type": "movie",
                    "overview": "本地浏览器验收资料。",
                    "provider_type": provider_type,
                    "provider_id": item_id,
                    "dimensions": {"media_type": "movie"},
                },
                "dimensions": {"media_type": "movie"},
                "dim_sources": {"media_type": "provider:browser-test"},
                "language": language or "zh-CN",
            }

        cls.search_patch = patch(
            "media_importer.api.task_handlers.search_provider_candidates",
            side_effect=fake_search,
        )
        cls.load_patch = patch(
            "media_importer.features.tasks.search_service.load_provider_candidate",
            side_effect=fake_load_candidate,
        )
        cls.search_patch.start()
        cls.load_patch.start()

        cls.port = _free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.server = threading.Thread(
            target=start_server,
            args=("127.0.0.1", cls.port, cls.config),
            daemon=True,
        )
        cls.server.start()
        _wait_for_server(cls.port)
        update_task(
            manager.conn,
            cls.running_task_id,
            status="PENDING",
            stage="RUNNING",
            error_message="",
            step_name="copy_transfer",
            percentage=10,
            bytes_copied=10 * 1024 * 1024,
            total_bytes=100 * 1024 * 1024,
        )
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.search_patch.stop()
        cls.load_patch.stop()
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_complete_customer_journey(self):
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

                # Startup backfill keeps historical fallback tasks completed and visible.
                history = _task_card(page, "小姐", reorganization=False)
                self.assertIn("已完成", history.inner_text())
                self.assertIn("已安全入库，等待整理", history.inner_text())
                self.assertIn("待整理", history.inner_text())
                self.assertNotIn("需确认", history.inner_text())
                self.assertEqual(history.get_by_role("button", name="重新整理").count(), 1)

                # A committed bundle is recovered on startup and shown as two clean completions.
                recovered_cards = page.locator("article.task-card").filter(has_text="重启恢复片")
                self.assertEqual(recovered_cards.count(), 2)
                for index in range(2):
                    self.assertIn("已完成", recovered_cards.nth(index).inner_text())
                    self.assertNotIn("待整理", recovered_cards.nth(index).inner_text())

                page.screenshot(
                    path=str(SCREENSHOT_DIR / "organization-customer-01-initial.png"),
                    full_page=True,
                )

                # Progress polling updates only the changed card. Stable cards keep their
                # original DOM node, so posters and the whole list do not flash. Loaded
                # pages also stay present instead of collapsing back to one API page.
                page.get_by_role("button", name="加载更多").click()
                page.wait_for_function(
                    "() => document.querySelectorAll('article.task-card').length > 20"
                )
                loaded_card_count = page.locator("article.task-card").count()
                stable_card = history.element_handle()
                self.assertIsNotNone(stable_card)
                page.evaluate("window.scrollTo({ top: 700, behavior: 'instant' })")
                page.wait_for_timeout(100)
                stable_scroll_y = page.evaluate("window.scrollY")
                update_task(
                    self.manager.conn,
                    self.running_task_id,
                    step_name="copy_transfer",
                    percentage=55,
                    bytes_copied=55 * 1024 * 1024,
                    total_bytes=100 * 1024 * 1024,
                )
                page.wait_for_function(
                    """taskId => {
                      const card = document.querySelector(`[data-task-row="${taskId}"]`);
                      return card && card.textContent.includes("55.0 MB / 100.0 MB · 55%");
                    }""",
                    arg=self.running_task_id,
                )
                self.assertTrue(page.evaluate("node => node.isConnected", stable_card))
                self.assertEqual(page.locator("article.task-card").count(), loaded_card_count)
                self.assertEqual(page.evaluate("window.scrollY"), stable_scroll_y)
                update_task(
                    self.manager.conn,
                    self.running_task_id,
                    status="SUCCESS",
                    stage="DONE",
                    percentage=100,
                    bytes_copied=100 * 1024 * 1024,
                )
                page.wait_for_function(
                    """taskId => {
                      const card = document.querySelector(`[data-task-row="${taskId}"]`);
                      return card && card.textContent.includes("已完成");
                    }""",
                    arg=self.running_task_id,
                )
                self.assertTrue(page.evaluate("node => node.isConnected", stable_card))
                self.assertEqual(page.locator("article.task-card").count(), loaded_card_count)
                self.assertEqual(page.evaluate("window.scrollY"), stable_scroll_y)

                # Create a linked child through the completed parent detail.
                history.get_by_role("button", name="查看详情").click()
                self.assertIn(
                    "影片已安全入库到待整理区",
                    page.locator(".cinema-modal").last.inner_text(),
                )
                self.assertEqual(page.get_by_role("button", name="保存").count(), 0)
                page.get_by_role("button", name="创建重新整理任务").click()
                page.wait_for_selector("text=正在准备重新整理")
                self.assertIn(
                    "当前资料仍未匹配正式规则",
                    page.locator(".cinema-modal").last.inner_text(),
                )
                self.assertEqual(page.get_by_role("button", name="确认重新整理").count(), 0)

                # The same detail remains usable without horizontal scrolling on a phone.
                page.set_viewport_size({"width": 390, "height": 844})
                page.wait_for_timeout(150)
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
                    path=str(SCREENSHOT_DIR / "organization-customer-02-mobile-child.png"),
                    full_page=False,
                )
                page.set_viewport_size({"width": 1440, "height": 1000})

                # Manual scraping exposes type/language/year and at least ten candidates.
                page.get_by_role("button", name="手动刮削").click()
                page.locator("#scrape-search-query").fill("小姐 2016")
                page.locator("#scrape-search-media-type").select_option("movie")
                page.locator("#scrape-search-language").select_option("zh-CN")
                page.locator("#scrape-search-year").fill("2016")
                page.get_by_role("button", name="搜索前 20 条").click()
                page.wait_for_selector("text=找到 12 条结果")
                self.assertEqual(page.locator(".tmdb-scrape-card").count(), 12)
                page.locator(".tmdb-scrape-card").first.click()
                self.assertIn("The Handmaiden", page.locator("#scrape-search-detail").inner_text())
                page.screenshot(
                    path=str(SCREENSHOT_DIR / "organization-customer-03-manual-search.png"),
                    full_page=False,
                )
                page.get_by_role("button", name="使用这份资料").click()
                page.wait_for_selector("text=已经匹配正式入库规则")
                self.assertIn(
                    str(self.paths["library"] / "电影" / "小姐 (2016)"),
                    page.locator(".cinema-modal").last.inner_text(),
                )
                self.assertEqual(page.get_by_role("button", name="确认重新整理").count(), 1)
                self.assertTrue(any(
                    request == {
                        "query": "小姐 2016",
                        "year": 2016,
                        "media_type": "movie",
                        "language": "zh-CN",
                        "limit": 20,
                    }
                    for request in self.search_requests
                ))

                # Confirming moves video and subtitle as one bundle; parent remains completed.
                page.get_by_role("button", name="确认重新整理").click()
                _refresh_until(
                    page,
                    lambda: (
                        page.locator("article.task-card")
                        .filter(has_text="小姐")
                        .filter(has_text="已完成")
                        .count()
                        >= 2
                    ),
                )
                destination = self.paths["library"] / "电影" / "小姐 (2016)"
                self.assertTrue((destination / "小姐.2016.mkv").is_file())
                self.assertTrue((destination / "小姐.2016.zh.srt").is_file())
                self.assertFalse(self.history_video.exists())
                self.assertFalse(self.history_subtitles[0].exists())
                finished_history = _task_card(page, "小姐", reorganization=False)
                self.assertIn("已完成", finished_history.inner_text())
                self.assertNotIn("待整理", finished_history.inner_text())
                self.assertEqual(finished_history.get_by_role("button", name="重新整理").count(), 0)
                self.assertEqual(finished_history.get_by_role("button", name="调整位置").count(), 1)
                page.screenshot(
                    path=str(SCREENSHOT_DIR / "organization-customer-04-completed.png"),
                    full_page=True,
                )

                # A normally completed item can create a separate audited manual move.
                finished_history.get_by_role("button", name="调整位置").click()
                page.wait_for_selector("text=指定片库子目录")
                relocation_modal = page.locator(".cinema-modal").last
                self.assertIn(str(destination / "小姐.2016.mkv"), relocation_modal.inner_text())
                relocation_modal.get_by_text("指定片库子目录").click()
                relocation_modal.locator("#relocation-root").select_option("main")
                relocation_modal.locator("#relocation-relative-dir").fill("人工收藏/获奖电影")
                relocation_modal.get_by_role("button", name="创建人工调整任务").click()
                page.wait_for_selector("text=正在准备人工调整位置")
                manual_modal = page.locator(".cinema-modal").last
                self.assertIn("原位置：", manual_modal.inner_text())
                self.assertIn("目标位置：", manual_modal.inner_text())
                self.assertEqual(page.get_by_role("button", name="手动刮削").count(), 0)
                self.assertEqual(page.get_by_role("button", name="确认调整位置").count(), 1)
                page.get_by_role("button", name="确认调整位置").click()
                manual_target = self.paths["library"] / "人工收藏" / "获奖电影"
                _refresh_until(
                    page,
                    lambda: (manual_target / "小姐.2016.mkv").is_file(),
                )
                self.assertTrue((manual_target / "小姐.2016.zh.srt").is_file())
                self.assertFalse((destination / "小姐.2016.mkv").exists())
                self.assertGreaterEqual(
                    page.locator("article.task-card").filter(has_text="人工调整").count(),
                    1,
                )

                # A target conflict is explained in the UI; replace is forbidden for reorganization.
                conflict_parent = _task_card(page, "花样年华", reorganization=False)
                conflict_parent.get_by_role("button", name="重新整理").click()
                page.locator('select[data-task-dim="media_type"]').select_option("movie")
                page.get_by_role("button", name="保存").click()
                page.wait_for_selector("text=已经匹配正式入库规则")
                page.get_by_role("button", name="确认重新整理").click()
                _refresh_until(
                    page,
                    lambda: _task_card(page, "花样年华", reorganization=True)
                    .get_by_role("button", name="查看详情")
                    .count()
                    == 1,
                )
                conflict_child = _task_card(page, "花样年华", reorganization=True)
                conflict_child.get_by_role("button", name="查看详情").click()
                page.wait_for_selector("text=片库现有文件未发生任何改动")
                conflict_modal = page.locator(".cinema-modal").last
                self.assertIn("保留现状，不再整理", conflict_modal.inner_text())
                self.assertIn("两个都保留", conflict_modal.inner_text())
                self.assertNotIn("替换片库文件", conflict_modal.inner_text())
                self.assertNotIn("回收新资源", conflict_modal.inner_text())
                page.screenshot(
                    path=str(SCREENSHOT_DIR / "organization-customer-05-conflict.png"),
                    full_page=False,
                )
                page.get_by_role("button", name="保留现状，不再整理").click()
                _refresh_until(
                    page,
                    lambda: "待整理" in _task_card(
                        page,
                        "花样年华",
                        reorganization=False,
                    ).inner_text(),
                )
                self.assertEqual(self.conflict_target.read_bytes(), b"existing-library-version")
                self.assertTrue(self.conflict_video.is_file())
                self.assertTrue(self.conflict_subtitles[0].is_file())

                # A new fallback import requires an explicit customer acknowledgement.
                pending = _task_card(page, "未匹配新片", reorganization=False)
                pending.get_by_role("button", name="查看详情").click()
                pending_modal = page.locator(".cinema-modal").last
                page.screenshot(
                    path=str(SCREENSHOT_DIR / "organization-customer-06-fallback-review.png"),
                    full_page=False,
                )
                self.assertEqual(
                    page.get_by_role("button", name="确认放入待整理区").count(),
                    1,
                    pending_modal.inner_text(),
                )
                page.get_by_role("button", name="确认放入待整理区").click()
                _refresh_until(
                    page,
                    lambda: (
                        "已完成" in _task_card(page, "未匹配新片").inner_text()
                        and "待整理" in _task_card(page, "未匹配新片").inner_text()
                    ),
                )
                self.assertTrue(
                    (self.paths["library"] / "待整理" / "未匹配新片.2024.mkv").is_file()
                )
                self.assertTrue(
                    (self.paths["library"] / "待整理" / "未匹配新片.2024.zh.srt").is_file()
                )
                page.screenshot(
                    path=str(SCREENSHOT_DIR / "organization-customer-06-fallback-complete.png"),
                    full_page=True,
                )

                self.assertEqual(page_errors, [])
                self.assertEqual(bad_responses, [])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
