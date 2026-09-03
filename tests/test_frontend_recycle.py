import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.api.handler import start_server
from media_importer.features.configuration import load_config


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def _wait_for_server(host, port, timeout=10):
    import urllib.request
    url = f'http://{host}:{port}/api/health'
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(url, timeout=2)
            if resp.status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


class TestFrontendRecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix='recycle_test_')
        cls.source_dir = os.path.join(cls.tmpdir, 'source')
        cls.log_dir = os.path.join(cls.tmpdir, 'logs')
        cls.recycle_dir = os.path.join(cls.tmpdir, 'recycle')
        for d in [cls.source_dir, cls.log_dir, cls.recycle_dir]:
            os.makedirs(d, exist_ok=True)

        config_yaml = f"""source_dir: {cls.source_dir}
log_dir: {cls.log_dir}
llm:
  api_key: test-key
  model: test-model
source_policy:
  recycle_dir: {cls.recycle_dir}
  cleanup_mode: full_cleanup
  delete_source_after_import: true
metadata:
  providers:
    - type: tmdb
      enabled: false
"""
        cls.config_path = os.path.join(cls.tmpdir, 'config.yaml')
        with open(cls.config_path, 'w') as f:
            f.write(config_yaml)

        cls.config = load_config(cls.config_path)
        cls.port = find_free_port()
        cls.host = '127.0.0.1'
        cls.base_url = f'http://{cls.host}:{cls.port}'

        cls._server_thread = threading.Thread(
            target=start_server,
            args=(cls.host, cls.port, cls.config),
            daemon=True,
        )
        cls._server_thread.start()
        if not _wait_for_server(cls.host, cls.port, timeout=10):
            raise RuntimeError('Server did not start within timeout')

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'tmpdir') and os.path.exists(cls.tmpdir):
            shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _open_page(self, playwright):
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(self.base_url)
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        return browser, page

    def _navigate_to_config_stage(self, page, stage):
        page.locator(".bottom-nav [data-nav='config']").click()
        time.sleep(0.5)
        page.locator(f"[data-config-stage='{stage}']").click()
        time.sleep(0.5)

    def _navigate_to_config_import(self, page):
        self._navigate_to_config_stage(page, "source")

    def _navigate_to_tasks(self, page):
        page.locator(".bottom-nav [data-nav='tasks']").click()
        time.sleep(0.5)

    def test_config_recycle_dir_is_a_storage_ledger_row(self):
        with sync_playwright() as p:
            browser, page = self._open_page(p)
            try:
                self._navigate_to_config_stage(page, "temp")
                recycle_row = page.locator(".storage-readiness-card", has_text="本地回收")
                self.assertEqual(recycle_row.count(), 1, "recycle storage row not found")
                self.assertIn(self.recycle_dir, recycle_row.inner_text())
            finally:
                browser.close()

    def test_config_cleanup_mode_options_exist_when_enabled(self):
        with sync_playwright() as p:
            browser, page = self._open_page(p)
            try:
                self._navigate_to_config_import(page)
                page.locator('input[name="cfg-source-after-done"][value="preserve_media"]').check()
                cleanup_modes = page.locator('input[name="cfg-source_cleaner-cleanup_mode_inline"]')
                self.assertEqual(cleanup_modes.count(), 2, "cleanup mode options not found")
                option_values = [cleanup_modes.nth(i).get_attribute("value") for i in range(cleanup_modes.count())]
                self.assertEqual(option_values, ["media_and_related", "media_only"])
            finally:
                browser.close()

    def test_config_no_isolation_zone_text(self):
        with sync_playwright() as p:
            browser, page = self._open_page(p)
            try:
                self._navigate_to_config_import(page)
                body_text = page.locator("body").inner_text()
                self.assertNotIn("隔离区", body_text, "Page should not contain '隔离区' text")
            finally:
                browser.close()

    def test_tasks_page_loads(self):
        with sync_playwright() as p:
            browser, page = self._open_page(p)
            try:
                self._navigate_to_tasks(page)
                tasks_panel = page.locator('.page-view[data-view="tasks"]')
                self.assertTrue(tasks_panel.is_visible(), "Tasks panel should be visible")
                task_list = page.locator("#task-list")
                self.assertTrue(task_list.is_visible(), "Task list should be visible")
            finally:
                browser.close()

    def test_task_cards_show_current_status_and_filename(self):
        with sync_playwright() as p:
            browser, page = self._open_page(p)
            try:
                self._navigate_to_tasks(page)
                page.evaluate("""() => {
                    currentTaskRecords = [
                        { task_id: 'test-1', source_filename: 'movie1.mkv', status: 'PENDING', stage: 'QUEUED', source_path: '/vol1/source/movie1.mkv' },
                        { task_id: 'test-2', source_filename: 'movie2.mkv', status: 'FAILED', stage: 'DONE', source_path: '/vol1/recycle/movie2.mkv' },
                        { task_id: 'test-3', source_filename: 'movie3.mkv', status: 'SUCCESS', stage: 'DONE', import_video_path: '/vol1/movies/movie3.mkv' },
                    ];
                    renderTaskList();
                }""")
                time.sleep(0.5)

                cards = page.locator(".task-card")
                self.assertEqual(cards.count(), 3)
                self.assertIn("排队中", cards.nth(0).inner_text())
                self.assertIn("失败", cards.nth(1).inner_text())
                self.assertIn("已完成", cards.nth(2).inner_text())
                self.assertIn("movie1.mkv", cards.nth(0).inner_text())
            finally:
                browser.close()

    def test_failed_task_card_has_recovery_actions(self):
        with sync_playwright() as p:
            browser, page = self._open_page(p)
            try:
                self._navigate_to_tasks(page)
                page.evaluate("""() => {
                    currentTaskRecords = [
                        { task_id: 'test-r', source_filename: 'recycled.mkv', status: 'FAILED', stage: 'DONE', source_path: '/vol1/recycle/recycled.mkv' },
                    ];
                    renderTaskList();
                }""")
                time.sleep(0.5)

                card = page.locator(".task-card").first
                self.assertIn("失败", card.inner_text())
                self.assertEqual(card.locator('[data-task-action="retry-task"]').count(), 1)
                self.assertEqual(card.locator('[data-task-action="view-task"]').count(), 1)
            finally:
                browser.close()

    def test_no_isolation_zone_text_entire_page(self):
        with sync_playwright() as p:
            browser, page = self._open_page(p)
            try:
                self._navigate_to_config_import(page)
                self._navigate_to_tasks(page)
                body_text = page.locator("body").inner_text()
                self.assertNotIn("隔离区", body_text, "Entire page should not contain '隔离区' text")
            finally:
                browser.close()

    def test_recycle_bin_text_appears(self):
        with sync_playwright() as p:
            browser, page = self._open_page(p)
            try:
                self._navigate_to_config_stage(page, "temp")
                body_text = page.locator("body").inner_text()
                self.assertIn("本地回收", body_text, "Page should identify the recycle directory in storage checks")
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()
