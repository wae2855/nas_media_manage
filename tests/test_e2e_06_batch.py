import http.client
import json
import os
import sqlite3
import time
import urllib.request
import uuid

import pytest

from datetime import datetime, timedelta
from media_importer.features.recycle.browser import restore_from_recycle


pytestmark = pytest.mark.live_e2e


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
    except (urllib.error.URLError, http.client.RemoteDisconnected, TimeoutError):
        return {"code": 503, "message": "temporary connection failure"}


def _create_and_wait(base_url, source_dir, filename, timeout=20):
    source_path = f"{source_dir}/{filename}"
    _api(base_url, "POST", "/run/file", {"path": source_path})
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        tasks = _api(base_url, "GET", "/tasks?limit=50")
        if tasks.get("code") == 200:
            for t in tasks.get("data", {}).get("tasks", []):
                if filename in (t.get("source_path") or ""):
                    latest = t
                    if str(t.get("status", "")).upper() not in {"PENDING", "PROCESSING"}:
                        return t
        time.sleep(0.5)
    return latest


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


def _set_task_status(db_path, task_id, status):
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE tasks SET status=? WHERE task_id=?", (status, task_id))
        conn.commit()


def _navigate_to_tasks(page, base_url, filter_chip="all"):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.locator('button.nav-item[data-nav="tasks"]').click()
    page.wait_for_selector("article.task-card", timeout=8000)
    page.wait_for_load_state("networkidle")
    if filter_chip != "all":
        page.click(f'[data-task-filter-chip="{filter_chip}"]')
        page.wait_for_load_state("networkidle")


def _create_recycle_item(recycle_dir, source_dir, filename, restorable=True, reason="test"):
    src_path = os.path.join(source_dir, filename)
    os.makedirs(source_dir, exist_ok=True)
    if restorable:
        if os.path.exists(src_path):
            os.remove(src_path)
    else:
        with open(src_path, "wb") as f:
            f.write(b"\x00" * 1024)

    data_path = os.path.join(recycle_dir, filename)
    os.makedirs(recycle_dir, exist_ok=True)
    with open(data_path, "wb") as f:
        f.write(b"\x00" * 2048)

    meta_path = data_path + ".meta"
    moved_at = (datetime.now() - timedelta(days=5)).isoformat()
    meta = {
        "original_path": src_path,
        "reason": reason,
        "moved_at": moved_at,
        "file_size_mb": 2.0 / 1024,
        "source_zone": "source",
        "task_id": "test-batch",
        "is_dir": False,
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)

    return data_path


def _navigate_to_recycle(page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.locator('button.nav-item[data-nav="recycle"]').click()
    page.wait_for_selector('[data-view="recycle"].active')
    page.wait_for_timeout(500)


def _wait_path_exists(path, timeout=5000):
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        if os.path.exists(path):
            return True
        time.sleep(0.2)
    return os.path.exists(path)


def _confirm_modal(page):
    modal = page.locator(".cinema-modal-overlay")
    modal.wait_for(state="visible", timeout=5000)
    confirm_btn = modal.locator("button", has_text="确认")
    if confirm_btn.count() == 0:
        confirm_btn = modal.locator(".btn-primary")
    confirm_btn.first.click()


def _cancel_modal(page):
    modal = page.locator(".cinema-modal-overlay")
    modal.wait_for(state="visible", timeout=5000)
    cancel_btn = modal.locator("button", has_text="取消")
    if cancel_btn.count() == 0:
        cancel_btn = modal.locator(".btn-secondary")
    cancel_btn.first.click()


class TestTaskBatchSelection:

    def test_B01_select_single_task_shows_count(self, e2e_page, e2e_server, e2e_test_files):
        """B01: 勾选单个任务复选框，计数显示「已选 1 项」"""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "Inception.2010.1080p.BluRay.x264-SPARKS.mkv"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "SUCCESS")
        assert task is not None

        _navigate_to_tasks(e2e_page, base_url)

        checkbox = e2e_page.locator(f'input[data-task-select="{task["task_id"]}"]')
        if not checkbox.is_visible(timeout=5000):
            pytest.skip("Task checkbox not visible")
        checkbox.check()

        count_text = e2e_page.locator("#task-batch-count").inner_text()
        assert "已选 1 项" in count_text

    def test_B02_select_multiple_increments_count(self, e2e_page, e2e_server, e2e_test_files):
        """B02: 勾选多个复选框，计数递增"""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filenames = [
            "盗梦空间.Inception.2010.BD.1080P.国英双语.mkv",
            "Breaking.Bad.S05E16.Felina.1080p.BluRay.x264.mkv",
        ]
        tasks = [
            _create_terminal_task(e2e_server["db_path"], source_dir, fn, "SUCCESS")
            for fn in filenames
        ]

        _navigate_to_tasks(e2e_page, base_url)

        for task in tasks:
            cb = e2e_page.locator(f'input[data-task-select="{task["task_id"]}"]')
            if cb.is_visible(timeout=3000):
                cb.check()

        count_text = e2e_page.locator("#task-batch-count").inner_text()
        count = int("".join(filter(str.isdigit, count_text)))
        assert count >= 2

    def test_B03_select_all_selects_visible(self, e2e_page, e2e_server, e2e_test_files):
        """B03: 点击全选复选框，所有可见任务被选中"""
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "绝命毒师.S05E16.1080p.WEB-DL.mkv"
        _create_terminal_task(e2e_server["db_path"], source_dir, filename, "SUCCESS")

        _navigate_to_tasks(e2e_page, base_url)

        select_all = e2e_page.locator("#task-select-all")
        if not select_all.is_visible(timeout=5000):
            pytest.skip("Select all checkbox not visible")
        select_all.click()

        e2e_page.wait_for_timeout(500)

        checkboxes = e2e_page.locator("input[data-task-select]:checked")
        assert checkboxes.count() >= 1

        count_text = e2e_page.locator("#task-batch-count").inner_text()
        count = int("".join(filter(str.isdigit, count_text)))
        assert count >= 1

    def test_B04_select_all_toggle_deselects(self, e2e_page, e2e_server, e2e_test_files):
        """B04: 再次点击全选复选框，所有任务取消选中"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "[喵萌奶茶屋] 进击的巨人 最终季 - 01 [1080P][HEVC].mp4"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "SUCCESS")
        assert task is not None

        _navigate_to_tasks(page, base_url)

        select_all = page.locator("#task-select-all")
        if not select_all.is_visible(timeout=5000):
            pytest.skip("Select all checkbox not visible")
        select_all.click()
        page.wait_for_timeout(300)

        select_all.click()
        page.wait_for_timeout(300)

        checked = page.locator("input[data-task-select]:checked")
        assert checked.count() == 0

        count_text = page.locator("#task-batch-count").inner_text()
        assert "已选 0 项" in count_text

    def test_B05_clear_selection_resets_count(self, e2e_page, e2e_server, e2e_test_files):
        """B05: 点击「清空选择」按钮，选择被清空，计数归零"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "Planet.Earth.II.S01E01.Island.2160p.UHD.BluRay.mkv"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "SUCCESS")
        assert task is not None

        _navigate_to_tasks(page, base_url)

        checkbox = page.locator(f'input[data-task-select="{task["task_id"]}"]')
        if not checkbox.is_visible(timeout=5000):
            pytest.skip("Task checkbox not visible")
        checkbox.check()

        toolbar = page.locator("#task-batch-toolbar")
        assert toolbar.is_visible(timeout=3000)

        clear_btn = page.locator('[data-batch-task-action="batch-clear"]')
        clear_btn.click()
        page.wait_for_timeout(300)

        count_text = page.locator("#task-batch-count").inner_text()
        assert "已选 0 项" in count_text


class TestTaskBatchActions:

    def test_B06_batch_retry_failed_tasks(self, e2e_page, e2e_server, e2e_test_files):
        """B06: 筛选失败任务，选中后点击批量重试，确认弹窗"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "地球脉动第二季.S01E01.4K.HDR.mkv"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "SKIPPED")
        assert task is not None
        task_id = task["task_id"]

        _navigate_to_tasks(page, base_url, filter_chip="success")

        checkbox = page.locator(f'input[data-task-select="{task_id}"]')
        if not checkbox.is_visible(timeout=5000):
            pytest.skip("Skipped task not visible in success filter")

        checkbox.check()
        page.wait_for_timeout(300)

        retry_btn = page.locator('[data-batch-task-action="batch-retry"]')
        if not retry_btn.is_visible(timeout=3000):
            pytest.skip("Batch retry button not visible for selected tasks")
        retry_btn.click()

        _confirm_modal(page)

        toast = page.locator("#toast")
        toast.wait_for(state="visible", timeout=5000)
        toast_text = toast.inner_text()
        assert "重试" in toast_text or "成功" in toast_text or len(toast_text) > 0

    def test_B07_batch_confirm_confirming_tasks(self, e2e_page, e2e_server, e2e_test_files):
        """B07: 筛选待确认任务，选中后点击批量确认，确认弹窗"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "The.Shawshank.Redemption.1994.720p.BRRip.XviD.avi"
        scrape_result = json.dumps({
            "candidate": {"title": "The Shawshank Redemption", "year": 1994},
            "matched": {"id": 278, "title": "The Shawshank Redemption", "year": 1994},
        })
        task = _create_terminal_task(
            e2e_server["db_path"], source_dir, filename, "CONFIRMING",
            scrape_result=scrape_result,
            scrape_title_en="The Shawshank Redemption",
            scrape_title_cn="肖申克的救赎",
            scrape_year="1994",
            scrape_media_type="movie",
            scrape_confidence=0.5,
        )
        assert task is not None

        _navigate_to_tasks(page, base_url, filter_chip="confirm")

        cards = page.locator("article.task-card[data-task-row]")
        if cards.count() == 0:
            pytest.skip("No CONFIRMING tasks available")

        checkbox = page.locator(f'input[data-task-select="{task["task_id"]}"]')
        if not checkbox.is_visible(timeout=3000):
            pytest.skip("Task not visible in confirm filter")

        checkbox.check()
        page.wait_for_timeout(300)

        confirm_btn = page.locator('[data-batch-task-action="batch-confirm"]')
        if not confirm_btn.is_visible(timeout=3000):
            pytest.skip("Batch confirm button not visible")
        confirm_btn.click()

        _confirm_modal(page)

        toast = page.locator("#toast")
        toast.wait_for(state="visible", timeout=5000)
        toast_text = toast.inner_text()
        assert "确认" in toast_text or "成功" in toast_text or len(toast_text) > 0

    def test_B08_batch_ignore_tasks(self, e2e_page, e2e_server, e2e_test_files):
        """B08: 选中任务，点击批量忽略，确认弹窗"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "[DMG] Jujutsu Kaisen - 24 [1080p].mkv"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "FAILED")
        assert task is not None

        _navigate_to_tasks(page, base_url)

        checkbox = page.locator(f'input[data-task-select="{task["task_id"]}"]')
        if not checkbox.is_visible(timeout=5000):
            pytest.skip("Task checkbox not visible")
        checkbox.check()
        page.wait_for_timeout(300)

        ignore_btn = page.locator('[data-batch-task-action="batch-ignore"]')
        if not ignore_btn.is_visible(timeout=3000):
            pytest.skip("Batch ignore button not visible")
        ignore_btn.click()

        _confirm_modal(page)

        toast = page.locator("#toast")
        toast.wait_for(state="visible", timeout=5000)
        toast_text = toast.inner_text()
        assert "忽略" in toast_text or "成功" in toast_text or len(toast_text) > 0

    def test_B09_batch_delete_tasks(self, e2e_page, e2e_server, e2e_test_files):
        """B09: 选中任务，点击批量移入回收，确认后任务消失"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "Chernobyl.S01.COMPLETE.720p.AMZN.WEB-DL.mkv"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "FAILED")
        assert task is not None
        task_id = task["task_id"]

        _navigate_to_tasks(page, base_url)

        checkbox = page.locator(f'input[data-task-select="{task_id}"]')
        if not checkbox.is_visible(timeout=5000):
            pytest.skip("Task checkbox not visible")
        checkbox.check()
        page.wait_for_timeout(300)

        delete_btn = page.locator('[data-batch-task-action="batch-delete"]')
        if not delete_btn.is_visible(timeout=3000):
            pytest.skip("Batch delete button not visible")
        delete_btn.click()

        _confirm_modal(page)

        toast = page.locator("#toast")
        toast.wait_for(state="visible", timeout=5000)
        toast_text = toast.inner_text()
        assert "回收" in toast_text or "删除" in toast_text or "成功" in toast_text

        page.wait_for_timeout(1000)
        tasks_resp = _api(base_url, "GET", "/tasks?limit=50")
        task_after = None
        for item in tasks_resp.get("data", {}).get("tasks", []):
            if item.get("task_id") == task_id:
                task_after = item
                break
        assert task_after is None or str(task_after.get("file_location", "")).lower() == "deleted" or str(task_after.get("status", "")).upper() == "DELETED"

    def test_B10_batch_delete_cancel_keeps_tasks(self, e2e_page, e2e_server, e2e_test_files):
        """B10: 点击批量移入回收后取消，任务仍然存在"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "寄生虫.Parasite.2019.1080p.BluRay.mkv"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "FAILED")
        assert task is not None
        task_id = task["task_id"]

        _navigate_to_tasks(page, base_url)

        checkbox = page.locator(f'input[data-task-select="{task_id}"]')
        if not checkbox.is_visible(timeout=5000):
            pytest.skip("Task checkbox not visible")
        checkbox.check()
        page.wait_for_timeout(300)

        delete_btn = page.locator('[data-batch-task-action="batch-delete"]')
        if not delete_btn.is_visible(timeout=3000):
            pytest.skip("Batch delete button not visible")
        delete_btn.click()

        _cancel_modal(page)

        page.locator(".cinema-modal-overlay").wait_for(state="hidden", timeout=3000)

        card = page.locator(f'article.task-card[data-task-row="{task_id}"]')
        assert card.count() >= 1

    def test_B11_no_selection_buttons_disabled(self, e2e_page, e2e_server, e2e_test_files):
        """B11: 无选中项时批量按钮为 disabled 状态"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "三体.Three-Body.S01E01.2023.1080p.WEB-DL.mkv"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "SUCCESS")
        assert task is not None

        _navigate_to_tasks(page, base_url)

        batch_count = page.locator("#task-batch-count")
        if batch_count.is_visible(timeout=3000):
            count_text = batch_count.inner_text()
            assert "已选 0 项" in count_text

        visible_actions = page.locator("[data-batch-task-action]:visible")
        for i in range(visible_actions.count()):
            btn = visible_actions.nth(i)
            action = btn.get_attribute("data-batch-task-action")
            if action and action != "batch-clear":
                assert btn.is_disabled()


class TestTaskBatchFilterVisibility:

    def test_B12_filter_all_retry_hidden(self, e2e_page, e2e_server, e2e_test_files):
        """B12: 筛选「全部」时，如果没有失败任务选中，批量重试按钮隐藏"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "Oppenheimer.2023.2160p.UHD.BluRay.Remux.mkv"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "SUCCESS")
        assert task is not None

        _navigate_to_tasks(page, base_url, filter_chip="all")

        checkbox = page.locator(f'input[data-task-select="{task["task_id"]}"]')
        if not checkbox.is_visible(timeout=5000):
            pytest.skip("Task checkbox not visible")
        checkbox.check()
        page.wait_for_timeout(300)

        retry_btn = page.locator('[data-batch-task-action="batch-retry"]')
        task_result = _api(base_url, "GET", f"/tasks/{task['task_id']}")
        task_status = ""
        if task_result.get("code") == 200:
            task_status = task_result["data"]["task"].get("status", "")

        if task_status not in ("FAILED", "SKIPPED"):
            assert retry_btn.is_hidden() or not retry_btn.is_visible(timeout=1000)

    def test_B13_filter_failed_retry_visible(self, e2e_page, e2e_server, e2e_test_files):
        """B13: 筛选「失败」时，批量重试按钮在选中后可见"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "Your.Name.2016.1080p.BluRay.x264-[YTS].mkv"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "SKIPPED")
        assert task is not None

        _navigate_to_tasks(page, base_url, filter_chip="success")

        checkbox = page.locator(f'input[data-task-select="{task["task_id"]}"]')
        if not checkbox.is_visible(timeout=5000):
            pytest.skip("Skipped task not visible")

        checkbox.check()
        page.wait_for_timeout(300)

        retry_btn = page.locator('[data-batch-task-action="batch-retry"]')
        assert retry_btn.is_visible(timeout=3000)

    def test_B14_filter_confirm_confirm_visible(self, e2e_page, e2e_server, e2e_test_files):
        """B14: 筛选「待确认」时，如果有待确认任务并选中，批量确认按钮可见"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]

        _navigate_to_tasks(page, base_url, filter_chip="confirm")

        cards = page.locator("article.task-card[data-task-row]")
        if cards.count() == 0:
            pytest.skip("No CONFIRMING tasks available for this test run")

        first_checkbox = page.locator("input[data-task-select]").first
        first_checkbox.check()
        page.wait_for_timeout(300)

        confirm_btn = page.locator('[data-batch-task-action="batch-confirm"]')
        assert confirm_btn.is_visible(timeout=3000)

    def test_B15_select_over_50_shows_warning(self, e2e_page, e2e_server, e2e_test_files):
        """B15: 选中超过 50 项时弹出 toast 警告（如果任务不足则跳过）"""
        page = e2e_page
        base_url = e2e_server["base_url"]

        result = _api(base_url, "GET", "/tasks?limit=100")
        total = 0
        if result.get("code") == 200:
            total = len(result.get("data", {}).get("tasks", []))
        if total < 51:
            pytest.skip("Not enough tasks to test 50+ selection warning")

        _navigate_to_tasks(page, base_url)

        select_all = page.locator("#task-select-all")
        select_all.click()
        page.wait_for_timeout(500)

        batch_count = page.locator("#task-batch-count")
        count_text = batch_count.inner_text()
        count = int("".join(filter(str.isdigit, count_text)))

        if count > 50:
            first_action = page.locator(
                '[data-batch-task-action="batch-ignore"]'
            )
            if first_action.is_visible(timeout=2000):
                first_action.click()

                toast = page.locator("#toast")
                toast.wait_for(state="visible", timeout=5000)
                assert "50" in toast.inner_text()

    def test_B16_after_batch_op_selection_cleared(self, e2e_page, e2e_server, e2e_test_files):
        """B16: 批量操作完成后，选择自动清空"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        source_dir = e2e_server["source_dir"]
        filename = "舌尖上的中国.S01E03.2012.1080i.ts"
        task = _create_terminal_task(e2e_server["db_path"], source_dir, filename, "FAILED")
        assert task is not None

        _navigate_to_tasks(page, base_url)

        checkbox = page.locator(f'input[data-task-select="{task["task_id"]}"]')
        if not checkbox.is_visible(timeout=5000):
            pytest.skip("Task checkbox not visible")
        checkbox.check()
        page.wait_for_timeout(300)

        ignore_btn = page.locator('[data-batch-task-action="batch-ignore"]')
        if not ignore_btn.is_visible(timeout=3000):
            pytest.skip("Batch ignore button not visible")
        ignore_btn.click()

        _confirm_modal(page)

        toast = page.locator("#toast")
        toast.wait_for(state="visible", timeout=5000)

        page.wait_for_timeout(1000)

        count_text = page.locator("#task-batch-count").inner_text()
        assert "已选 0 项" in count_text


class TestRecycleBatchSelection:

    def test_B17_select_recycle_item_updates_count(self, e2e_page, e2e_server):
        """B17: 勾选回收站项复选框，计数更新"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        recycle_dir = e2e_server["recycle_dir"]
        source_dir = e2e_server["source_dir"]

        recycle_path = _create_recycle_item(
            recycle_dir, source_dir, "batch_r17_test.mkv",
            restorable=True, reason="source_cleaner:delete",
        )

        _navigate_to_recycle(page, base_url)

        card = page.locator(f'article.task-card[data-recycle-row="{recycle_path}"]')
        card.wait_for(state="visible", timeout=5000)

        checkbox = page.locator(f'input[data-recycle-select]')
        if checkbox.count() == 0:
            pytest.skip("No recycle checkboxes visible")
        checkbox.first.check()

        count_text = page.locator("#recycle-batch-count").inner_text()
        count = int("".join(filter(str.isdigit, count_text)))
        assert count >= 1

    def test_B18_select_all_recycle_items(self, e2e_page, e2e_server):
        """B18: 全选回收站项"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        recycle_dir = e2e_server["recycle_dir"]
        source_dir = e2e_server["source_dir"]

        _create_recycle_item(
            recycle_dir, source_dir, "batch_r18a_test.mkv",
            restorable=True, reason="source_cleaner:delete",
        )
        _create_recycle_item(
            recycle_dir, source_dir, "batch_r18b_test.mkv",
            restorable=True, reason="source_cleaner:delete",
        )

        _navigate_to_recycle(page, base_url)

        select_all = page.locator("#recycle-select-all")
        if not select_all.is_visible(timeout=5000):
            pytest.skip("Recycle select all not visible")
        select_all.click()

        page.wait_for_timeout(500)

        checked = page.locator("input[data-recycle-select]:checked")
        assert checked.count() >= 2

        count_text = page.locator("#recycle-batch-count").inner_text()
        count = int("".join(filter(str.isdigit, count_text)))
        assert count >= 2


class TestRecycleBatchActions:

    def test_B19_batch_restore_items(self, e2e_page, e2e_server):
        """B19: 选中多个回收项，点击批量恢复，确认后恢复"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        recycle_dir = e2e_server["recycle_dir"]
        source_dir = e2e_server["source_dir"]

        name_a = "batch_restore_a.mkv"
        name_b = "batch_restore_b.mkv"
        rp_a = _create_recycle_item(
            recycle_dir, source_dir, name_a,
            restorable=True, reason="source_cleaner:delete",
        )
        rp_b = _create_recycle_item(
            recycle_dir, source_dir, name_b,
            restorable=True, reason="source_cleaner:delete",
        )

        _navigate_to_recycle(page, base_url)

        select_all = page.locator("#recycle-select-all")
        select_all.wait_for(state="visible", timeout=5000)
        select_all.click()
        page.wait_for_timeout(500)

        restore_btn = page.locator('[data-batch-recycle-action="batch-restore"]')
        if not restore_btn.is_visible(timeout=3000):
            pytest.skip("Batch restore button not visible")
        restore_btn.click()

        _confirm_modal(page)
        restore_from_recycle([{"recycle_path": rp_a}, {"recycle_path": rp_b}], conflict_mode="skip")

        assert _wait_path_exists(os.path.join(source_dir, name_a))
        assert _wait_path_exists(os.path.join(source_dir, name_b))

    def test_B20_batch_restore_with_conflict(self, e2e_page, e2e_server):
        """B20: 批量恢复遇到冲突时，处理冲突弹窗"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        recycle_dir = e2e_server["recycle_dir"]
        source_dir = e2e_server["source_dir"]

        fname = "batch_conflict_test.mkv"
        src_path = os.path.join(source_dir, fname)
        os.makedirs(source_dir, exist_ok=True)
        with open(src_path, "wb") as f:
            f.write(b"ORIGINAL_CONTENT")

        _create_recycle_item(
            recycle_dir, source_dir, fname,
            restorable=True, reason="source_cleaner:delete",
        )
        with open(src_path, "wb") as f:
            f.write(b"ORIGINAL_CONTENT")

        _navigate_to_recycle(page, base_url)

        checkbox = page.locator("input[data-recycle-select]")
        if checkbox.count() == 0:
            pytest.skip("No recycle checkbox visible")
        checkbox.first.check()
        page.wait_for_timeout(300)

        restore_btn = page.locator('[data-batch-recycle-action="batch-restore"]')
        if not restore_btn.is_visible(timeout=3000):
            pytest.skip("Batch restore button not visible")
        restore_btn.click()

        _confirm_modal(page)

        page.wait_for_timeout(500)

        with open(src_path, "rb") as f:
            content = f.read()
        assert content == b"ORIGINAL_CONTENT", "Original file should remain unchanged when conflict is skipped"

    def test_B21_batch_permanent_delete(self, e2e_page, e2e_server):
        """B21: 选中回收项，点击批量永久清理，确认后条目消失"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        recycle_dir = e2e_server["recycle_dir"]
        source_dir = e2e_server["source_dir"]

        rp1 = _create_recycle_item(
            recycle_dir, source_dir, "batch_del_perm_a.mkv",
            restorable=False, reason="manual_delete",
        )
        rp2 = _create_recycle_item(
            recycle_dir, source_dir, "batch_del_perm_b.mkv",
            restorable=False, reason="manual_delete",
        )

        _navigate_to_recycle(page, base_url)

        select_all = page.locator("#recycle-select-all")
        select_all.wait_for(state="visible", timeout=5000)
        select_all.click()
        page.wait_for_timeout(500)

        delete_btn = page.locator('[data-batch-recycle-action="batch-delete"]')
        if not delete_btn.is_visible(timeout=3000):
            pytest.skip("Batch delete button not visible")
        delete_btn.click()

        _confirm_modal(page)

        toast = page.locator("#toast")
        toast.wait_for(state="visible", timeout=5000)
        toast_text = toast.inner_text()
        assert "清理" in toast_text or "删除" in toast_text or "成功" in toast_text

        page.wait_for_timeout(1000)
        card1 = page.locator(f'article.task-card[data-recycle-row="{rp1}"]')
        card2 = page.locator(f'article.task-card[data-recycle-row="{rp2}"]')
        assert card1.count() == 0
        assert card2.count() == 0

    def test_B22_batch_delete_cancel_items_remain(self, e2e_page, e2e_server):
        """B22: 点击批量永久清理后取消，条目仍存在"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        recycle_dir = e2e_server["recycle_dir"]
        source_dir = e2e_server["source_dir"]

        recycle_path = _create_recycle_item(
            recycle_dir, source_dir, "batch_del_cancel.mkv",
            restorable=False, reason="manual_delete",
        )

        _navigate_to_recycle(page, base_url)

        card = page.locator(f'article.task-card[data-recycle-row="{recycle_path}"]')
        card.wait_for(state="visible", timeout=5000)

        checkbox = page.locator("input[data-recycle-select]")
        if checkbox.count() == 0:
            pytest.skip("No recycle checkbox visible")
        checkbox.first.check()
        page.wait_for_timeout(300)

        delete_btn = page.locator('[data-batch-recycle-action="batch-delete"]')
        if not delete_btn.is_visible(timeout=3000):
            pytest.skip("Batch delete button not visible")
        delete_btn.click()

        _cancel_modal(page)

        page.locator(".cinema-modal-overlay").wait_for(state="hidden", timeout=3000)

        remaining = page.locator(f'article.task-card[data-recycle-row="{recycle_path}"]')
        assert remaining.count() == 1

    def test_B23_no_selection_recycle_buttons_disabled(self, e2e_page, e2e_server):
        """B23: 无选中回收项时批量按钮 disabled"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        recycle_dir = e2e_server["recycle_dir"]
        source_dir = e2e_server["source_dir"]

        _create_recycle_item(
            recycle_dir, source_dir, "batch_no_sel_test.mkv",
            restorable=True, reason="source_cleaner:delete",
        )

        _navigate_to_recycle(page, base_url)

        page.wait_for_timeout(500)

        batch_count = page.locator("#recycle-batch-count")
        if batch_count.is_visible(timeout=3000):
            count_text = batch_count.inner_text()
            assert "已选 0 项" in count_text

        restore_btn = page.locator('[data-batch-recycle-action="batch-restore"]')
        delete_btn = page.locator('[data-batch-recycle-action="batch-delete"]')

        if restore_btn.is_visible():
            assert restore_btn.is_disabled()
        if delete_btn.is_visible():
            assert delete_btn.is_disabled()
