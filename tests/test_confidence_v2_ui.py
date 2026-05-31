#!/usr/bin/env python3
import unittest
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:9855"
API_KEY = "oppenssl-11"


class TestConfidenceV2UI(unittest.TestCase):
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
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        modal = page.locator("#api-key-modal")
        if modal.count() > 0 and modal.is_visible():
            page.evaluate("document.getElementById('api-key-modal').style.display='none'")
        page.evaluate("switchTab('config')")
        page.wait_for_timeout(400)
        page.evaluate("switchConfigSubTab('confidence')")
        page.wait_for_timeout(1500)
        return page

    def test_tmdb_match_threshold_default_085(self):
        page = self._open_confidence_tab()
        try:
            inp = page.locator('input[data-key="tmdb_match_threshold"]')
            self.assertTrue(inp.count() > 0, "tmdb_match_threshold input not found")
            default_td = page.locator('tr:has(input[data-key="tmdb_match_threshold"]) .param-default')
            self.assertTrue(default_td.count() > 0, "Default value cell not found")
            default_text = default_td.inner_text()
            self.assertEqual(default_text, "0.85", f"Default value expected 0.85, got {default_text}")
        finally:
            page.close()

    def test_l2_title_exact_with_season_exists(self):
        page = self._open_confidence_tab()
        try:
            inp = page.locator('input[data-key="title_exact_with_season"]')
            self.assertTrue(inp.count() > 0, "title_exact_with_season input not found")
            value = inp.input_value()
            self.assertEqual(value, "0.9", f"Expected 0.9, got {value}")
        finally:
            page.close()

    def test_l2_label_visible(self):
        page = self._open_confidence_tab()
        try:
            label = page.locator('td.param-name:has-text("L2 精确+有季号")')
            self.assertTrue(label.count() > 0, "L2 label not found in UI")
        finally:
            page.close()

    def test_l1_label_still_exists(self):
        page = self._open_confidence_tab()
        try:
            label = page.locator('td.param-name:has-text("L1 精确+年份精确")')
            self.assertTrue(label.count() > 0, "L1 label not found in UI")
        finally:
            page.close()

    def test_l3_label_still_exists(self):
        page = self._open_confidence_tab()
        try:
            label = page.locator('td.param-name:has-text("L3 精确无年份")')
            self.assertTrue(label.count() > 0, "L3 label not found in UI")
        finally:
            page.close()

    def test_r_t_floor_and_curve_params(self):
        page = self._open_confidence_tab()
        try:
            floor_inp = page.locator('input[data-key="R_T_floor"]')
            curve_inp = page.locator('input[data-key="R_T_curve"]')
            self.assertTrue(floor_inp.count() > 0, "R_T_floor input not found")
            self.assertTrue(curve_inp.count() > 0, "R_T_curve input not found")
            floor_val = floor_inp.input_value()
            curve_val = curve_inp.input_value()
            self.assertEqual(floor_val, "0.5", f"R_T_floor expected 0.5, got {floor_val}")
            self.assertEqual(curve_val, "1.5", f"R_T_curve expected 1.5, got {curve_val}")
        finally:
            page.close()

    def test_threshold_bar_renders(self):
        page = self._open_confidence_tab()
        try:
            bar = page.locator("#confidence-threshold-bar")
            self.assertTrue(bar.count() > 0, "Threshold bar not found")
            inner = bar.inner_html()
            self.assertIn("PASS", inner)
            self.assertIn("FAILED", inner)
        finally:
            page.close()

    def test_formula_preview_shows(self):
        page = self._open_confidence_tab()
        try:
            formula = page.locator("#confidence-formula-preview")
            self.assertTrue(formula.count() > 0, "Formula preview not found")
            text = formula.inner_text()
            self.assertIn("search_conf", text)
            self.assertIn("data_conf", text)
        finally:
            page.close()

    def test_dimension_sensitivity_cards_load(self):
        page = self._open_confidence_tab()
        try:
            container = page.locator("#dim-sensitivity-cards")
            self.assertTrue(container.count() > 0, "Dimension sensitivity container not found")
            page.wait_for_timeout(2000)
            cards = container.locator(".dim-card")
            self.assertTrue(cards.count() > 0, "No dimension cards rendered")
        finally:
            page.close()

    def test_confidence_config_saveable(self):
        page = self._open_confidence_tab()
        try:
            save_btns = page.locator('[data-section="confidence"] .cfg-section-save')
            self.assertTrue(save_btns.count() > 0, "No save buttons found in confidence section")
        finally:
            page.close()


if __name__ == "__main__":
    unittest.main()
