import json
import os
import time
import urllib.request

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
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8"))


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
        "task_id": "test-task",
        "is_dir": False,
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)

    return data_path


def _create_expired_recycle_item(recycle_dir, source_dir, filename):
    src_path = os.path.join(source_dir, filename)
    os.makedirs(source_dir, exist_ok=True)
    with open(src_path, "wb") as f:
        f.write(b"\x00" * 1024)

    data_path = os.path.join(recycle_dir, filename)
    os.makedirs(recycle_dir, exist_ok=True)
    with open(data_path, "wb") as f:
        f.write(b"\x00" * 1024)

    meta_path = data_path + ".meta"
    moved_at = (datetime.now() - timedelta(days=60)).isoformat()
    meta = {
        "original_path": src_path,
        "reason": "recycle_expired",
        "moved_at": moved_at,
        "file_size_mb": 1.0 / 1024,
        "source_zone": "source",
        "task_id": "expired-task",
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


def _wait_locator_gone(locator, timeout=5000):
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        if locator.count() == 0:
            return True
        time.sleep(0.2)
    return locator.count() == 0


def _wait_path_exists(path, timeout=5000):
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        if os.path.exists(path):
            return True
        time.sleep(0.2)
    return os.path.exists(path)


def _wait_path_missing(path, timeout=5000):
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        if not os.path.exists(path):
            return True
        time.sleep(0.2)
    return not os.path.exists(path)


class TestRecycleBasics:

    def test_R01_empty_recycle_shows_empty_text(self, e2e_page, e2e_server):
        """R01: 空回收站应显示"回收站还是空的"提示文本"""
        page = e2e_page
        base_url = e2e_server["base_url"]

        recycle_dir = e2e_server["recycle_dir"]
        for f in os.listdir(recycle_dir):
            fp = os.path.join(recycle_dir, f)
            if os.path.isfile(fp):
                os.remove(fp)

        _navigate_to_recycle(page, base_url)

        recycle_list = page.locator("#recycle-list")
        inner = recycle_list.inner_text()
        assert "回收站还是空的" in inner or "当前回收站还是空的" in inner

    def test_R02_recycle_stats_show_counts(self, e2e_page, e2e_server):
        """R02: 有回收项时统计区显示正确的可恢复/待清理计数"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        recycle_dir = e2e_server["recycle_dir"]
        source_dir = e2e_server["source_dir"]

        _create_recycle_item(
            recycle_dir, source_dir, "restorable_movie.mkv",
            restorable=True, reason="source_cleaner:delete",
        )
        _create_recycle_item(
            recycle_dir, source_dir, "cleanup_movie.mkv",
            restorable=False, reason="manual_delete",
        )

        _navigate_to_recycle(page, base_url)

        recoverable = page.locator("#recycle-recoverable-count").inner_text()
        cleanup = page.locator("#recycle-cleanup-count").inner_text()
        size_text = page.locator("#recycle-size").inner_text()

        assert int(recoverable) >= 1
        assert int(cleanup) >= 1
        assert size_text != "--"

    def test_R03_restore_recoverable_item(self, e2e_page, e2e_server):
        """R03: 点击可恢复项的"立即恢复"按钮，验证 toast 提示成功且条目消失"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        recycle_dir = e2e_server["recycle_dir"]
        source_dir = e2e_server["source_dir"]

        fname = "restore_test_movie.mkv"
        recycle_path = _create_recycle_item(
            recycle_dir, source_dir, fname,
            restorable=True, reason="source_cleaner:delete",
        )

        _navigate_to_recycle(page, base_url)

        card = page.locator(f'article.task-card[data-recycle-row="{recycle_path}"]')
        card.wait_for(state="visible", timeout=5000)

        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(f"{msg.type}: {msg.text}") if msg.type == "error" else None)

        restore_btn = card.locator('[data-recycle-action="restore-recycle"]')
        restore_btn.click()

        confirm_btn = page.locator(".cinema-modal-overlay .btn-primary")
        confirm_btn.wait_for(state="visible", timeout=3000)
        confirm_btn.click()

        restored_path = os.path.join(source_dir, fname)
        assert _wait_path_exists(restored_path), f"restore failed; console={errors}"
        assert _wait_path_missing(recycle_path)
        _navigate_to_recycle(page, base_url)
        cards = page.locator(f'article.task-card[data-recycle-row="{recycle_path}"]')
        assert _wait_locator_gone(cards)

    def test_R04_view_reason_on_non_recoverable(self, e2e_page, e2e_server):
        """R04: 点击不可恢复项的"查看原因"按钮，验证弹窗显示原因信息"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        recycle_dir = e2e_server["recycle_dir"]
        source_dir = e2e_server["source_dir"]

        fname = "view_reason_test.mkv"
        recycle_path = _create_recycle_item(
            recycle_dir, source_dir, fname,
            restorable=False, reason="manual_delete",
        )

        _navigate_to_recycle(page, base_url)

        card = page.locator(f'article.task-card[data-recycle-row="{recycle_path}"]')
        card.wait_for(state="visible", timeout=5000)

        view_btn = card.locator('[data-recycle-action="view-recycle"]')
        view_btn.click()

        modal = page.locator(".cinema-modal-overlay")
        modal.wait_for(state="visible", timeout=3000)
        modal_text = modal.inner_text()
        assert "回收记录详情" in modal_text or "原路径" in modal_text or "原因" in modal_text

    def test_R05_delete_cleanup_item(self, e2e_page, e2e_server):
        """R05: 点击清理项的"去清理"按钮并确认，验证条目被移除"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        recycle_dir = e2e_server["recycle_dir"]
        source_dir = e2e_server["source_dir"]

        fname = "delete_cleanup_test.mkv"
        recycle_path = _create_recycle_item(
            recycle_dir, source_dir, fname,
            restorable=False, reason="manual_delete",
        )

        _navigate_to_recycle(page, base_url)

        card = page.locator(f'article.task-card[data-recycle-row="{recycle_path}"]')
        card.wait_for(state="visible", timeout=5000)

        delete_btn = card.locator('[data-recycle-action="delete-recycle"]')
        delete_btn.click()

        with page.expect_response(lambda resp: "/api/recycle/delete" in resp.url) as resp_info:
            confirm_btn = page.locator(".cinema-modal-overlay .btn-primary")
            confirm_btn.wait_for(state="visible", timeout=3000)
            confirm_btn.click()
        resp_json = resp_info.value.json()
        assert resp_json.get("code") in (200, 207)

        assert _wait_path_missing(recycle_path)
        _navigate_to_recycle(page, base_url)
        cards = page.locator(f'article.task-card[data-recycle-row="{recycle_path}"]')
        assert _wait_locator_gone(cards)

    def test_R06_delete_cancel_item_remains(self, e2e_page, e2e_server):
        """R06: 点击"去清理"后取消确认，验证条目仍然存在"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        recycle_dir = e2e_server["recycle_dir"]
        source_dir = e2e_server["source_dir"]

        fname = "delete_cancel_test.mkv"
        recycle_path = _create_recycle_item(
            recycle_dir, source_dir, fname,
            restorable=False, reason="manual_delete",
        )

        _navigate_to_recycle(page, base_url)

        card = page.locator(f'article.task-card[data-recycle-row="{recycle_path}"]')
        card.wait_for(state="visible", timeout=5000)

        delete_btn = card.locator('[data-recycle-action="delete-recycle"]')
        delete_btn.click()

        cancel_btn = page.locator(".cinema-modal-overlay .btn-secondary")
        cancel_btn.wait_for(state="visible", timeout=3000)
        cancel_btn.click()

        page.wait_for_timeout(500)

        cards = page.locator(f'article.task-card[data-recycle-row="{recycle_path}"]')
        assert cards.count() == 1

    def test_R07_clean_expired_items(self, e2e_page, e2e_server):
        """R07: 点击 hero 区的"清理过期项"按钮并确认，验证过期条目被移除"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        recycle_dir = e2e_server["recycle_dir"]
        source_dir = e2e_server["source_dir"]

        fname = "expired_item_test.mkv"
        recycle_path = _create_expired_recycle_item(
            recycle_dir, source_dir, fname,
        )

        _navigate_to_recycle(page, base_url)

        card = page.locator(f'article.task-card[data-recycle-row="{recycle_path}"]')
        card.wait_for(state="visible", timeout=5000)

        clean_btn = page.locator('[data-action="clear-expired-recycle"]')
        clean_btn.click()

        with page.expect_response(lambda resp: "/api/recycle/delete" in resp.url) as resp_info:
            confirm_btn = page.locator(".cinema-modal-overlay .btn-primary")
            confirm_btn.wait_for(state="visible", timeout=3000)
            confirm_btn.click()
        resp_json = resp_info.value.json()
        assert resp_json.get("code") in (200, 207)

        assert _wait_path_missing(recycle_path)
        _navigate_to_recycle(page, base_url)
        cards = page.locator(f'article.task-card[data-recycle-row="{recycle_path}"]')
        assert _wait_locator_gone(cards)


class TestRecycleConflict:

    def test_R08_restore_conflict_skip(self, e2e_page, e2e_server):
        """R08: 恢复时原位置有同名文件 → 跳过 → 文件未被覆盖"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        recycle_dir = e2e_server["recycle_dir"]
        source_dir = e2e_server["source_dir"]

        fname = "conflict_skip_test.mkv"
        original_content = b"ORIGINAL_CONTENT"

        src_path = os.path.join(source_dir, fname)
        os.makedirs(source_dir, exist_ok=True)
        with open(src_path, "wb") as f:
            f.write(original_content)

        recycle_path = _create_recycle_item(
            recycle_dir, source_dir, fname,
            restorable=True, reason="source_cleaner:delete",
        )
        with open(src_path, "wb") as f:
            f.write(original_content)

        _navigate_to_recycle(page, base_url)

        card = page.locator(f'article.task-card[data-recycle-row="{recycle_path}"]')
        card.wait_for(state="visible", timeout=5000)

        result = restore_from_recycle([{"recycle_path": recycle_path}], conflict_mode="skip")
        assert result.get("failed")

        with open(src_path, "rb") as f:
            content = f.read()
        assert content == original_content

    def test_R09_restore_conflict_overwrite(self, e2e_page, e2e_server):
        """R09: 恢复时原位置有同名文件 → 覆盖 → 回收文件覆盖原文件"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        recycle_dir = e2e_server["recycle_dir"]
        source_dir = e2e_server["source_dir"]

        fname = "conflict_overwrite_test.mkv"
        original_content = b"ORIGINAL_CONTENT"

        src_path = os.path.join(source_dir, fname)
        os.makedirs(source_dir, exist_ok=True)
        with open(src_path, "wb") as f:
            f.write(original_content)

        recycle_path = _create_recycle_item(
            recycle_dir, source_dir, fname,
            restorable=True, reason="source_cleaner:delete",
        )
        with open(src_path, "wb") as f:
            f.write(original_content)

        _navigate_to_recycle(page, base_url)

        card = page.locator(f'article.task-card[data-recycle-row="{recycle_path}"]')
        card.wait_for(state="visible", timeout=5000)

        restore_from_recycle([{"recycle_path": recycle_path}], conflict_mode="overwrite")

        page.wait_for_timeout(500)

        with open(src_path, "rb") as f:
            content = f.read()
        assert content != original_content

    def test_R10_restore_conflict_rename(self, e2e_page, e2e_server):
        """R10: 恢复时原位置有同名文件 → 重命名 → 文件以不同名称恢复"""
        page = e2e_page
        base_url = e2e_server["base_url"]
        recycle_dir = e2e_server["recycle_dir"]
        source_dir = e2e_server["source_dir"]

        fname = "conflict_rename_test.mkv"
        original_content = b"ORIGINAL_CONTENT"

        src_path = os.path.join(source_dir, fname)
        os.makedirs(source_dir, exist_ok=True)
        with open(src_path, "wb") as f:
            f.write(original_content)

        recycle_path = _create_recycle_item(
            recycle_dir, source_dir, fname,
            restorable=True, reason="source_cleaner:delete",
        )
        with open(src_path, "wb") as f:
            f.write(original_content)

        _navigate_to_recycle(page, base_url)

        card = page.locator(f'article.task-card[data-recycle-row="{recycle_path}"]')
        card.wait_for(state="visible", timeout=5000)

        restore_from_recycle([{"recycle_path": recycle_path}], conflict_mode="rename")

        page.wait_for_timeout(500)

        name, ext = os.path.splitext(src_path)
        renamed_path = f"{name}_restored{ext}"
        assert os.path.exists(renamed_path), f"重命名恢复的文件应存在: {renamed_path}"
        with open(src_path, "rb") as f:
            assert f.read() == original_content
