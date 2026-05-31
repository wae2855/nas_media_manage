import unittest
from playwright.sync_api import sync_playwright

BASE_URL = 'http://localhost:9855'
API_KEY = 'oppenssl-11'


class TestConfidenceConfigUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def _open_confidence_tab(self):
        page = self.browser.new_page()
        page.add_init_script(f"window.localStorage.setItem('nas_api_key', '{API_KEY}');")
        page.goto(BASE_URL)
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)
        page.evaluate("switchTab('config')")
        page.wait_for_timeout(400)
        page.evaluate("switchConfigSubTab('confidence')")
        page.wait_for_timeout(1500)
        modal = page.locator('#api-key-modal')
        if modal.count() > 0 and modal.is_visible():
            page.evaluate("document.getElementById('api-key-modal').style.display='none'")
        return page

    def test_confidence_section_save_buttons(self):
        page = self._open_confidence_tab()
        try:
            buttons = page.locator('.cfg-section-save').all()
            self.assertGreaterEqual(len(buttons), 5, 'Should have at least 5 section save buttons')
            visible_count = 0
            for btn in buttons:
                if btn.is_visible():
                    visible_count += 1
            self.assertGreaterEqual(visible_count, 1, 'At least 1 save button should be visible')
        finally:
            page.close()

    def test_confidence_save_no_error(self):
        page = self._open_confidence_tab()
        try:
            section = page.locator('[data-section="confidence"]')
            first_section_header = section.locator('.cfg-section-header').first
            first_section_header.click()
            page.wait_for_timeout(300)
            first_btn = section.locator('.cfg-section-save').first
            if first_btn.is_visible():
                first_btn.click()
                page.wait_for_timeout(2000)
                toast = page.locator('.toast')
                if toast.count() > 0:
                    msg = toast.first.inner_text()
                    self.assertNotIn('未知', msg, f'Save should not return unknown section, got: {msg}')
        finally:
            page.close()

    def test_help_trigger_on_source_confidence(self):
        page = self._open_confidence_tab()
        try:
            page.evaluate("""
                var cards = document.querySelectorAll('.dim-card[data-dim]');
                cards.forEach(function(c) {
                    var header = c.querySelector('.dim-card-header');
                    if (header && !header.classList.contains('open')) header.click();
                });
            """)
            page.wait_for_timeout(500)
            triggers = page.locator('.help-trigger').all()
            found = False
            for t in triggers:
                tip = t.get_attribute('data-tooltip') or ''
                if '覆盖' in tip or '来源' in tip:
                    found = True
                    self.assertIn('置信度', tip, 'Tooltip should mention 置信度')
                    break
            self.assertTrue(found, 'Should find help-trigger for source confidence override')
        finally:
            page.close()

    def test_restricted_level_veto_default(self):
        page = self._open_confidence_tab()
        try:
            result = page.evaluate("""
                () => {
                    var card = document.querySelector('.dim-card[data-dim="restricted_level"]');
                    if (!card) return { found: false };
                    var header = card.querySelector('.dim-card-header');
                    if (header && !header.classList.contains('open')) {
                        header.click();
                    }
                    var body = card.querySelector('.conf-dim-card-body');
                    if (!body || !body.classList.contains('open')) return { found: true, open: false };
                    var veto = card.querySelector('input[data-dim-field="veto_threshold"]');
                    return { found: true, open: true, vetoValue: veto ? veto.value : null };
                }
            """)
            self.assertTrue(result.get('found'), 'restricted_level dimension should exist')
            if result.get('open'):
                self.assertEqual(result.get('vetoValue'), '0.9', 'restricted_level veto_threshold should default to 0.9')
        finally:
            page.close()

    def test_ai_consult_prompt_format(self):
        page = self._open_confidence_tab()
        try:
            page.evaluate("""
                var el = document.querySelector('[data-section="confidence"]');
                if (el) el.scrollTop = el.scrollHeight;
            """)
            page.wait_for_timeout(300)
            need_input = page.locator('#ai-consult-need')
            need_input.fill('我想从严控制限制级内容')
            page.evaluate("generateConsultPrompt()")
            page.wait_for_timeout(500)
            prompt_el = page.locator('#ai-consult-prompt')
            if prompt_el.count() > 0:
                text = prompt_el.inner_text()
                self.assertIn('配置清单', text, 'Prompt should have 配置清单 section')
                self.assertIn('调整原因', text, 'Prompt should have 调整原因 section')
                self.assertIn('示例计算过程', text, 'Prompt should have 示例计算过程 section')
                self.assertIn('区域.参数名 = 建议值', text, 'Prompt should explain the format')
                self.assertNotIn('```yaml', text, 'Prompt should NOT use YAML format for current config')
                self.assertIn('决策阈值.自动通过', text, 'Prompt should show example format')
        finally:
            page.close()

    def test_no_global_save_button(self):
        page = self._open_confidence_tab()
        try:
            section = page.locator('[data-section="confidence"]')
            old_btns = section.locator('.section-actions .btn-primary').all()
            for btn in old_btns:
                if btn.is_visible():
                    text = btn.inner_text()
                    self.assertNotEqual(text.strip(), '保存配置', 'Old global save button should be removed')
        finally:
            page.close()


if __name__ == '__main__':
    unittest.main()
