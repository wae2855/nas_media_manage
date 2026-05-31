import os
import sys
import tempfile
import shutil
import socket
import threading
import time
import unittest

import yaml
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.api.handler import start_server
from media_importer.core.config_loader import load_config


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
        cls.temp_dir = os.path.join(cls.tmpdir, 'temp')
        cls.log_dir = os.path.join(cls.tmpdir, 'logs')
        cls.recycle_dir = os.path.join(cls.tmpdir, 'recycle')
        for d in [cls.source_dir, cls.temp_dir, cls.log_dir, cls.recycle_dir]:
            os.makedirs(d, exist_ok=True)

        config_yaml = f"""source_dir: {cls.source_dir}
temp_dir: {cls.temp_dir}
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

    def _navigate_to_config_import(self, page):
        page.locator("#tab-config").click()
        time.sleep(0.5)
        page.locator("#cfg-subtab-import").click()
        time.sleep(0.5)

    def _navigate_to_tasks(self, page):
        page.locator("#tab-tasks").click()
        time.sleep(0.5)

    def test_config_recycle_dir_input_exists(self):
        with sync_playwright() as p:
            browser, page = self._open_page(p)
            try:
                self._navigate_to_config_import(page)
                recycle_input = page.locator("#cfg-source_policy-recycle_dir")
                self.assertEqual(recycle_input.count(), 1, "recycle_dir input not found")
                value = recycle_input.input_value()
                self.assertIn(self.recycle_dir, value, f"recycle_dir should contain {self.recycle_dir}, got {value}")
            finally:
                browser.close()

    def test_config_cleanup_mode_selector_exists(self):
        with sync_playwright() as p:
            browser, page = self._open_page(p)
            try:
                self._navigate_to_config_import(page)
                cleanup_select = page.locator("#cfg-source_policy-cleanup_mode")
                self.assertGreaterEqual(cleanup_select.count(), 1, "cleanup_mode selector not found")
                options = cleanup_select.locator("option")
                option_values = []
                for i in range(options.count()):
                    option_values.append(options.nth(i).get_attribute("value"))
                for expected in ["read_only", "smart_cleanup", "full_cleanup"]:
                    self.assertIn(expected, option_values, f"cleanup_mode missing option: {expected}")
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
                tasks_panel = page.locator("#tasks-panel")
                self.assertTrue(tasks_panel.is_visible(), "Tasks panel should be visible")
                table = page.locator("#tasks-table")
                self.assertTrue(table.is_visible(), "Tasks table should be visible")
            finally:
                browser.close()

    def test_tasks_file_location_labels(self):
        with sync_playwright() as p:
            browser, page = self._open_page(p)
            try:
                self._navigate_to_tasks(page)
                page.evaluate("""() => {
                    const tbody = document.getElementById('tasks-table-body');
                    if (!tbody) return;
                    const mockTasks = [
                        { task_id: 'test-1', source_filename: 'movie1.mkv', status: 'PENDING', file_location: 'source', source_path: '/vol1/source/movie1.mkv' },
                        { task_id: 'test-2', source_filename: 'movie2.mkv', status: 'FAILED', file_location: 'recycle', source_path: '/vol1/recycle/movie2.mkv' },
                        { task_id: 'test-3', source_filename: 'movie3.mkv', status: 'SUCCESS', file_location: 'import', import_video_path: '/vol1/movies/movie3.mkv' },
                    ];
                    if (typeof renderTaskTable === 'function') {
                        renderTaskTable(mockTasks);
                    }
                }""")
                time.sleep(0.5)

                source_tag = page.locator(".location-tag-source")
                self.assertGreater(source_tag.count(), 0, "location-tag-source not found")
                self.assertEqual(source_tag.first.inner_text(), "源目录")

                recycle_tag = page.locator(".location-tag-recycle")
                self.assertGreater(recycle_tag.count(), 0, "location-tag-recycle not found")
                self.assertEqual(recycle_tag.first.inner_text(), "回收站")

                import_tag = page.locator(".location-tag-import")
                self.assertGreater(import_tag.count(), 0, "location-tag-import not found")
                self.assertEqual(import_tag.first.inner_text(), "已入库")
            finally:
                browser.close()

    def test_tasks_recycle_css_class(self):
        with sync_playwright() as p:
            browser, page = self._open_page(p)
            try:
                self._navigate_to_tasks(page)
                page.evaluate("""() => {
                    const tbody = document.getElementById('tasks-table-body');
                    if (!tbody) return;
                    const mockTasks = [
                        { task_id: 'test-r', source_filename: 'recycled.mkv', status: 'FAILED', file_location: 'recycle', source_path: '/vol1/recycle/recycled.mkv' },
                    ];
                    if (typeof renderTaskTable === 'function') {
                        renderTaskTable(mockTasks);
                    }
                }""")
                time.sleep(0.5)

                recycle_tag = page.locator(".location-tag-recycle")
                self.assertGreater(recycle_tag.count(), 0, ".location-tag-recycle class not found")
                recycle_el = recycle_tag.first
                class_attr = recycle_el.get_attribute("class") or ""
                self.assertIn("location-tag-recycle", class_attr, "Element should have location-tag-recycle CSS class")
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
                self._navigate_to_config_import(page)
                body_text = page.locator("body").inner_text()
                self.assertIn("回收站", body_text, "Page should contain '回收站' text in config section")
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()
