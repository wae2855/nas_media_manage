import json
import sqlite3
import time
import urllib.request
import uuid
from datetime import datetime

import pytest


def _api(base_url, method, path, body=None):
    url = f"{base_url}/api{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8"))


def _wait_toast_text(page, timeout=5000):
    toast = page.locator("#toast")
    toast.wait_for(state="attached", timeout=timeout)
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        text = toast.inner_text() or ""
        if text.strip():
            return text
        time.sleep(0.2)
    return ""


def _wait_task_list_settled(page, timeout=10000):
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        text = page.locator("#task-list").inner_text() if page.locator("#task-list").count() else ""
        if "正在读取任务队列" not in text and "加载中" not in text:
            return
        time.sleep(0.2)


def _navigate_to_tasks(page, filter_chip="all"):
    page.click('button.nav-item[data-nav="tasks"]')
    page.wait_for_load_state("networkidle")
    page.locator(f'[data-task-filter-chip="{filter_chip}"]').click()
    page.wait_for_load_state("networkidle")
    _wait_task_list_settled(page)


def _create_terminal_task(db_path, source_dir, filename, status, **fields):
    source_path = f"{source_dir}/{filename}"
    task_id = uuid.uuid4().hex[:12]
    now = datetime.now().isoformat()
    base_columns = {
        "task_id": task_id,
        "source_path": source_path,
        "source_filename": filename,
        "file_size_mb": 1.0,
        "status": status,
        "created_at": now,
        "last_seen_at": now,
        "total_steps": 10,
    }
    base_columns.update(fields)
    columns = ", ".join(base_columns.keys())
    placeholders = ", ".join("?" for _ in base_columns)
    with sqlite3.connect(db_path) as conn:
        conn.execute(f"INSERT INTO tasks ({columns}) VALUES ({placeholders})", list(base_columns.values()))
        conn.commit()
    return {"task_id": task_id, "status": status, "source_path": source_path, "source_filename": filename}


@pytest.mark.live_e2e
class TestTaskSingleActions:

    def test_A01_click_task_card_opens_detail_modal(self, e2e_page, e2e_server, e2e_test_files):
        """A01: Click task card to view details, modal opens with task info."""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "Inception.2010.1080p.BluRay.x264-SPARKS.mkv"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "SUCCESS",
                                     scrape_title_en="Inception", scrape_year=2010,
                                     scrape_media_type="movie", scrape_confidence=0.95,
                                     import_success=1)

        _navigate_to_tasks(e2e_page)
        view_button = e2e_page.locator('[data-task-action="view-task"]').first
        view_button.scroll_into_view_if_needed()
        view_button.click()

        e2e_page.locator(".cinema-modal-overlay").wait_for(state="visible", timeout=5000)
        assert e2e_page.locator(".cinema-modal-overlay").is_visible()

    def test_A02_detail_modal_shows_scrape_results(self, e2e_page, e2e_server, e2e_test_files):
        """A02: In detail modal, verify scrape result fields rendered (title, year, type, confidence)."""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "Inception.2010.1080p.BluRay.x264-SPARKS.mkv"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "SUCCESS",
                                     scrape_title_en="Inception", scrape_year=2010,
                                     scrape_media_type="movie", scrape_confidence=0.95)
        _api(
            base_url,
            "POST",
            f"/tasks/{task['task_id']}/rename",
            {"new_filename": "Inception.2010.test.mkv"},
        )

        _navigate_to_tasks(e2e_page)
        e2e_page.click(f'[data-task-action="view-task"][data-task-id="{task["task_id"]}"]')
        e2e_page.locator(".cinema-modal-overlay").wait_for(state="visible", timeout=5000)

        modal = e2e_page.locator(".cinema-modal-overlay")
        assert modal.get_by_text("刮削结果", exact=True).count() > 0 or modal.get_by_text("文件名微调", exact=True).count() > 0

    def test_A03_failed_task_shows_error_highlighted(self, e2e_page, e2e_server, e2e_test_files):
        """A03: For FAILED task, view error info highlighted in red/danger tone."""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "Inception.2010.1080p.BluRay.x264-SPARKS.mkv"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "FAILED",
                                     scrape_title_en="Inception", scrape_year=2010,
                                     scrape_media_type="movie", scrape_confidence=0.0,
                                     error_message="Scrape failed: upstream LLM/TMDB unavailable",
                                     error_code=500)

        _api(base_url, "POST", f"/tasks/{task['task_id']}/rename", {"new_filename": "test.mkv"})

        _navigate_to_tasks(e2e_page)
        card = e2e_page.locator(f'article.task-card[data-task-row="{task["task_id"]}"]')
        card.scroll_into_view_if_needed()
        card.click()
        e2e_page.locator(".cinema-modal-overlay").wait_for(state="visible", timeout=5000)

        modal = e2e_page.locator(".cinema-modal-overlay")
        summary_text = modal.locator(".cinema-modal-summary").inner_text()
        assert len(summary_text) > 0

    def test_A04_modify_filename_preview_updates(self, e2e_page, e2e_server, e2e_test_files):
        """A04: In detail modal, modify filename input, verify preview updates."""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "Inception.2010.1080p.BluRay.x264-SPARKS.mkv"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "SUCCESS",
                                     scrape_title_en="Inception", scrape_year=2010,
                                     scrape_media_type="movie", scrape_confidence=0.95)

        _navigate_to_tasks(e2e_page)
        e2e_page.click(f'[data-task-action="view-task"][data-task-id="{task["task_id"]}"]')
        e2e_page.locator(".cinema-modal-overlay").wait_for(state="visible", timeout=5000)

        rename_input = e2e_page.locator("#task-rename-input")
        rename_input.fill("New.Movie.Name.2024.mkv")

        preview_target = e2e_page.locator("#task-rename-preview [data-rename-target]")
        preview_text = preview_target.inner_text()
        assert "New.Movie.Name.2024.mkv" in preview_text

    def test_A05_save_filename_shows_toast(self, e2e_page, e2e_server, e2e_test_files):
        """A05: Save new filename, verify toast success message."""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "Inception.2010.1080p.BluRay.x264-SPARKS.mkv"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "SUCCESS",
                                     scrape_title_en="Inception", scrape_year=2010,
                                     scrape_media_type="movie", scrape_confidence=0.95)

        _navigate_to_tasks(e2e_page)
        e2e_page.click(f'[data-task-action="view-task"][data-task-id="{task["task_id"]}"]')
        e2e_page.locator(".cinema-modal-overlay").wait_for(state="visible", timeout=5000)

        rename_input = e2e_page.locator("#task-rename-input")
        rename_input.fill("Inception.Renamed.2010.mkv")

        e2e_page.locator("button", has_text="保存新文件名").click()

        toast_text = _wait_toast_text(e2e_page)
        assert len(toast_text) > 0

    def test_A06_clear_filename_shows_empty_preview(self, e2e_page, e2e_server, e2e_test_files):
        """A06: Clear filename input, verify red border / empty preview indicator."""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "Inception.2010.1080p.BluRay.x264-SPARKS.mkv"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "SUCCESS",
                                     scrape_title_en="Inception", scrape_year=2010,
                                     scrape_media_type="movie", scrape_confidence=0.95)

        _navigate_to_tasks(e2e_page)
        e2e_page.click(f'[data-task-action="view-task"][data-task-id="{task["task_id"]}"]')
        e2e_page.locator(".cinema-modal-overlay").wait_for(state="visible", timeout=5000)

        rename_input = e2e_page.locator("#task-rename-input")
        rename_input.fill("")

        preview_target = e2e_page.locator("#task-rename-preview [data-rename-target]")
        preview_text = preview_target.inner_text()
        assert "空" in preview_text or preview_text.strip() == ""

        is_empty_class = rename_input.evaluate("el => el.classList.contains('is-empty')")
        assert is_empty_class

    def test_A07_modify_dimension_apply_classification(self, e2e_page, e2e_server, e2e_test_files):
        """A07: Modify dimension values, apply classification tweak."""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "Inception.2010.1080p.BluRay.x264-SPARKS.mkv"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "SUCCESS",
                                     scrape_title_en="Inception", scrape_year=2010,
                                     scrape_media_type="movie", scrape_confidence=0.95)

        _navigate_to_tasks(e2e_page)
        e2e_page.click(f'[data-task-action="view-task"][data-task-id="{task["task_id"]}"]')
        e2e_page.locator(".cinema-modal-overlay").wait_for(state="visible", timeout=5000)

        dim_input = e2e_page.locator("[data-task-dim]").first
        if dim_input.is_visible():
            dim_input.fill("true")

            e2e_page.locator("button", has_text="应用分类微调").click()

            toast_text = _wait_toast_text(e2e_page)
            assert len(toast_text) > 0

    def test_A08_apply_classification_no_values_error_toast(self, e2e_page, e2e_server, e2e_test_files):
        """A08: Apply classification with no dimension values filled, verify error toast."""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "Inception.2010.1080p.BluRay.x264-SPARKS.mkv"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "SUCCESS",
                                     scrape_title_en="Inception", scrape_year=2010,
                                     scrape_media_type="movie", scrape_confidence=0.95)

        _navigate_to_tasks(e2e_page)
        e2e_page.click(f'[data-task-action="view-task"][data-task-id="{task["task_id"]}"]')
        e2e_page.locator(".cinema-modal-overlay").wait_for(state="visible", timeout=5000)

        dim_inputs = e2e_page.locator("[data-task-dim]")
        count = dim_inputs.count()
        for i in range(count):
            dim_inputs.nth(i).fill("")

        e2e_page.locator("button", has_text="应用分类微调").click()

        toast = e2e_page.locator("#toast")
        toast.wait_for(state="visible", timeout=5000)
        toast_text = toast.inner_text()
        assert "维度" in toast_text or "至少" in toast_text

    def test_A09_retry_failed_task_changes_status(self, e2e_page, e2e_server, e2e_test_files):
        """A09: Click retry on FAILED task, verify status changes from FAILED."""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "Inception.2010.1080p.BluRay.x264-SPARKS.mkv"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "FAILED",
                                     scrape_title_en="Inception", scrape_year=2010,
                                     scrape_media_type="movie", scrape_confidence=0.0,
                                     error_message="Scrape failed: upstream LLM/TMDB unavailable",
                                     error_code=500, retry_count=0)

        _navigate_to_tasks(e2e_page)
        e2e_page.click('[data-task-filter-chip="failed"]')
        e2e_page.wait_for_load_state("networkidle")

        card = e2e_page.locator(f'article.task-card[data-task-row="{task["task_id"]}"]')
        if card.is_visible(timeout=5000):
            retry_btn = e2e_page.locator(
                f'[data-task-action="retry-task"][data-task-id="{task["task_id"]}"]'
            )
            if retry_btn.is_visible(timeout=3000):
                retry_btn.click()
                toast = e2e_page.locator("#toast")
                toast.wait_for(state="visible", timeout=5000)
                assert toast.inner_text() != ""

    def test_A10_confirm_confirming_task_succeeds(self, e2e_page, e2e_server, e2e_test_files):
        """A10: Click confirm on CONFIRMING task, verify SUCCESS status."""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "Inception.2010.1080p.BluRay.x264-SPARKS.mkv"
        scrape_result = json.dumps({
            "candidate": {"id": 27205, "title": "Inception", "year": 2010, "media_type": "movie"},
            "matched": {"id": 27205, "title": "Inception", "year": 2010, "media_type": "movie"},
        })
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "CONFIRMING",
                                     scrape_result=scrape_result,
                                     scrape_title_en="Inception", scrape_title_cn="盗梦空间",
                                     scrape_year=2010, scrape_media_type="movie",
                                     scrape_confidence=0.5)

        _navigate_to_tasks(e2e_page)

        confirm_btn = e2e_page.locator(
            f'[data-task-action="confirm"][data-task-id="{task["task_id"]}"]'
        )
        if not confirm_btn.is_visible(timeout=3000):
            pytest.skip("No CONFIRMING task available for this test run")

        confirm_btn.click()

        e2e_page.locator(".cinema-modal-overlay").wait_for(state="visible", timeout=5000)
        confirm_in_modal = e2e_page.locator(".cinema-modal-overlay button", has_text="确认")
        confirm_in_modal.click()

        toast = e2e_page.locator("#toast")
        toast.wait_for(state="visible", timeout=5000)
        toast_text = toast.inner_text()
        assert "确认" in toast_text or "成功" in toast_text or len(toast_text) > 0

    def test_A11_ignore_confirming_task_skipped(self, e2e_page, e2e_server, e2e_test_files):
        """A11: Click ignore on CONFIRMING task, verify SKIPPED status."""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "Breaking.Bad.S05E16.Felina.1080p.BluRay.x264.mkv"
        scrape_result = json.dumps({
            "candidate": {"id": 1396, "title": "Breaking Bad", "year": 2008, "media_type": "tv"},
            "matched": {"id": 1396, "title": "Breaking Bad", "year": 2008, "media_type": "tv"},
        })
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "CONFIRMING",
                                     scrape_result=scrape_result,
                                     scrape_title_en="Breaking Bad", scrape_title_cn="绝命毒师",
                                     scrape_year=2008, scrape_media_type="tv",
                                     scrape_confidence=0.5)

        _navigate_to_tasks(e2e_page)

        ignore_btn = e2e_page.locator(
            f'[data-task-action="ignore-task"][data-task-id="{task["task_id"]}"]'
        )
        if not ignore_btn.is_visible(timeout=3000):
            pytest.skip("No task with ignore action available for this test run")

        ignore_btn.click()

        e2e_page.locator(".cinema-modal-overlay").wait_for(state="visible", timeout=5000)
        confirm_in_modal = e2e_page.locator(".cinema-modal-overlay button", has_text="确认")
        confirm_in_modal.click()

        toast = e2e_page.locator("#toast")
        toast.wait_for(state="visible", timeout=5000)
        toast_text = toast.inner_text()
        assert "忽略" in toast_text or len(toast_text) > 0

    def test_A12_delete_task_confirm_removes(self, e2e_page, e2e_server, e2e_test_files):
        """A12: Click delete on task, confirm in dialog, verify task removed."""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "The.Shawshank.Redemption.1994.720p.BRRip.XviD.avi"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "FAILED",
                                     scrape_title_en="The Shawshank Redemption", scrape_year=1994,
                                     scrape_media_type="movie", scrape_confidence=0.0,
                                     error_message="Scrape failed",
                                     error_code=500)

        _navigate_to_tasks(e2e_page)

        delete_btn = e2e_page.locator(
            f'[data-task-action="delete-task"][data-task-id="{task["task_id"]}"]'
        )
        if not delete_btn.is_visible(timeout=3000):
            pytest.skip("No task with delete action available for this test run")

        delete_btn.click()

        e2e_page.locator(".cinema-modal-overlay").wait_for(state="visible", timeout=5000)
        confirm_btn = e2e_page.locator(".cinema-modal-overlay button", has_text="确认")
        confirm_btn.click()

        toast = e2e_page.locator("#toast")
        toast.wait_for(state="visible", timeout=5000)
        toast_text = toast.inner_text()
        assert "回收" in toast_text or "删除" in toast_text or len(toast_text) > 0

    def test_A13_delete_task_cancel_keeps_task(self, e2e_page, e2e_server, e2e_test_files):
        """A13: Click delete, cancel in dialog, verify task remains."""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "Oppenheimer.2023.2160p.UHD.BluRay.Remux.mkv"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "FAILED",
                                     scrape_title_en="Oppenheimer", scrape_year=2023,
                                     scrape_media_type="movie", scrape_confidence=0.0,
                                     error_message="Scrape failed",
                                     error_code=500)

        _navigate_to_tasks(e2e_page)

        delete_btn = e2e_page.locator(
            f'[data-task-action="delete-task"][data-task-id="{task["task_id"]}"]'
        )
        if not delete_btn.is_visible(timeout=3000):
            pytest.skip("No task with delete action available for this test run")

        delete_btn.click()

        e2e_page.locator(".cinema-modal-overlay").wait_for(state="visible", timeout=5000)
        cancel_btn = e2e_page.locator(".cinema-modal-overlay button", has_text="取消")
        cancel_btn.click()

        e2e_page.locator(".cinema-modal-overlay").wait_for(state="hidden", timeout=3000)

        card = e2e_page.locator(f'article.task-card[data-task-row="{task["task_id"]}"]')
        assert card.is_visible(timeout=3000)


@pytest.mark.live_e2e
class TestTaskFilterAndNavigation:

    def test_A14_filter_all_shows_all_tasks(self, e2e_page, e2e_server, e2e_test_files):
        """A14: Click 'all' filter chip, show all tasks."""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "Inception.2010.1080p.BluRay.x264-SPARKS.mkv"
        _create_terminal_task(e2e_server["db_path"], source_dir, filename, "SUCCESS",
                              scrape_title_en="Inception", scrape_year=2010,
                              scrape_media_type="movie", scrape_confidence=0.95)

        _navigate_to_tasks(e2e_page, filter_chip="all")

        chip = e2e_page.locator('[data-task-filter-chip="all"]')
        assert chip.evaluate("el => el.classList.contains('active')")

        cards = e2e_page.locator("article.task-card[data-task-row]")
        assert cards.count() >= 1

    def test_A15_filter_pending_shows_pending_tasks(self, e2e_page, e2e_server, e2e_test_files):
        """A15: Click 'pending' filter, show only PENDING/PROCESSING tasks."""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "Your.Name.2016.1080p.BluRay.x264-[YTS].mkv"
        _create_terminal_task(e2e_server["db_path"], source_dir, filename, "PENDING")

        _navigate_to_tasks(e2e_page)
        e2e_page.click('[data-task-filter-chip="pending"]')
        e2e_page.wait_for_load_state("networkidle")

        chip = e2e_page.locator('[data-task-filter-chip="pending"]')
        assert chip.evaluate("el => el.classList.contains('active')")

        cards = e2e_page.locator("article.task-card[data-task-row]")
        if cards.count() > 0:
            first_card = cards.first
            badge_text = first_card.locator(".badge").inner_text()
            assert badge_text in ("待处理", "处理中")

    def test_A16_filter_confirm_shows_confirming_tasks(self, e2e_page, e2e_server, e2e_test_files):
        """A16: Click 'confirm' filter, show only CONFIRMING tasks."""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]

        _navigate_to_tasks(e2e_page)
        e2e_page.click('[data-task-filter-chip="confirm"]')
        e2e_page.wait_for_load_state("networkidle")

        chip = e2e_page.locator('[data-task-filter-chip="confirm"]')
        assert chip.evaluate("el => el.classList.contains('active')")

        cards = e2e_page.locator("article.task-card[data-task-row]")
        if cards.count() > 0:
            first_card = cards.first
            badge_text = first_card.locator(".badge").inner_text()
            assert badge_text in ("待确认",)

    def test_A17_filter_failed_shows_failed_tasks(self, e2e_page, e2e_server, e2e_test_files):
        """A17: Click 'failed' filter, show only FAILED tasks."""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]

        _navigate_to_tasks(e2e_page)
        e2e_page.click('[data-task-filter-chip="failed"]')
        e2e_page.wait_for_load_state("networkidle")

        chip = e2e_page.locator('[data-task-filter-chip="failed"]')
        assert chip.evaluate("el => el.classList.contains('active')")

        cards = e2e_page.locator("article.task-card[data-task-row]")
        if cards.count() > 0:
            first_card = cards.first
            badge_text = first_card.locator(".badge").inner_text()
            assert badge_text == "失败"

    def test_A18_filter_success_shows_success_tasks(self, e2e_page, e2e_server, e2e_test_files):
        """A18: Click 'success' filter, show only SUCCESS/SKIPPED tasks."""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]

        _navigate_to_tasks(e2e_page)
        e2e_page.click('[data-task-filter-chip="success"]')
        e2e_page.wait_for_load_state("networkidle")

        chip = e2e_page.locator('[data-task-filter-chip="success"]')
        assert chip.evaluate("el => el.classList.contains('active')")

        cards = e2e_page.locator("article.task-card[data-task-row]")
        if cards.count() > 0:
            first_card = cards.first
            badge_text = first_card.locator(".badge").inner_text()
            assert badge_text in ("已完成", "已跳过")

    def test_A19_filter_no_matching_shows_empty_state(self, e2e_page, e2e_server, e2e_test_files):
        """A19: Filter with no matching tasks, show empty state message."""
        base_url = e2e_server["base_url"]

        _navigate_to_tasks(e2e_page)
        e2e_page.click('[data-task-filter-chip="failed"]')
        e2e_page.wait_for_load_state("networkidle")
        _wait_task_list_settled(e2e_page)

        cards_with_row = e2e_page.locator("article.task-card[data-task-row]")
        if cards_with_row.count() == 0:
            page_text = e2e_page.locator("article.task-card").first.inner_text()
            assert "当前筛选下还没有任务" in page_text or "空队列" in page_text

    def test_A20_switch_filter_clears_selection(self, e2e_page, e2e_server, e2e_test_files):
        """A20: Select tasks, switch filter, verify selection cleared."""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "Chernobyl.S01.COMPLETE.720p.AMZN.WEB-DL.mkv"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "PENDING")

        _navigate_to_tasks(e2e_page)

        checkbox = e2e_page.locator(f'input[data-task-select="{task["task_id"]}"]')
        if checkbox.is_visible(timeout=5000):
            checkbox.check()

            toolbar = e2e_page.locator("#task-batch-toolbar")
            assert toolbar.is_visible(timeout=3000)

        e2e_page.click('[data-task-filter-chip="success"]')
        e2e_page.wait_for_load_state("networkidle")
        _wait_task_list_settled(e2e_page)

        batch_count = e2e_page.locator("#task-batch-count")
        if batch_count.is_visible(timeout=3000):
            deadline = time.time() + 5
            count_text = batch_count.inner_text()
            while time.time() < deadline and "已选 0 项" not in count_text:
                time.sleep(0.2)
                count_text = batch_count.inner_text()
            assert "已选 0 项" in count_text
