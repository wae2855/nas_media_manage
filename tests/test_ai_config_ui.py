"""AI 配置 UI 测试（覆盖 T3.4）。

需要本地服务运行和 Playwright 安装。如果不满足条件，测试自动跳过。
"""
import os
import sys
import tempfile
import shutil
import socket
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.api.handler import start_server
from media_importer.features.configuration import load_config
from media_importer.features.prompts.defaults import PromptDefaults

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

    def test_config_section_fields(self):
        """ai_assist section 字段结构正确。"""
        from media_importer.features.configuration import ConfigView
        cfg = {
            "ai_assist": {"base_url": "https://a.com", "model": "m", "api_key": "k"},
        }
        view = ConfigView.from_dict(cfg)
        self.assertEqual(view.ai_assist.base_url, "https://a.com")
        self.assertEqual(view.ai_assist.model, "m")
        self.assertEqual(view.ai_assist.api_key, "k")

    def test_config_apikey_masked_in_config_view(self):
        """ConfigView 保留原始 api_key（脱敏在 API 层处理）。"""
        from media_importer.features.configuration import ConfigView, mask_sensitive
        cfg = {
            "ai_assist": {"api_key": "my-secret-key"},
            "ai_search": {"api_key": "my-search-key"},
        }
        view = ConfigView.from_dict(cfg)
        masked = mask_sensitive(cfg)
        self.assertIn("***", masked["ai_assist"]["api_key"])
        self.assertIn("***", masked["ai_search"]["api_key"])

    def test_prompt_defaults_endpoint_structure(self):
        """PromptDefaults.get_all() 返回结构正确。"""
        data = PromptDefaults.get_all()
        self.assertIn("prompts", data)
        self.assertIn("descriptions", data)
        self.assertEqual(len(data["prompts"]), 5)

    def test_ai_scene_strategy_saved_correctly(self):
        """ai_scene_strategy 校验与回读正确。"""
        from media_importer.core.config_view import ConfigView
        cfg = {
            "ai_scene_strategy": {
                "dimension_supplement": {"primary": "ai_search", "fallback": ""},
                "dimension_mapping": {"primary": "ai_assist", "fallback": "ai_search"},
            },
        }
        view = ConfigView.from_dict(cfg)
        self.assertEqual(view.ai_scene_strategy.dimension_supplement.primary, "ai_search")
        self.assertEqual(view.ai_scene_strategy.dimension_mapping.fallback, "ai_search")


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
        cls.temp_dir = os.path.join(cls.tmpdir, 'temp')
        cls.log_dir = os.path.join(cls.tmpdir, 'logs')
        cls.recycle_dir = os.path.join(cls.tmpdir, 'recycle')
        for d in [cls.source_dir, cls.temp_dir, cls.log_dir, cls.recycle_dir]:
            os.makedirs(d, exist_ok=True)

        config_yaml = f"""source_dir: {cls.source_dir}
temp_dir: {cls.temp_dir}
log_dir: {cls.log_dir}
source_policy:
  recycle_dir: {cls.recycle_dir}
ai_assist:
  api_key: test-key
  model: test-model
  base_url: https://api.test.example/v1
  max_retries: 1
  retry_delay: 0
ai_search:
  enabled: true
  api_key: search-key
  model: search-model
  base_url: https://search.test.example/v1
  provider: zhipu
  search_type: search_std
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
        page.locator("#tab-config").click()
        time.sleep(0.5)
        page.locator("#cfg-subtab-ai").click()
        time.sleep(0.5)

    def test_three_accordion_default_collapsed(self):
        """进入 AI 配置页，3 个区域默认折叠。"""
        with sync_playwright() as p:
            browser, page = self._open_page(p)
            try:
                self._navigate_to_ai_config(page)
                for card_id in ["ai-apikey-card", "ai-prompts-card", "ai-scene-strategy-card"]:
                    body = page.locator(f"#{card_id} > .config-collapse-body")
                    is_visible = body.is_visible()
                    self.assertFalse(is_visible, f"{card_id} body 应默认折叠")
            finally:
                browser.close()

    def test_apikey_tab_switch(self):
        """API Key 区两个 tab 切换正常。"""
        with sync_playwright() as p:
            browser, page = self._open_page(p)
            try:
                self._navigate_to_ai_config(page)
                page.locator("#ai-apikey-card .config-collapse-header").click()
                time.sleep(0.3)
                page.locator("#ai-apikey-card .tab-btn[data-tab='ai_search']").click()
                time.sleep(0.2)
                search_panel = page.locator("#ai-apikey-card .tab-panel[data-tab='ai_search']")
                self.assertTrue(search_panel.is_visible())
            finally:
                browser.close()

    def test_prompts_five_tabs(self):
        """提示词区 5 个 tab 显示。"""
        with sync_playwright() as p:
            browser, page = self._open_page(p)
            try:
                self._navigate_to_ai_config(page)
                page.locator("#ai-prompts-card .config-collapse-header").click()
                time.sleep(0.3)
                count = page.locator("#ai-prompts-card .tab-bar .tab-btn").count()
                self.assertEqual(count, 5, "提示词区应有 5 个 tab")
            finally:
                browser.close()

    def test_scene_strategy_five_rows(self):
        """场景区 5 行配置完整显示。"""
        with sync_playwright() as p:
            browser, page = self._open_page(p)
            try:
                self._navigate_to_ai_config(page)
                page.locator("#ai-scene-strategy-card .config-collapse-header").click()
                time.sleep(0.3)
                count = page.locator("#ai-scene-strategy-card .strategy-row").count()
                self.assertEqual(count, 5, "场景区应有 5 行")
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
