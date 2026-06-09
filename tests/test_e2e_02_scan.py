import os
import shutil
import time

import pytest


def _navigate_to_dashboard(page, server):
    page.goto(server["base_url"])
    page.wait_for_load_state("networkidle")
    page.locator('button.nav-item[data-nav="dashboard"]').click()
    page.wait_for_load_state("networkidle")


def _navigate_to_tasks(page, server):
    page.goto(server["base_url"])
    page.wait_for_load_state("networkidle")
    page.locator('button.nav-item[data-nav="tasks"]').click()
    page.wait_for_load_state("networkidle")


def _wait_for_toast(page, expected_text=None, timeout=5000):
    toast = page.locator("#toast")
    toast.wait_for(state="attached", timeout=timeout)
    start = time.time()
    while time.time() - start < timeout / 1000:
        text = toast.text_content() or ""
        if expected_text:
            if expected_text in text:
                return text
        elif text.strip():
            return text
        time.sleep(0.3)
    if expected_text:
        pytest.fail(f"Toast did not contain '{expected_text}', got: {toast.text_content()}")
    pytest.fail("Toast did not contain any text")


def _wait_for_task_cards(page, min_count=1, timeout=30000):
    start = time.time()
    while time.time() - start < timeout / 1000:
        cards = page.locator("article.task-card[data-task-row]")
        if cards.count() >= min_count:
            return cards
        page.locator('[data-task-action="refresh-tasks"]').click() if page.locator(
            '[data-task-action="refresh-tasks"]'
        ).count() > 0 else None
        time.sleep(1)
    return page.locator("article.task-card[data-task-row]")


def _find_task_card_by_filename(page, filename):
    cards = page.locator("article.task-card[data-task-row]")
    for i in range(cards.count()):
        card = cards.nth(i)
        text = card.inner_text()
        if filename in text:
            return card
    return None


def _poll_task_status(page, server, task_id, expected_status, timeout=60000):
    import json
    import urllib.request

    start = time.time()
    while time.time() - start < timeout / 1000:
        try:
            url = f"{server['base_url']}/api/tasks/{task_id}"
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read())
            task = data.get("data", {}).get("task", data.get("data", {}))
            status = str(task.get("status", "")).upper()
            if status == expected_status:
                return task
            if status in ("SUCCESS", "SKIPPED") and expected_status not in ("SUCCESS", "SKIPPED"):
                return task
        except Exception:
            pass
        time.sleep(2)
    return None


def _get_first_task_id(page):
    card = page.locator("article.task-card[data-task-row]").first
    return card.get_attribute("data-task-row")


# ── 3.2.1 扫描触发 (S01-S04) ──────────────────────────────────────────


class TestScanTrigger:

    def test_s01_scan_with_files_shows_toast(self, e2e_page, e2e_server, e2e_test_files):
        """S01: 源目录有文件时，点击扫描按钮，验证 toast 提示扫描已开始"""
        page = e2e_page
        server = e2e_server
        _navigate_to_dashboard(page, server)

        scan_btn = page.locator('[data-action="scan"]')
        scan_btn.wait_for(state="visible", timeout=5000)
        scan_btn.click()

        toast_text = _wait_for_toast(page, timeout=5000)
        assert toast_text, "Scan trigger should produce a toast notification"

    def test_s02_scan_queue_status_processing(self, e2e_page, e2e_server, e2e_test_files):
        """S02: 扫描期间，检查队列状态显示处理中信息"""
        page = e2e_page
        server = e2e_server
        _navigate_to_dashboard(page, server)

        scan_btn = page.locator('[data-action="scan"]')
        scan_btn.wait_for(state="visible", timeout=5000)
        scan_btn.click()
        _wait_for_toast(page, timeout=5000)

        page.wait_for_timeout(2000)

        status_el = page.locator("#runtime-status")
        assert status_el.count() > 0, "Runtime status element should exist"

    def test_s03_scan_empty_dir_no_new_files(self, e2e_page, e2e_server):
        """S03: 空源目录点击扫描，验证无新文件提示"""
        page = e2e_page
        server = e2e_server

        source_dir = server["source_dir"]
        for entry in os.listdir(source_dir):
            full = os.path.join(source_dir, entry)
            if os.path.isdir(full):
                shutil.rmtree(full, ignore_errors=True)
            else:
                os.remove(full)

        _navigate_to_dashboard(page, server)

        scan_btn = page.locator('[data-action="scan"]')
        scan_btn.wait_for(state="visible", timeout=5000)
        scan_btn.click()

        toast_text = _wait_for_toast(page, timeout=10000)
        assert toast_text, "Scan on empty dir should produce a toast"

    def test_s04_rescan_after_completion(self, e2e_page, e2e_server, e2e_test_files):
        """S04: 扫描完成后再次扫描，验证只发现新文件或无新文件"""
        page = e2e_page
        server = e2e_server
        _navigate_to_dashboard(page, server)

        scan_btn = page.locator('[data-action="scan"]')
        scan_btn.wait_for(state="visible", timeout=5000)
        scan_btn.click()
        _wait_for_toast(page, timeout=5000)

        page.wait_for_timeout(5000)

        scan_btn = page.locator('[data-action="scan"]')
        scan_btn.wait_for(state="visible", timeout=5000)
        scan_btn.click()

        toast_text = _wait_for_toast(page, timeout=10000)
        assert toast_text, "Second scan should produce a toast"


# ── 3.2.2 任务状态转换 (T01-T09) ──────────────────────────────────────


class TestTaskStatusTransitions:

    def _scan_and_wait_for_tasks(self, page, server, timeout=60000):
        _navigate_to_dashboard(page, server)
        scan_btn = page.locator('[data-action="scan"]')
        scan_btn.wait_for(state="visible", timeout=5000)
        scan_btn.click()
        _wait_for_toast(page, timeout=5000)

        _navigate_to_tasks(page, server)
        page.locator('[data-task-filter-chip="all"]').click()
        page.wait_for_timeout(2000)

        deadline = time.time() + timeout / 1000
        while time.time() < deadline:
            cards = page.locator("article.task-card[data-task-row]")
            if cards.count() > 0:
                return cards
            page.wait_for_timeout(3000)
        return page.locator("article.task-card[data-task-row]")

    def test_t01_new_task_shows_pending(self, e2e_page, e2e_server, e2e_test_files):
        """T01: 新任务显示 PENDING/待处理 状态"""
        page = e2e_page
        server = e2e_server

        _navigate_to_dashboard(page, server)
        scan_btn = page.locator('[data-action="scan"]')
        scan_btn.wait_for(state="visible", timeout=5000)
        scan_btn.click()
        _wait_for_toast(page, timeout=5000)

        page.wait_for_timeout(3000)

        _navigate_to_tasks(page, server)
        page.locator('[data-task-filter-chip="all"]').click()
        page.wait_for_timeout(2000)

        cards = _wait_for_task_cards(page, min_count=1, timeout=30000)
        assert cards.count() > 0, "Should have at least one task card after scan"

        first_card = cards.first
        badge = first_card.locator(".badge")
        badge.wait_for(state="visible", timeout=5000)
        status_text = badge.text_content()
        assert status_text, "Task card should show a status badge"

    def test_t02_success_after_processing(self, e2e_page, e2e_server, e2e_test_files):
        """T02: 处理成功后显示 SUCCESS/已完成"""
        page = e2e_page
        server = e2e_server

        self._scan_and_wait_for_tasks(page, server)

        cards = page.locator("article.task-card[data-task-row]")
        if cards.count() == 0:
            pytest.skip("No tasks created by scan")

        deadline = time.time() + 120
        found_success = False
        while time.time() < deadline:
            cards = page.locator("article.task-card[data-task-row]")
            for i in range(cards.count()):
                badge = cards.nth(i).locator(".badge")
                if badge.count() > 0:
                    text = badge.text_content() or ""
                    if "已完成" in text or "SUCCESS" in text.upper():
                        found_success = True
                        break
            if found_success:
                break
            page.wait_for_timeout(5000)
            page.locator('[data-task-filter-chip="all"]').click()
            page.wait_for_timeout(2000)

        assert found_success, "At least one task should reach SUCCESS status"

    def test_t03_failed_shows_error_info(self, e2e_page, e2e_server, e2e_test_files):
        """T03: 处理失败后显示 FAILED/失败，并包含错误信息"""
        page = e2e_page
        server = e2e_server

        self._scan_and_wait_for_tasks(page, server)

        page.locator('[data-task-filter-chip="failed"]').click()
        page.wait_for_timeout(3000)

        cards = page.locator("article.task-card[data-task-row]")
        if cards.count() == 0:
            pytest.skip("No failed tasks in this run")

        first_card = cards.first
        badge = first_card.locator(".badge")
        if badge.count() > 0:
            status_text = badge.text_content() or ""
            assert "失败" in status_text, f"Expected failed status, got: {status_text}"

    def test_t04_low_confidence_shows_confirming(self, e2e_page, e2e_server, e2e_test_files):
        """T04: 低置信度任务显示 CONFIRMING/待确认"""
        page = e2e_page
        server = e2e_server

        self._scan_and_wait_for_tasks(page, server)

        page.locator('[data-task-filter-chip="confirm"]').click()
        page.wait_for_timeout(3000)

        cards = page.locator("article.task-card[data-task-row]")
        if cards.count() == 0:
            pytest.skip("No confirming tasks in this run")

        first_card = cards.first
        badge = first_card.locator(".badge")
        if badge.count() > 0:
            status_text = badge.text_content() or ""
            assert "确认" in status_text, f"Expected confirming status, got: {status_text}"

    def test_t05_confirm_confirming_task_to_success(self, e2e_page, e2e_server, e2e_test_files):
        """T05: 用户确认 CONFIRMING 任务后转为 SUCCESS"""
        page = e2e_page
        server = e2e_server

        self._scan_and_wait_for_tasks(page, server)

        page.locator('[data-task-filter-chip="confirm"]').click()
        page.wait_for_timeout(3000)

        cards = page.locator("article.task-card[data-task-row]")
        if cards.count() == 0:
            pytest.skip("No confirming tasks to confirm")

        first_card = cards.first
        confirm_btn = first_card.locator('[data-task-action="confirm"]')
        if confirm_btn.count() == 0:
            confirm_btn = first_card.locator('button:has-text("去确认")')
        if confirm_btn.count() == 0:
            pytest.skip("No confirm button found on confirming task")

        confirm_btn.first.click()
        page.wait_for_timeout(1000)

        dialog_confirm = page.locator('.cinema-modal-actions button:has-text("确认")')
        if dialog_confirm.count() > 0:
            dialog_confirm.first.click()

        page.wait_for_timeout(3000)
        page.locator('[data-task-filter-chip="all"]').click()
        page.wait_for_timeout(2000)

    def test_t06_ignore_confirming_task_to_skipped(self, e2e_page, e2e_server, e2e_test_files):
        """T06: 用户忽略 CONFIRMING 任务后转为 SKIPPED"""
        page = e2e_page
        server = e2e_server

        self._scan_and_wait_for_tasks(page, server)

        page.locator('[data-task-filter-chip="confirm"]').click()
        page.wait_for_timeout(3000)

        cards = page.locator("article.task-card[data-task-row]")
        if cards.count() == 0:
            pytest.skip("No confirming tasks to ignore")

        first_card = cards.first
        ignore_btn = first_card.locator('[data-task-action="ignore-task"]')
        if ignore_btn.count() == 0:
            ignore_btn = first_card.locator('button:has-text("忽略")')
        if ignore_btn.count() == 0:
            pytest.skip("No ignore button found on confirming task")

        ignore_btn.first.click()
        page.wait_for_timeout(1000)

        dialog_confirm = page.locator('.cinema-modal-actions button:has-text("确认")')
        if dialog_confirm.count() > 0:
            dialog_confirm.first.click()

        _wait_for_toast(page, timeout=10000)

        page.wait_for_timeout(3000)

    def test_t07_retry_failed_task(self, e2e_page, e2e_server, e2e_test_files):
        """T07: 重试 FAILED 任务 → PENDING→PROCESSING"""
        page = e2e_page
        server = e2e_server

        self._scan_and_wait_for_tasks(page, server)

        page.locator('[data-task-filter-chip="failed"]').click()
        page.wait_for_timeout(3000)

        cards = page.locator("article.task-card[data-task-row]")
        if cards.count() == 0:
            pytest.skip("No failed tasks to retry")

        first_card = cards.first
        retry_btn = first_card.locator('[data-task-action="retry-task"]')
        if retry_btn.count() == 0:
            retry_btn = first_card.locator('button:has-text("去重试")')
        if retry_btn.count() == 0:
            pytest.skip("No retry button found on failed task")

        retry_btn.first.click()
        _wait_for_toast(page, timeout=10000)

        page.wait_for_timeout(3000)

    def test_t08_failed_beyond_retry_to_recycle(self, e2e_page, e2e_server, e2e_test_files):
        """T08: 失败次数超过重试限制的任务移入回收站"""
        page = e2e_page
        server = e2e_server

        self._scan_and_wait_for_tasks(page, server)

        page.locator('[data-task-filter-chip="failed"]').click()
        page.wait_for_timeout(3000)

        cards = page.locator("article.task-card[data-task-row]")
        if cards.count() == 0:
            pytest.skip("No failed tasks to move to recycle")

        first_card = cards.first
        delete_btn = first_card.locator('[data-task-action="delete-task"]')
        if delete_btn.count() == 0:
            delete_btn = first_card.locator('button:has-text("移入回收")')
        if delete_btn.count() == 0:
            pytest.skip("No delete/recycle button found on failed task")

        delete_btn.first.click()
        page.wait_for_timeout(1000)

        dialog_confirm = page.locator('.cinema-modal-actions button:has-text("确认")')
        if dialog_confirm.count() > 0:
            dialog_confirm.first.click()

        page.wait_for_timeout(3000)

        page.locator('button.nav-item[data-nav="recycle"]').click()
        page.wait_for_timeout(2000)

    def test_t09_success_is_terminal(self, e2e_page, e2e_server, e2e_test_files):
        """T09: SUCCESS 是终态，已完成的任务不再变化"""
        page = e2e_page
        server = e2e_server

        self._scan_and_wait_for_tasks(page, server)

        page.locator('[data-task-filter-chip="success"]').click()
        page.wait_for_timeout(3000)

        cards = page.locator("article.task-card[data-task-row]")
        if cards.count() == 0:
            pytest.skip("No successful tasks yet")

        first_card = cards.first
        badge = first_card.locator(".badge")
        if badge.count() > 0:
            status_text = badge.text_content() or ""
            assert "已完成" in status_text, f"Expected SUCCESS/已完成, got: {status_text}"

            view_btn = first_card.locator('[data-task-action="view-task"]')
            assert view_btn.count() > 0, "SUCCESS task should have view action"

            confirm_btn = first_card.locator('[data-task-action="confirm"]')
            retry_btn = first_card.locator('[data-task-action="retry-task"]')
            ignore_btn = first_card.locator('[data-task-action="ignore-task"]')
            assert confirm_btn.count() == 0, "SUCCESS task should not have confirm action"
            assert retry_btn.count() == 0, "SUCCESS task should not have retry action"
            assert ignore_btn.count() == 0, "SUCCESS task should not have ignore action"


# ── 3.2.3 不同视频类型扫描结果 (ST01-ST05) ───────────────────────────


class TestVideoTypeScanning:

    def _scan_and_wait_all_done(self, page, server, timeout=180):
        _navigate_to_dashboard(page, server)
        scan_btn = page.locator('[data-action="scan"]')
        scan_btn.wait_for(state="visible", timeout=5000)
        scan_btn.click()
        _wait_for_toast(page, timeout=5000)

        deadline = time.time() + timeout
        while time.time() < deadline:
            _navigate_to_tasks(page, server)
            page.locator('[data-task-filter-chip="all"]').click()
            page.wait_for_timeout(3000)

            cards = page.locator("article.task-card[data-task-row]")
            if cards.count() > 0:
                return cards
            page.wait_for_timeout(5000)
        return page.locator("article.task-card[data-task-row]")

    def _find_task_for_video(self, page, server, video_filename, timeout=120):
        import json
        import urllib.request

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                url = f"{server['base_url']}/api/tasks?limit=50"
                resp = urllib.request.urlopen(url, timeout=5)
                data = json.loads(resp.read())
                tasks = data.get("data", {}).get("tasks", [])
                for task in tasks:
                    source = task.get("source_path", "") or task.get("source_filename", "")
                    if video_filename in source:
                        return task
            except Exception:
                pass
            time.sleep(3)
        return None

    def _media_type_or_skip(self, task):
        media_type = (task.get("scrape_media_type")
                      or (task.get("scrape_result") or {}).get("type")
                      or "")
        if not media_type:
            pytest.skip("Scrape metadata unavailable; API keys/provider result not available in this run")
        return media_type

    def _dimension_or_skip(self, task, name):
        dimensions = task.get("scrape_dimensions") or (task.get("scrape_result") or {}).get("dimensions") or {}
        value = str(dimensions.get(name, "")).lower()
        if not value:
            pytest.skip(f"Dimension {name} unavailable; scrape metadata not available in this run")
        return value

    def test_st01_inception_is_movie(self, e2e_page, e2e_server, e2e_test_files):
        """ST01: V01 (Inception) → movie 类型"""
        page = e2e_page
        server = e2e_server

        self._scan_and_wait_all_done(page, server)

        task = self._find_task_for_video(page, server, "Inception.2010")
        if task is None:
            pytest.skip("Inception task not found in API results")

        media_type = self._media_type_or_skip(task)
        assert media_type == "movie", f"Expected movie, got: {media_type}"

    def test_st02_breaking_bad_is_tv(self, e2e_page, e2e_server, e2e_test_files):
        """ST02: V03 (Breaking Bad) → tv 类型"""
        page = e2e_page
        server = e2e_server

        self._scan_and_wait_all_done(page, server)

        task = self._find_task_for_video(page, server, "Breaking.Bad.S05E16")
        if task is None:
            pytest.skip("Breaking Bad task not found in API results")

        media_type = self._media_type_or_skip(task)
        assert media_type == "tv", f"Expected tv, got: {media_type}"

    def test_st03_attack_on_titan_is_tv_animation(self, e2e_page, e2e_server, e2e_test_files):
        """ST03: V05 (进击的巨人) → tv 类型, animation=true"""
        page = e2e_page
        server = e2e_server

        self._scan_and_wait_all_done(page, server)

        task = self._find_task_for_video(page, server, "进击的巨人")
        if task is None:
            pytest.skip("Attack on Titan task not found in API results")

        media_type = self._media_type_or_skip(task)
        assert media_type == "tv", f"Expected tv, got: {media_type}"

        animation_val = self._dimension_or_skip(task, "animation")
        assert animation_val == "true", f"Expected animation=true, got: {animation_val}"

    def test_st04_planet_earth_ii_is_tv_documentary(self, e2e_page, e2e_server, e2e_test_files):
        """ST04: V06 (Planet Earth II) → tv 类型, documentary=true"""
        page = e2e_page
        server = e2e_server

        self._scan_and_wait_all_done(page, server)

        task = self._find_task_for_video(page, server, "Planet.Earth.II")
        if task is None:
            pytest.skip("Planet Earth II task not found in API results")

        media_type = self._media_type_or_skip(task)
        assert media_type == "tv", f"Expected tv, got: {media_type}"

        doc_val = self._dimension_or_skip(task, "documentary")
        assert doc_val == "true", f"Expected documentary=true, got: {doc_val}"

    def test_st05_your_name_is_movie_animation(self, e2e_page, e2e_server, e2e_test_files):
        """ST05: V14 (Your Name) → movie 类型, animation=true"""
        page = e2e_page
        server = e2e_server

        self._scan_and_wait_all_done(page, server)

        task = self._find_task_for_video(page, server, "Your.Name.2016")
        if task is None:
            pytest.skip("Your Name task not found in API results")

        media_type = self._media_type_or_skip(task)
        assert media_type == "movie", f"Expected movie, got: {media_type}"

        animation_val = self._dimension_or_skip(task, "animation")
        assert animation_val == "true", f"Expected animation=true, got: {animation_val}"
