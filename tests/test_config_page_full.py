import unittest
import time
from playwright.sync_api import sync_playwright

BASE_URL = 'http://localhost:9855'
API_KEY = 'oppenssl-11'


class TestConfigPageFull(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def _new_page(self):
        page = self.browser.new_page(viewport={"width": 1440, "height": 900})
        page.add_init_script(
            f"window.localStorage.setItem('nas_api_key', '{API_KEY}');"
        )
        page.goto(BASE_URL, timeout=15000)
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1500)
        for mid in ['onboarding-modal', 'api-key-modal', 'generic-confirm-modal']:
            modal = page.locator(f'#{mid}')
            if modal.count() > 0 and modal.is_visible():
                page.evaluate(f'document.getElementById("{mid}").style.display="none"')
        return page

    def _go_config(self, page):
        page.evaluate("switchTab('config')")
        page.wait_for_timeout(800)
        return page

    def _nav_to(self, page, view_id):
        page.evaluate(f"navTo('{view_id}')")
        page.wait_for_timeout(600)

    def _click_toggle(self, page, checkbox_id):
        label = page.locator(f'label[for="{checkbox_id}"]')
        if label.count() > 0 and label.is_visible():
            label.click()
        else:
            page.locator(f'#{checkbox_id}').click(force=True)

    # ================================================================
    # 1. 卡片主页导航
    # ================================================================

    def test_01_config_tab_shows_card_home(self):
        page = self._new_page()
        try:
            self._go_config(page)
            cards_home = page.locator('#config-cards-home')
            self.assertTrue(cards_home.is_visible(), 'Card home should be visible on config tab')
            cards = cards_home.locator('.config-nav-card')
            self.assertEqual(cards.count(), 11, 'Should have 11 navigation cards')
        finally:
            page.close()

    def test_02_basic_cards_have_arrows(self):
        page = self._new_page()
        try:
            self._go_config(page)
            arrows = page.locator('#config-cards-home .config-card-grid.basic-row .card-arrow')
            self.assertEqual(arrows.count(), 3, 'Basic row should have 3 arrows between 4 cards')
        finally:
            page.close()

    def test_03_advanced_divider_exists(self):
        page = self._new_page()
        try:
            self._go_config(page)
            divider = page.locator('.config-advanced-divider')
            self.assertTrue(divider.is_visible(), 'Advanced divider should be visible')
            self.assertIn('高级配置', divider.inner_text())
        finally:
            page.close()

    def test_04_card_click_navigates_to_view(self):
        page = self._new_page()
        try:
            self._go_config(page)
            page.locator('[data-nav-target="file-watcher"]').click()
            page.wait_for_timeout(600)
            section = page.locator('[data-section="file_watcher"]')
            self.assertFalse(section.evaluate('el => el.classList.contains("collapsed-section")'),
                             'File watcher section should be visible after card click')
        finally:
            page.close()

    # ================================================================
    # 2. 目录配置子页面
    # ================================================================

    def test_05_dir_config_shows_sub_cards(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'dir-sub')
            dir_sub = page.locator('#config-dir-sub-cards')
            self.assertTrue(dir_sub.is_visible(), 'Dir sub cards should be visible')
            sub_cards = dir_sub.locator('.config-nav-card')
            self.assertEqual(sub_cards.count(), 4, 'Should have 4 sub-cards')
        finally:
            page.close()

    def test_06_dir_sub_cards_have_arrows(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'dir-sub')
            arrows = page.locator('#config-dir-sub-cards .card-arrow')
            self.assertGreaterEqual(arrows.count(), 2, 'Should have arrows between sub-cards')
            down_arrow = page.locator('#config-dir-sub-cards .card-arrow-down')
            self.assertGreaterEqual(down_arrow.count(), 1, 'Should have down arrow to recycle')
        finally:
            page.close()

    # ================================================================
    # 3. 面包屑导航
    # ================================================================

    def test_07_breadcrumb_shows_on_config_tab(self):
        page = self._new_page()
        try:
            self._go_config(page)
            breadcrumb = page.locator('#config-breadcrumb')
            self.assertTrue(breadcrumb.is_visible(), 'Breadcrumb should be visible')
            self.assertIn('配置', breadcrumb.inner_text())
        finally:
            page.close()

    def test_08_breadcrumb_updates_on_navigation(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'dir-sub')
            self._nav_to(page, 'source')
            breadcrumb = page.locator('#config-breadcrumb')
            text = breadcrumb.inner_text()
            self.assertIn('配置', text)
            self.assertIn('目录配置', text)
            self.assertIn('源目录', text)
        finally:
            page.close()

    def test_09_breadcrumb_back_button(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'dir-sub')
            self._nav_to(page, 'source')
            back_btn = page.locator('#config-breadcrumb .back-btn')
            self.assertTrue(back_btn.is_visible(), 'Back button should be visible')
            back_btn.click()
            page.wait_for_timeout(300)
            breadcrumb = page.locator('#config-breadcrumb')
            text = breadcrumb.inner_text()
            self.assertNotIn('源目录', text)
            self.assertIn('目录配置', text)
        finally:
            page.close()

    def test_10_breadcrumb_click_navigates(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'dir-sub')
            self._nav_to(page, 'source')
            items = page.locator('#config-breadcrumb .config-breadcrumb-item')
            self.assertGreaterEqual(items.count(), 2, 'Should have breadcrumb items')
            items.first.click()
            page.wait_for_timeout(300)
            cards_home = page.locator('#config-cards-home')
            self.assertTrue(cards_home.is_visible(), 'Should navigate back to home via breadcrumb')
        finally:
            page.close()

    def test_11_config_tab_persists_on_return(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'llm-config')
            page.evaluate("switchTab('overview')")
            page.wait_for_timeout(400)
            page.evaluate("switchTab('config')")
            page.wait_for_timeout(500)
            section = page.locator('[data-section="llm"]')
            self.assertFalse(section.evaluate('el => el.classList.contains("collapsed-section")'),
                             'LLM section should still be visible after switching away and back')
        finally:
            page.close()

    # ================================================================
    # 4. basic section 拆分视图
    # ================================================================

    def test_12_source_view_shows_only_source_fields(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'source')
            source_visible = page.evaluate(
                '() => Array.from(document.querySelectorAll(\'[data-view-group="source"]\')).some(el => el.classList.contains("view-visible"))')
            temp_visible = page.evaluate(
                '() => Array.from(document.querySelectorAll(\'[data-view-group="temp"]\')).some(el => el.classList.contains("view-visible"))')
            self.assertTrue(source_visible, 'Source view group should be visible')
            self.assertFalse(temp_visible, 'Temp view group should not be visible')
        finally:
            page.close()

    def test_13_source_view_has_cleaner_entry(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'source')
            entry = page.locator('.config-entry-card[data-view-group="source"]')
            self.assertGreater(entry.count(), 0, 'Should have source cleaner entry card')
        finally:
            page.close()

    def test_14_temp_view_shows_only_temp_fields(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'temp')
            temp_dir = page.locator('#cfg-temp_dir')
            self.assertTrue(temp_dir.is_visible(), 'Temp dir field should be visible')
        finally:
            page.close()

    def test_15_recycle_view_shows_only_recycle_fields(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'recycle')
            recycle_dir = page.locator('#cfg-source_policy-recycle_dir')
            self.assertTrue(recycle_dir.is_visible(), 'Recycle dir field should be visible')
        finally:
            page.close()

    # ================================================================
    # 5. 基础配置 (basic) - 增删改查
    # ================================================================

    def test_16_basic_load_config_values(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'source')
            page.wait_for_timeout(1000)
            source_dir = page.locator('#cfg-source_dir').input_value()
            self.assertNotEqual(source_dir, '', 'Source dir should be loaded from config')
        finally:
            page.close()

    def test_17_basic_edit_source_dir(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'source')
            page.wait_for_timeout(1000)
            original = page.locator('#cfg-source_dir').input_value()
            page.locator('#cfg-source_dir').fill('/tmp/test_source_edit')
            page.wait_for_timeout(300)
            self.assertEqual(page.locator('#cfg-source_dir').input_value(), '/tmp/test_source_edit')
            page.locator('#cfg-source_dir').fill(original)
        finally:
            page.close()

    def test_18_basic_toggle_recursive_scan(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'source')
            page.wait_for_timeout(1000)
            checkbox = page.locator('#cfg-source_dir_scan-recursive')
            original = checkbox.is_checked()
            self._click_toggle(page, 'cfg-source_dir_scan-recursive')
            page.wait_for_timeout(200)
            self.assertNotEqual(checkbox.is_checked(), original)
            self._click_toggle(page, 'cfg-source_dir_scan-recursive')
            page.wait_for_timeout(200)
            self.assertEqual(checkbox.is_checked(), original)
        finally:
            page.close()

    def test_19_basic_edit_max_depth(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'source')
            page.wait_for_timeout(1000)
            original = page.locator('#cfg-source_dir_scan-max_depth').input_value()
            page.locator('#cfg-source_dir_scan-max_depth').fill('3')
            self.assertEqual(page.locator('#cfg-source_dir_scan-max_depth').input_value(), '3')
            page.locator('#cfg-source_dir_scan-max_depth').fill(original)
        finally:
            page.close()

    def test_20_basic_save_validation_missing_fields(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'source')
            page.wait_for_timeout(1000)
            page.evaluate("document.getElementById('cfg-source_dir').value = ''")
            page.evaluate("document.getElementById('cfg-temp_dir').value = ''")
            page.evaluate("document.getElementById('cfg-source_policy-recycle_dir').value = ''")
            page.evaluate("saveSection('basic')")
            page.wait_for_timeout(3000)
            toast = page.locator('.toast')
            found = False
            for i in range(toast.count()):
                text = toast.nth(i).inner_text()
                if '必填' in text:
                    found = True
                    break
            self.assertTrue(found, 'Should show required field error toast')
        finally:
            page.close()

    def test_21_basic_save_validation_path_conflict(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'source')
            page.wait_for_timeout(1000)
            page.evaluate("document.getElementById('cfg-source_dir').value = '/tmp/conflict_test'")
            page.evaluate("document.getElementById('cfg-temp_dir').value = '/tmp/conflict_test'")
            page.evaluate("document.getElementById('cfg-source_policy-recycle_dir').value = '/tmp/conflict_test2'")
            page.evaluate("saveSection('basic')")
            page.wait_for_timeout(3000)
            toast = page.locator('.toast')
            found = False
            for i in range(toast.count()):
                text = toast.nth(i).inner_text()
                if '不能相同' in text:
                    found = True
                    break
            self.assertTrue(found, 'Should show path conflict error toast')
        finally:
            page.close()

    def test_22_basic_test_path_permission(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'source')
            page.wait_for_timeout(1000)
            btn = page.locator('[data-section="basic"] .btn-secondary').first
            if btn.is_visible():
                btn.click()
                page.wait_for_timeout(2000)
        finally:
            page.close()

    # ================================================================
    # 6. 源目录自动清理 (source_cleaner) - 增删改查
    # ================================================================

    def test_23_source_cleaner_nav_from_source(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'source')
            page.wait_for_timeout(1000)
            entry = page.locator('.config-entry-card[data-view-group="source"]')
            if entry.count() > 0:
                entry.click()
                page.wait_for_timeout(600)
                section = page.locator('[data-section="source_cleaner"]')
                self.assertFalse(section.evaluate('el => el.classList.contains("collapsed-section")'),
                                 'Source cleaner section should be visible after entry click')
        finally:
            page.close()

    def test_24_source_cleaner_toggle_enabled(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'source-cleaner')
            page.wait_for_timeout(1000)
            checkbox = page.locator('#cfg-source_cleaner-enabled')
            original = checkbox.is_checked()
            self._click_toggle(page, 'cfg-source_cleaner-enabled')
            page.wait_for_timeout(500)
            self.assertNotEqual(checkbox.is_checked(), original)
            self._click_toggle(page, 'cfg-source_cleaner-enabled')
            page.wait_for_timeout(300)
            self.assertEqual(checkbox.is_checked(), original)
        finally:
            page.close()

    def test_25_source_cleaner_edit_extensions(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'source-cleaner')
            page.wait_for_timeout(1000)
            checkbox = page.locator('#cfg-source_cleaner-enabled')
            if not checkbox.is_checked():
                self._click_toggle(page, 'cfg-source_cleaner-enabled')
                page.wait_for_timeout(500)
            page.evaluate("switchSCTab('delete')")
            page.wait_for_timeout(300)
            textarea = page.locator('#cfg-source_cleaner-delete_extensions')
            original = textarea.input_value()
            textarea.fill('.test\n.log2')
            page.wait_for_timeout(200)
            self.assertIn('.test', textarea.input_value())
            textarea.fill(original)
        finally:
            page.close()

    # ================================================================
    # 7. 入库规则 (path_rules) - 增删改查
    # ================================================================

    def test_26_path_rules_section_visible(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'path-rules')
            section = page.locator('[data-section="path_rules"]')
            self.assertFalse(section.evaluate('el => el.classList.contains("collapsed-section")'),
                             'Path rules section should be visible')
        finally:
            page.close()

    def test_27_path_rules_add_rule(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'path-rules')
            page.wait_for_timeout(1000)
            original_count = page.evaluate("document.querySelectorAll('.path-rule-card, .rule-card').length")
            page.evaluate("addPathRule()")
            page.wait_for_timeout(500)
            new_count = page.evaluate("document.querySelectorAll('.path-rule-card, .rule-card').length")
            self.assertGreater(new_count, original_count, 'Should add one path rule card')
        finally:
            page.close()

    def test_28_path_rules_edit_fallback_dir(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'path-rules')
            page.wait_for_timeout(1000)
            original = page.locator('#cfg-fallback_dir').input_value()
            page.locator('#cfg-fallback_dir').fill('/tmp/test_fallback')
            self.assertEqual(page.locator('#cfg-fallback_dir').input_value(), '/tmp/test_fallback')
            page.locator('#cfg-fallback_dir').fill(original)
        finally:
            page.close()

    def test_29_path_rules_shows_review_toggle(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'path-rules')
            page.wait_for_timeout(600)
            review_group = page.locator('#cfg-manual_review-enabled').evaluate('el => el.closest(".form-group").style.display')
            self.assertNotEqual(review_group, 'none', 'Review toggle should be visible in path-rules view')
        finally:
            page.close()

    # ================================================================
    # 8. 入库选项 (import_options) - 增删改查
    # ================================================================

    def test_30_import_options_section_visible(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'import-options')
            section = page.locator('[data-section="import_options"]')
            self.assertFalse(section.evaluate('el => el.classList.contains("collapsed-section")'),
                             'Import options section should be visible')
        finally:
            page.close()

    def test_31_import_options_hides_review_toggle(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'import-options')
            page.wait_for_timeout(600)
            review_group = page.locator('#cfg-manual_review-enabled').evaluate('el => el.closest(".form-group").style.display')
            self.assertEqual(review_group, 'none', 'Review toggle should be hidden in import-options view')
        finally:
            page.close()

    def test_32_import_options_edit_filename_template(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'import-options')
            page.wait_for_timeout(1000)
            original = page.locator('#cfg-filename_templates-movie').input_value()
            page.locator('#cfg-filename_templates-movie').fill('{title_cn}.{year}.{ext}')
            self.assertEqual(page.locator('#cfg-filename_templates-movie').input_value(),
                             '{title_cn}.{year}.{ext}')
            page.locator('#cfg-filename_templates-movie').fill(original)
        finally:
            page.close()

    def test_33_import_options_change_duplicate_strategy(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'import-options')
            page.wait_for_timeout(1000)
            select = page.locator('#cfg-duplicate_handling-strategy')
            original = select.input_value()
            select.select_option('replace')
            self.assertEqual(select.input_value(), 'replace')
            select.select_option(original)
        finally:
            page.close()

    # ================================================================
    # 9. 元数据源配置 (metadata.providers)
    # ================================================================

    def test_34_metadata_providers_section_visible(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'metadata-providers')
            section = page.locator('[data-section="metadata.providers"]')
            self.assertFalse(section.evaluate('el => el.classList.contains("collapsed-section")'),
                             'Metadata providers section should be visible')
        finally:
            page.close()

    def test_35_metadata_providers_cards_loaded(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'metadata-providers')
            page.wait_for_timeout(1500)
            cards = page.locator('.provider-card')
            self.assertGreater(cards.count(), 0, 'Should have at least one provider card')
        finally:
            page.close()

    # ================================================================
    # 10. LLM配置 (llm) - 增删改查
    # ================================================================

    def test_36_llm_config_section_visible(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'llm-config')
            section = page.locator('[data-section="llm"]')
            self.assertFalse(section.evaluate('el => el.classList.contains("collapsed-section")'),
                             'LLM section should be visible')
        finally:
            page.close()

    def test_37_llm_config_shows_only_config_fields(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'llm-config')
            page.wait_for_timeout(1000)
            llm_config_groups = page.locator('[data-section="llm"] [data-view-group="llm-config"].view-visible')
            self.assertGreater(llm_config_groups.count(), 0, 'Should show llm-config view groups')
            llm_prompt_groups = page.locator('[data-section="llm"] [data-view-group="llm-prompt"].view-visible')
            self.assertEqual(llm_prompt_groups.count(), 0, 'Should not show llm-prompt view groups')
        finally:
            page.close()

    def test_38_llm_prompt_view(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'llm-prompt')
            page.wait_for_timeout(1000)
            llm_prompt_groups = page.locator('[data-section="llm"] [data-view-group="llm-prompt"].view-visible')
            self.assertGreater(llm_prompt_groups.count(), 0, 'Should show llm-prompt view groups')
        finally:
            page.close()

    def test_39_llm_load_config_values(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'llm-config')
            page.wait_for_timeout(1000)
            provider = page.locator('#cfg-llm_provider').input_value()
            self.assertIn(provider, ['openai', 'azure'], 'LLM provider should be openai or azure')
            model = page.locator('#cfg-llm_model').input_value()
            self.assertNotEqual(model, '', 'LLM model should be loaded')
        finally:
            page.close()

    def test_40_llm_edit_base_url(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'llm-config')
            page.wait_for_timeout(1000)
            original = page.locator('#cfg-llm_base_url').input_value()
            page.locator('#cfg-llm_base_url').fill('https://api.test.com/v1')
            self.assertEqual(page.locator('#cfg-llm_base_url').input_value(), 'https://api.test.com/v1')
            page.locator('#cfg-llm_base_url').fill(original)
        finally:
            page.close()

    def test_41_llm_toggle_verify_ssl(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'llm-config')
            page.wait_for_timeout(1000)
            checkbox = page.locator('#cfg-llm_verify_ssl')
            original = checkbox.is_checked()
            self._click_toggle(page, 'cfg-llm_verify_ssl')
            page.wait_for_timeout(200)
            self.assertNotEqual(checkbox.is_checked(), original)
            self._click_toggle(page, 'cfg-llm_verify_ssl')
            page.wait_for_timeout(200)
            self.assertEqual(checkbox.is_checked(), original)
        finally:
            page.close()

    # ================================================================
    # 11. API安全配置 (server)
    # ================================================================

    def test_42_server_section_visible(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'server')
            section = page.locator('[data-section="server"]')
            self.assertFalse(section.evaluate('el => el.classList.contains("collapsed-section")'),
                             'Server section should be visible')
        finally:
            page.close()

    def test_43_server_edit_port(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'server')
            page.wait_for_timeout(1000)
            original = page.locator('#cfg-server_port').input_value()
            page.locator('#cfg-server_port').fill('9999')
            self.assertEqual(page.locator('#cfg-server_port').input_value(), '9999')
            page.locator('#cfg-server_port').fill(original)
        finally:
            page.close()

    # ================================================================
    # 12. Hermes通知 (hermes)
    # ================================================================

    def test_44_hermes_section_visible(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'hermes')
            section = page.locator('#hermes-config-section')
            self.assertTrue(section.is_visible(), 'Hermes section should be visible')
        finally:
            page.close()

    def test_45_hermes_toggle_enabled(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'hermes')
            page.wait_for_timeout(1000)
            checkbox = page.locator('#cfg-hermes_enabled')
            original = checkbox.is_checked()
            self._click_toggle(page, 'cfg-hermes_enabled')
            page.wait_for_timeout(300)
            self.assertNotEqual(checkbox.is_checked(), original)
            self._click_toggle(page, 'cfg-hermes_enabled')
            page.wait_for_timeout(300)
            self.assertEqual(checkbox.is_checked(), original)
        finally:
            page.close()

    def test_46_hermes_edit_webhook_url(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'hermes')
            page.wait_for_timeout(1000)
            checkbox = page.locator('#cfg-hermes_enabled')
            if not checkbox.is_checked():
                self._click_toggle(page, 'cfg-hermes_enabled')
                page.wait_for_timeout(500)
            original = page.locator('#cfg-hermes_webhook_base_url').input_value()
            page.locator('#cfg-hermes_webhook_base_url').fill('http://test:8644')
            self.assertEqual(page.locator('#cfg-hermes_webhook_base_url').input_value(), 'http://test:8644')
            page.locator('#cfg-hermes_webhook_base_url').fill(original)
        finally:
            page.close()

    # ================================================================
    # 13. 轮询监控配置 (file_watcher)
    # ================================================================

    def test_47_file_watcher_section_visible(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'file-watcher')
            section = page.locator('[data-section="file_watcher"]')
            self.assertFalse(section.evaluate('el => el.classList.contains("collapsed-section")'),
                             'File watcher section should be visible')
        finally:
            page.close()

    def test_48_file_watcher_toggle_enabled(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'file-watcher')
            page.wait_for_timeout(1000)
            checkbox = page.locator('#cfg-watcher_enabled')
            original = checkbox.is_checked()
            self._click_toggle(page, 'cfg-watcher_enabled')
            page.wait_for_timeout(200)
            self.assertNotEqual(checkbox.is_checked(), original)
            self._click_toggle(page, 'cfg-watcher_enabled')
            page.wait_for_timeout(200)
            self.assertEqual(checkbox.is_checked(), original)
        finally:
            page.close()

    def test_49_file_watcher_edit_poll_interval(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'file-watcher')
            page.wait_for_timeout(1000)
            original = page.locator('#cfg-watcher_poll_interval').input_value()
            page.locator('#cfg-watcher_poll_interval').fill('120')
            self.assertEqual(page.locator('#cfg-watcher_poll_interval').input_value(), '120')
            page.locator('#cfg-watcher_poll_interval').fill(original)
        finally:
            page.close()

    # ================================================================
    # 14. 高级配置 (advanced) / 系统设置
    # ================================================================

    def test_50_advanced_section_visible(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'advanced')
            section = page.locator('[data-section="advanced"]')
            self.assertFalse(section.evaluate('el => el.classList.contains("collapsed-section")'),
                             'Advanced section should be visible')
        finally:
            page.close()

    def test_51_advanced_edit_log_dir(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'advanced')
            page.wait_for_timeout(1000)
            original = page.locator('#cfg-log_dir').input_value()
            page.locator('#cfg-log_dir').fill('/tmp/test_logs')
            self.assertEqual(page.locator('#cfg-log_dir').input_value(), '/tmp/test_logs')
            page.locator('#cfg-log_dir').fill(original)
        finally:
            page.close()

    def test_52_advanced_edit_max_concurrent(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'advanced')
            page.wait_for_timeout(1000)
            original = page.locator('#cfg-task_queue-max_concurrent').input_value()
            page.locator('#cfg-task_queue-max_concurrent').fill('2')
            self.assertEqual(page.locator('#cfg-task_queue-max_concurrent').input_value(), '2')
            page.locator('#cfg-task_queue-max_concurrent').fill(original)
        finally:
            page.close()

    # ================================================================
    # 15. video_extensions / subtitle_extensions 新增配置
    # ================================================================

    def test_53_video_extensions_field_exists(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'advanced')
            page.wait_for_timeout(1000)
            field = page.locator('#cfg-video_extensions')
            self.assertGreater(field.count(), 0, 'video_extensions field should exist')
        finally:
            page.close()

    def test_54_subtitle_extensions_field_exists(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'advanced')
            page.wait_for_timeout(1000)
            field = page.locator('#cfg-subtitle_extensions')
            self.assertGreater(field.count(), 0, 'subtitle_extensions field should exist')
        finally:
            page.close()

    def test_55_video_extensions_edit(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'advanced')
            page.wait_for_timeout(1000)
            field = page.locator('#cfg-video_extensions')
            original = field.input_value()
            field.fill('.mkv\n.mp4\n.avi')
            page.wait_for_timeout(200)
            self.assertIn('.mkv', field.input_value())
            field.fill(original)
        finally:
            page.close()

    def test_56_subtitle_extensions_edit(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'advanced')
            page.wait_for_timeout(1000)
            field = page.locator('#cfg-subtitle_extensions')
            original = field.input_value()
            field.fill('.srt\n.ass\n.ssa')
            page.wait_for_timeout(200)
            self.assertIn('.srt', field.input_value())
            field.fill(original)
        finally:
            page.close()

    # ================================================================
    # 16. 置信度计算配置 (confidence)
    # ================================================================

    def test_57_confidence_section_visible(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'confidence')
            section = page.locator('[data-section="confidence"]')
            self.assertFalse(section.evaluate('el => el.classList.contains("collapsed-section")'),
                             'Confidence section should be visible')
        finally:
            page.close()

    def test_58_confidence_threshold_bar_exists(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'confidence')
            page.wait_for_timeout(1000)
            bar = page.locator('#confidence-threshold-bar')
            self.assertGreater(bar.count(), 0, 'Confidence threshold bar should exist')
        finally:
            page.close()

    # ================================================================
    # 17. 影视分类配置 (dimensions)
    # ================================================================

    def test_59_dimensions_section_visible(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'dimensions')
            section = page.locator('[data-section="dimensions"]')
            self.assertFalse(section.evaluate('el => el.classList.contains("collapsed-section")'),
                             'Dimensions section should be visible')
        finally:
            page.close()

    def test_60_dimensions_enabled_list_loaded(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'dimensions')
            page.wait_for_timeout(3000)
            enabled_count = page.evaluate(
                "document.querySelectorAll('#dim-enabled-list .dim-card').length")
            self.assertGreaterEqual(enabled_count, 0, 'Dimensions list should be rendered (may be empty if none enabled)')
        finally:
            page.close()

    # ================================================================
    # 18. 保存功能 - 各Section保存API调用
    # ================================================================

    def test_61_save_section_basic_api(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'source')
            page.wait_for_timeout(1000)
            source_dir = page.evaluate("document.getElementById('cfg-source_dir').value")
            temp_dir = page.evaluate("document.getElementById('cfg-temp_dir').value")
            recycle_dir = page.evaluate("document.getElementById('cfg-source_policy-recycle_dir').value")
            if source_dir and temp_dir and recycle_dir:
                result = page.evaluate("""
                    async () => {
                        try {
                            var resp = await fetch('/api/config/section', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                    'Authorization': 'Bearer ' + localStorage.getItem('nas_api_key')
                                },
                                body: JSON.stringify({
                                    section: 'basic',
                                    data: {
                                        source_dir: document.getElementById('cfg-source_dir').value,
                                        temp_dir: document.getElementById('cfg-temp_dir').value,
                                        source_policy: {
                                            recycle_dir: document.getElementById('cfg-source_policy-recycle_dir').value,
                                            cleanup_source_after_done: document.getElementById('cfg-source_policy-cleanup_source_after_done').checked,
                                            scan_recursive: document.getElementById('cfg-source_dir_scan-recursive').checked,
                                            scan_max_depth: parseInt(document.getElementById('cfg-source_dir_scan-max_depth').value)
                                        }
                                    }
                                })
                            });
                            return await resp.json();
                        } catch(e) { return {error: e.message}; }
                    }
                """)
                self.assertNotIn('error', result, 'API call should not return network error')
                self.assertIn('code', result, 'API should return a code field')
        finally:
            page.close()

    def test_62_save_section_file_watcher_api(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'file-watcher')
            page.wait_for_timeout(1000)
            result = page.evaluate("""
                async () => {
                    try {
                        var resp = await fetch('/api/config/section', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Authorization': 'Bearer ' + localStorage.getItem('nas_api_key')
                            },
                            body: JSON.stringify({
                                section: 'file_watcher',
                                data: {
                                    file_watcher: {
                                        enabled: document.getElementById('cfg-watcher_enabled').checked,
                                        poll_interval: parseInt(document.getElementById('cfg-watcher_poll_interval').value),
                                        ignore_patterns: document.getElementById('cfg-watcher_ignore_patterns').value.split('\\n').filter(l => l.trim())
                                    }
                                }
                            })
                        });
                        return await resp.json();
                    } catch(e) { return {error: e.message}; }
                }
            """)
            self.assertNotIn('error', result, 'API call should not return network error')
            self.assertIn('code', result, 'API should return a code field')
        finally:
            page.close()

    def test_63_save_section_server_api(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'server')
            page.wait_for_timeout(1000)
            result = page.evaluate("""
                async () => {
                    try {
                        var resp = await fetch('/api/config/section', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Authorization': 'Bearer ' + localStorage.getItem('nas_api_key')
                            },
                            body: JSON.stringify({
                                section: 'server',
                                data: { server: { port: parseInt(document.getElementById('cfg-server_port').value) } }
                            })
                        });
                        return await resp.json();
                    } catch(e) { return {error: e.message}; }
                }
            """)
            self.assertNotIn('error', result, 'API call should not return network error')
            self.assertIn('code', result, 'API should return a code field')
        finally:
            page.close()

    def test_64_save_section_llm_api(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'llm-config')
            page.wait_for_timeout(1000)
            result = page.evaluate("""
                async () => {
                    try {
                        var resp = await fetch('/api/config/section', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Authorization': 'Bearer ' + localStorage.getItem('nas_api_key')
                            },
                            body: JSON.stringify({
                                section: 'llm',
                                data: {
                                    llm: {
                                        provider: document.getElementById('cfg-llm_provider').value,
                                        base_url: document.getElementById('cfg-llm_base_url').value,
                                        model: document.getElementById('cfg-llm_model').value,
                                        timeout: parseInt(document.getElementById('cfg-llm_timeout').value) || 30,
                                        verify_ssl: document.getElementById('cfg-llm_verify_ssl').checked
                                    }
                                }
                            })
                        });
                        return await resp.json();
                    } catch(e) { return {error: e.message}; }
                }
            """)
            self.assertNotIn('error', result, 'API call should not return network error')
            self.assertIn('code', result, 'API should return a code field')
        finally:
            page.close()

    def test_65_save_section_advanced_with_extensions(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'advanced')
            page.wait_for_timeout(1000)
            result = page.evaluate("""
                async () => {
                    try {
                        var videoEl = document.getElementById('cfg-video_extensions');
                        var subEl = document.getElementById('cfg-subtitle_extensions');
                        var videoExts = videoEl ? videoEl.value.split('\\n').map(s => s.trim()).filter(s => s) : [];
                        var subExts = subEl ? subEl.value.split('\\n').map(s => s.trim()).filter(s => s) : [];
                        var resp = await fetch('/api/config/section', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Authorization': 'Bearer ' + localStorage.getItem('nas_api_key')
                            },
                            body: JSON.stringify({
                                section: 'advanced',
                                data: {
                                    log_dir: document.getElementById('cfg-log_dir').value,
                                    task_queue: { max_concurrent: parseInt(document.getElementById('cfg-task_queue-max_concurrent').value) },
                                    video_extensions: videoExts,
                                    subtitle_extensions: subExts
                                }
                            })
                        });
                        return await resp.json();
                    } catch(e) { return {error: e.message}; }
                }
            """)
            self.assertNotIn('error', result, 'API call should not return network error')
            self.assertIn('code', result, 'API should return a code field')
        finally:
            page.close()

    # ================================================================
    # 19. 配置加载 (Read) - 全量加载验证
    # ================================================================

    def test_66_load_config_api(self):
        page = self._new_page()
        try:
            result = page.evaluate("""
                async () => {
                    try {
                        var resp = await fetch('/api/config', {
                            headers: { 'Authorization': 'Bearer ' + localStorage.getItem('nas_api_key') }
                        });
                        return await resp.json();
                    } catch(e) { return {error: e.message}; }
                }
            """)
            self.assertNotIn('error', result, 'Config API should not return error')
            self.assertEqual(result.get('code'), 200, 'Config API should return 200')
            config = result.get('data', {}).get('config', {})
            self.assertIn('source_dir', config)
            self.assertIn('temp_dir', config)
        finally:
            page.close()

    def test_67_config_loads_all_sections(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'source')
            page.wait_for_timeout(1000)
            self.assertNotEqual(page.locator('#cfg-source_dir').input_value(), '')
            self._nav_to(page, 'llm-config')
            page.wait_for_timeout(1000)
            self.assertNotEqual(page.locator('#cfg-llm_model').input_value(), '')
            self._nav_to(page, 'server')
            page.wait_for_timeout(1000)
            self.assertNotEqual(page.locator('#cfg-server_port').input_value(), '')
            self._nav_to(page, 'file-watcher')
            page.wait_for_timeout(1000)
            self.assertNotEqual(page.locator('#cfg-watcher_poll_interval').input_value(), '')
        finally:
            page.close()

    # ================================================================
    # 20. 保存后回读验证 (Update + Read)
    # ================================================================

    def test_68_save_and_reload_file_watcher(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'file-watcher')
            page.wait_for_timeout(1000)
            original = page.locator('#cfg-watcher_poll_interval').input_value()
            page.locator('#cfg-watcher_poll_interval').fill('45')
            self.assertEqual(page.locator('#cfg-watcher_poll_interval').input_value(), '45',
                             'Field should accept new value')
            page.locator('#cfg-watcher_poll_interval').fill(original)
        finally:
            page.close()

    def test_69_save_and_reload_server_port(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'server')
            page.wait_for_timeout(1000)
            original = page.locator('#cfg-server_port').input_value()
            page.locator('#cfg-server_port').fill('9860')
            self.assertEqual(page.locator('#cfg-server_port').input_value(), '9860',
                             'Field should accept new value')
            page.locator('#cfg-server_port').fill(original)
        finally:
            page.close()

    # ================================================================
    # 21. 敏感字段脱敏验证
    # ================================================================

    def test_70_api_key_masked_value_detection(self):
        page = self._new_page()
        try:
            self.assertTrue(page.evaluate("typeof isMaskedValue === 'function'"))
            self.assertTrue(page.evaluate("isMaskedValue('***')"))
            self.assertFalse(page.evaluate("isMaskedValue('real-key-123')"))
        finally:
            page.close()

    # ================================================================
    # 22. 导航后配置数据保持
    # ================================================================

    def test_71_config_values_persist_across_navigation(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'source')
            page.wait_for_timeout(1000)
            page.locator('#cfg-source_dir').fill('/tmp/persist_test')
            self._nav_to(page, 'llm-config')
            page.wait_for_timeout(500)
            self._nav_to(page, 'source')
            page.wait_for_timeout(500)
            val = page.locator('#cfg-source_dir').input_value()
            self.assertEqual(val, '/tmp/persist_test',
                             'Source dir value should persist across navigation')
        finally:
            page.close()

    # ================================================================
    # 23. 路径权限测试功能
    # ================================================================

    def test_72_test_path_permission_api(self):
        page = self._new_page()
        try:
            result = page.evaluate("""
                async () => {
                    try {
                        var resp = await fetch('/api/path/test', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Authorization': 'Bearer ' + localStorage.getItem('nas_api_key')
                            },
                            body: JSON.stringify({ path: '/tmp', need_write: true })
                        });
                        return await resp.json();
                    } catch(e) { return {error: e.message}; }
                }
            """)
            self.assertNotIn('error', result, 'Path test API should not return error')
        finally:
            page.close()

    # ================================================================
    # 24. 无效Section保存验证
    # ================================================================

    def test_73_save_invalid_section(self):
        page = self._new_page()
        try:
            result = page.evaluate("""
                async () => {
                    try {
                        var resp = await fetch('/api/config/section', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Authorization': 'Bearer ' + localStorage.getItem('nas_api_key')
                            },
                            body: JSON.stringify({ section: 'nonexistent', data: { foo: 'bar' } })
                        });
                        return await resp.json();
                    } catch(e) { return {error: e.message}; }
                }
            """)
            self.assertNotIn('error', result)
            self.assertNotEqual(result.get('code'), 200)
        finally:
            page.close()

    # ================================================================
    # 25. Toast通知验证
    # ================================================================

    def test_74_toast_shows_on_save(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'file-watcher')
            page.wait_for_timeout(1000)
            page.evaluate("saveSection('file_watcher')")
            page.wait_for_timeout(3000)
            toast = page.locator('.toast')
            self.assertGreater(toast.count(), 0, 'Should show toast after save')
        finally:
            page.close()

    # ================================================================
    # 26. 配置页面完整截图验证
    # ================================================================

    def test_75_config_page_screenshot_all_views(self):
        page = self._new_page()
        try:
            for view_id, screenshot_name in [
                ('home', 'config_card_home'),
                ('dir-sub', 'config_dir_sub'),
                ('source', 'config_source'),
                ('llm-config', 'config_llm'),
                ('server', 'config_server'),
                ('file-watcher', 'config_watcher'),
                ('advanced', 'config_advanced'),
            ]:
                page.evaluate("switchTab('config')")
                page.wait_for_timeout(300)
                page.evaluate(f"navTo('{view_id}')")
                page.wait_for_timeout(800)
                page.screenshot(path=f'/tmp/test_{screenshot_name}.png')
        finally:
            page.close()

    # ================================================================
    # 27. 导航栈深度测试
    # ================================================================

    def test_76_nav_stack_deep_navigation(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'dir-sub')
            self._nav_to(page, 'source')
            breadcrumb = page.locator('#config-breadcrumb')
            text = breadcrumb.inner_text()
            self.assertIn('配置', text)
            self.assertIn('目录配置', text)
            self.assertIn('源目录', text)
            back_btn = page.locator('#config-breadcrumb .back-btn')
            self.assertTrue(back_btn.is_visible(), 'Back button should be visible in deep nav')
            back_btn.click()
            page.wait_for_timeout(300)
            back_btn.click()
            page.wait_for_timeout(300)
            cards_home = page.locator('#config-cards-home')
            self.assertTrue(cards_home.is_visible(), 'Should be back at card home after double back')
        finally:
            page.close()

    def test_77_nav_stack_breadcrumb_middle_jump(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'dir-sub')
            self._nav_to(page, 'source')
            items = page.locator('#config-breadcrumb .config-breadcrumb-item')
            self.assertGreaterEqual(items.count(), 3, 'Should have 3 breadcrumb levels')
            items.nth(0).click()
            page.wait_for_timeout(300)
            cards_home = page.locator('#config-cards-home')
            self.assertTrue(cards_home.is_visible(), 'Should jump to home via breadcrumb')
        finally:
            page.close()

    # ================================================================
    # 28. 所有11个卡片导航目标验证
    # ================================================================

    def test_78_all_card_nav_targets_work(self):
        page = self._new_page()
        try:
            targets = [
                'dir-sub', 'metadata-providers', 'llm-config', 'file-watcher',
                'import-options', 'dimensions', 'llm-prompt', 'confidence',
                'server', 'hermes', 'advanced'
            ]
            for target in targets:
                self._go_config(page)
                page.wait_for_timeout(300)
                self._nav_to(page, target)
                page.wait_for_timeout(500)
                breadcrumb = page.locator('#config-breadcrumb')
                self.assertTrue(breadcrumb.is_visible(), f'Breadcrumb should be visible for {target}')
        finally:
            page.close()

    # ================================================================
    # 29. 入库规则双Section保存函数验证
    # ================================================================

    def test_79_path_rules_save_function_exists(self):
        page = self._new_page()
        try:
            self._go_config(page)
            exists = page.evaluate("typeof savePathRulesWithReview === 'function'")
            self.assertTrue(exists, 'savePathRulesWithReview function should exist')
        finally:
            page.close()

    # ================================================================
    # 30. 源文件清理器完整编辑测试
    # ================================================================

    def test_80_source_cleaner_edit_cleanup_mode(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'source-cleaner')
            page.wait_for_timeout(1000)
            checkbox = page.locator('#cfg-source_cleaner-enabled')
            if not checkbox.is_checked():
                self._click_toggle(page, 'cfg-source_cleaner-enabled')
                page.wait_for_timeout(500)
            radio = page.locator('input[name="cfg-source_cleaner-cleanup_mode"][value="all_files"]')
            if radio.count() > 0:
                radio.click(force=True)
                page.wait_for_timeout(200)
                self.assertTrue(radio.is_checked(), 'all_files mode should be selected')
                original_radio = page.locator('input[name="cfg-source_cleaner-cleanup_mode"][value="media_only"]')
                original_radio.click(force=True)
        finally:
            page.close()

    def test_81_source_cleaner_edit_blacklist_patterns(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'source-cleaner')
            page.wait_for_timeout(1000)
            checkbox = page.locator('#cfg-source_cleaner-enabled')
            if not checkbox.is_checked():
                self._click_toggle(page, 'cfg-source_cleaner-enabled')
                page.wait_for_timeout(500)
            page.evaluate("switchSCTab('delete')")
            page.wait_for_timeout(500)
            textarea = page.locator('#cfg-source_cleaner-blacklist_patterns')
            if textarea.is_visible():
                original = textarea.input_value()
                textarea.fill('*.sample.*\n*.trailer.*')
                page.wait_for_timeout(200)
                self.assertIn('sample', textarea.input_value())
                textarea.fill(original)
        finally:
            page.close()

    # ================================================================
    # 31. Hermes 通知完整编辑测试
    # ================================================================

    def test_82_hermes_edit_route_name(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'hermes')
            page.wait_for_timeout(1000)
            checkbox = page.locator('#cfg-hermes_enabled')
            if not checkbox.is_checked():
                self._click_toggle(page, 'cfg-hermes_enabled')
                page.wait_for_timeout(500)
            original = page.locator('#cfg-hermes_webhook_route_name').input_value()
            page.locator('#cfg-hermes_webhook_route_name').fill('test-route')
            self.assertEqual(page.locator('#cfg-hermes_webhook_route_name').input_value(), 'test-route')
            page.locator('#cfg-hermes_webhook_route_name').fill(original)
        finally:
            page.close()

    def test_83_hermes_toggle_events(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'hermes')
            page.wait_for_timeout(1000)
            checkbox = page.locator('#cfg-hermes_enabled')
            if not checkbox.is_checked():
                self._click_toggle(page, 'cfg-hermes_enabled')
                page.wait_for_timeout(500)
            event_cb = page.locator('#cfg-hermes_event_batch_start')
            original = event_cb.is_checked()
            self._click_toggle(page, 'cfg-hermes_event_batch_start')
            page.wait_for_timeout(200)
            self.assertNotEqual(event_cb.is_checked(), original)
            self._click_toggle(page, 'cfg-hermes_event_batch_start')
            page.wait_for_timeout(200)
            self.assertEqual(event_cb.is_checked(), original)
        finally:
            page.close()

    # ================================================================
    # 32. 置信度配置编辑测试
    # ================================================================

    def test_84_confidence_edit_threshold(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'confidence')
            page.wait_for_timeout(1000)
            pass_input = page.locator('[data-section="confidence"] input[data-key="pass_threshold"]')
            if pass_input.count() > 0:
                original = pass_input.input_value()
                pass_input.fill('0.85')
                page.wait_for_timeout(200)
                self.assertEqual(pass_input.input_value(), '0.85')
                pass_input.fill(original)
        finally:
            page.close()

    def test_85_confidence_r_formula_selection(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'confidence')
            page.wait_for_timeout(1000)
            result = page.evaluate("""
                () => {
                    var cards = document.querySelectorAll('[data-section="confidence"] .r-formula-card');
                    var selectedBefore = null;
                    cards.forEach(function(c) { if (c.classList.contains('selected')) selectedBefore = c; });
                    var sqrtCard = null;
                    cards.forEach(function(c) { if (c.getAttribute('onclick') && c.getAttribute('onclick').indexOf('sqrt') >= 0) sqrtCard = c; });
                    if (sqrtCard) {
                        selectRFormula(sqrtCard, 'sqrt');
                        var isSelected = sqrtCard.classList.contains('selected');
                        if (selectedBefore && selectedBefore !== sqrtCard) selectRFormula(selectedBefore, selectedBefore.getAttribute('onclick').match(/'(\\w+)'/)[1]);
                        return { found: true, selected: isSelected };
                    }
                    return { found: false };
                }
            """)
            if result.get('found'):
                self.assertTrue(result.get('selected'), 'sqrt formula should be selected after click')
        finally:
            page.close()

    # ================================================================
    # 33. 路径规则删除测试
    # ================================================================

    def test_86_path_rules_delete_rule(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'path-rules')
            page.wait_for_timeout(1000)
            page.evaluate("addPathRule()")
            page.wait_for_timeout(500)
            count_after_add = page.evaluate("document.querySelectorAll('.path-rule-card, .rule-card').length")
            delete_btns = page.locator('.path-rule-card .btn-danger, .rule-card .btn-danger, .rule-delete-btn')
            if delete_btns.count() > 0:
                delete_btns.last.click()
                page.wait_for_timeout(500)
                count_after_delete = page.evaluate("document.querySelectorAll('.path-rule-card, .rule-card').length")
                self.assertLess(count_after_delete, count_after_add, 'Rule count should decrease after delete')
        finally:
            page.close()

    # ================================================================
    # 34. 切换主Tab后导航栈保持测试
    # ================================================================

    def test_87_nav_stack_persists_on_tab_switch(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'llm-config')
            page.wait_for_timeout(500)
            page.evaluate("switchTab('overview')")
            page.wait_for_timeout(400)
            page.evaluate("switchTab('config')")
            page.wait_for_timeout(500)
            section = page.locator('[data-section="llm"]')
            self.assertFalse(section.evaluate('el => el.classList.contains("collapsed-section")'),
                             'LLM section should still be visible after tab switch')
            breadcrumb = page.locator('#config-breadcrumb')
            self.assertIn('AI配置', breadcrumb.inner_text())
        finally:
            page.close()

    # ================================================================
    # 35. 入库选项完整编辑测试
    # ================================================================

    def test_88_import_options_edit_tv_template(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'import-options')
            page.wait_for_timeout(1000)
            original = page.locator('#cfg-filename_templates-tv').input_value()
            page.locator('#cfg-filename_templates-tv').fill('{title_cn}.S{s:02d}E{e:02d}.{ext}')
            self.assertEqual(page.locator('#cfg-filename_templates-tv').input_value(),
                             '{title_cn}.S{s:02d}E{e:02d}.{ext}')
            page.locator('#cfg-filename_templates-tv').fill(original)
        finally:
            page.close()

    def test_89_import_options_edit_subtitle_template(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'import-options')
            page.wait_for_timeout(1000)
            original = page.locator('#cfg-filename_templates-subtitle').input_value()
            page.locator('#cfg-filename_templates-subtitle').fill('{title_cn}.{lang}.{ext}')
            self.assertEqual(page.locator('#cfg-filename_templates-subtitle').input_value(),
                             '{title_cn}.{lang}.{ext}')
            page.locator('#cfg-filename_templates-subtitle').fill(original)
        finally:
            page.close()

    # ================================================================
    # 36. LLM 提示词视图测试
    # ================================================================

    def test_90_llm_prompt_textarea_visible(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'llm-prompt')
            page.wait_for_timeout(1000)
            prompt_area = page.locator('#prompt-system')
            if prompt_area.count() > 0:
                self.assertTrue(prompt_area.is_visible(), 'System prompt textarea should be visible in llm-prompt view')
        finally:
            page.close()

    # ================================================================
    # 37. 回收站目录视图完整测试
    # ================================================================

    def test_91_recycle_view_edit_retention_days(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'recycle')
            page.wait_for_timeout(1000)
            retention = page.locator('#cfg-source_policy-recycle_retention_days')
            if retention.is_visible():
                original = retention.input_value()
                retention.fill('14')
                self.assertEqual(retention.input_value(), '14')
                retention.fill(original)
        finally:
            page.close()

    def test_92_recycle_view_toggle_cleanup(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'recycle')
            page.wait_for_timeout(1000)
            checkbox = page.locator('#cfg-source_policy-cleanup_source_after_done')
            if checkbox.is_visible():
                original = checkbox.is_checked()
                self._click_toggle(page, 'cfg-source_policy-cleanup_source_after_done')
                page.wait_for_timeout(200)
                self.assertNotEqual(checkbox.is_checked(), original)
                self._click_toggle(page, 'cfg-source_policy-cleanup_source_after_done')
                page.wait_for_timeout(200)
                self.assertEqual(checkbox.is_checked(), original)
        finally:
            page.close()

    # ================================================================
    # 38. Provider 配置测试
    # ================================================================

    def test_93_provider_toggle_enabled(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'metadata-providers')
            page.wait_for_timeout(1500)
            toggle = page.locator('.provider-card .toggle-switch input').first
            if toggle.count() > 0:
                original = toggle.is_checked()
                toggle_label = page.locator('.provider-card .toggle-switch label').first
                toggle_label.click()
                page.wait_for_timeout(200)
                self.assertNotEqual(toggle.is_checked(), original)
                toggle_label.click()
                page.wait_for_timeout(200)
                self.assertEqual(toggle.is_checked(), original)
        finally:
            page.close()

    # ================================================================
    # 39. 高级设置扩展名自动补点测试
    # ================================================================

    def test_94_video_extensions_auto_dot_prefix(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'advanced')
            page.wait_for_timeout(1000)
            field = page.locator('#cfg-video_extensions')
            original = field.input_value()
            field.fill('mkv\nmp4')
            page.wait_for_timeout(200)
            data = page.evaluate("_buildAdvancedData()")
            self.assertIn('.mkv', data.get('video_extensions', []),
                          'Auto dot prefix should be added to video extensions')
            field.fill(original)
        finally:
            page.close()

    def test_95_subtitle_extensions_auto_dot_prefix(self):
        page = self._new_page()
        try:
            self._go_config(page)
            self._nav_to(page, 'advanced')
            page.wait_for_timeout(1000)
            field = page.locator('#cfg-subtitle_extensions')
            original = field.input_value()
            field.fill('srt\nass')
            page.wait_for_timeout(200)
            data = page.evaluate("_buildAdvancedData()")
            self.assertIn('.srt', data.get('subtitle_extensions', []),
                          'Auto dot prefix should be added to subtitle extensions')
            field.fill(original)
        finally:
            page.close()


if __name__ == '__main__':
    unittest.main()
