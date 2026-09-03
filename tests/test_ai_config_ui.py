"""AI 配置 UI 测试（覆盖 T3.4）。

需要本地服务运行和 Playwright 安装。如果不满足条件，测试自动跳过。
"""
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.api.handler import start_server
from media_importer.features.configuration import load_config

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


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


# ========================================================================
# API 响应结构测试（无 Playwright 需要）
# ========================================================================

class TestAiConfigApiStructure(unittest.TestCase):
    """验证 AI 配置 API 响应结构（不需浏览器）。"""

    def test_config_llm_section_remains_available_in_raw_view(self):
        """LLM 仅服务源目录清理，配置保留在唯一 llm 块。"""
        from media_importer.features.configuration import ConfigView
        cfg = {
            "llm": {"base_url": "https://a.com", "model": "m", "api_key": "k"},
        }
        view = ConfigView.from_dict(cfg)
        self.assertEqual(view.raw["llm"]["base_url"], "https://a.com")
        self.assertEqual(view.raw["llm"]["model"], "m")
        self.assertEqual(view.raw["llm"]["api_key"], "k")

    def test_config_apikey_masked_in_config_view(self):
        """ConfigView 保留原始 api_key（脱敏在 API 层处理）。"""
        from media_importer.features.configuration import mask_sensitive
        cfg = {
            "llm": {"api_key": "my-secret-key"},
        }
        masked = mask_sensitive(cfg)
        self.assertIn("***", masked["llm"]["api_key"])

# ========================================================================
# Playwright 浏览器交互测试（仅当 Playwright 可用时运行）
# ========================================================================


@unittest.skipIf(not HAS_PLAYWRIGHT, "需要 Playwright 才能运行")
class TestAiConfigUiPlaywright(unittest.TestCase):
    """浏览器级 UI 测试，需要 Playwright 和本地服务。"""

    @classmethod
    def setUpClass(cls):
        if not HAS_PLAYWRIGHT:
            return
        cls.tmpdir = tempfile.mkdtemp(prefix='ai_config_ui_')
        cls.source_dir = os.path.join(cls.tmpdir, 'source')
        cls.log_dir = os.path.join(cls.tmpdir, 'logs')
        cls.recycle_dir = os.path.join(cls.tmpdir, 'recycle')
        for d in [cls.source_dir, cls.log_dir, cls.recycle_dir]:
            os.makedirs(d, exist_ok=True)

        config_yaml = f"""source_dir: {cls.source_dir}
log_dir: {cls.log_dir}
source_policy:
  recycle_dir: {cls.recycle_dir}
llm:
  api_key: test-key
  model: test-model
  base_url: https://api.test.example/v1
  max_retries: 1
  retry_delay: 0
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

    def _navigate_to_ai_config(self, page):
        page.locator(".bottom-nav [data-nav='config']").click()
        time.sleep(0.5)
        page.evaluate("setConfigStage('ai')")
        time.sleep(0.5)

    def test_llm_advanced_disclosure_default_collapsed(self):
        """LLM 是后台整理中的高级可选项，默认不制造配置负担。"""
        with sync_playwright() as p:
            browser, page = self._open_page(p)
            try:
                self._navigate_to_ai_config(page)
                disclosure = page.locator("#automation-llm-disclosure")
                self.assertFalse(disclosure.get_attribute("open") is not None)
                self.assertFalse(page.locator("#cfg-llm-base_url").is_visible())
            finally:
                browser.close()

    def test_llm_connection_fields_are_available_after_expanding(self):
        """展开高级项后可配置唯一 LLM 连接。"""
        with sync_playwright() as p:
            browser, page = self._open_page(p)
            try:
                self._navigate_to_ai_config(page)
                page.locator("#automation-llm-disclosure").evaluate("element => { element.open = true; }")
                for field_id in ["cfg-llm-base_url", "cfg-llm-model", "cfg-llm-api_key"]:
                    self.assertEqual(page.locator(f"#{field_id}").count(), 1)
            finally:
                browser.close()

    def test_llm_connectivity_feedback_stays_inside_the_disclosure(self):
        """连接测试结果在当前配置区域内就地反馈。"""
        with sync_playwright() as p:
            browser, page = self._open_page(p)
            try:
                self._navigate_to_ai_config(page)
                self.assertEqual(page.locator("[data-llm-test]").count(), 1)
                feedback = page.locator("#llm-test-result")
                self.assertEqual(feedback.get_attribute("role"), "status")
                self.assertEqual(feedback.get_attribute("aria-live"), "polite")
            finally:
                browser.close()

    def test_background_polling_controls_remain_primary(self):
        """后台运行开关和轮询周期是本阶段的基础设置。"""
        with sync_playwright() as p:
            browser, page = self._open_page(p)
            try:
                self._navigate_to_ai_config(page)
                self.assertEqual(page.locator("#cfg-auto-watcher-enabled").count(), 1)
                self.assertEqual(page.locator("#cfg-auto-watcher-poll-interval").count(), 1)
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
