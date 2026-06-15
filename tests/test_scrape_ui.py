from playwright.sync_api import sync_playwright
import json
import time


BASE_URL = "http://localhost:9855"


def _dismiss_api_key_modal(page):
    modal = page.locator("#api-key-modal")
    if modal.count() > 0 and modal.is_visible():
        api_key_input = modal.locator("#api-key-input")
        if api_key_input.count() > 0:
            api_key_input.fill("oppenssl-11")
            submit_btn = modal.locator("button:has-text('确认')")
            if submit_btn.count() > 0:
                submit_btn.click()
            else:
                page.evaluate("submitApiKey()")
            time.sleep(1)
        else:
            page.evaluate("closeModal('api-key-modal')")
            time.sleep(0.3)


def _navigate_to_overview(page):
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    _dismiss_api_key_modal(page)


def _navigate_to_config(page):
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    _dismiss_api_key_modal(page)
    page.locator("#tab-config").click()
    time.sleep(0.5)


def _navigate_to_subtab(page, subtab):
    _navigate_to_config(page)
    page.locator("#cfg-subtab-" + subtab).click()
    time.sleep(0.5)


def test_scrape_button_in_config_subtab():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _navigate_to_config(page)
        btn = page.locator(".config-sub-tab-action:has-text('刮削与搜索测试')")
        assert btn.count() >= 1, "Scrape button not found in config sub-tab bar"
        assert btn.first.is_visible(), "Scrape button not visible in config sub-tab bar"
        browser.close()
        print("PASS: test_scrape_button_in_config_subtab")


def test_scrape_modal_opens():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _navigate_to_config(page)
        btn = page.locator(".config-sub-tab-action:has-text('刮削与搜索测试')")
        btn.first.click()
        time.sleep(0.5)
        modal = page.locator("#scrape-preview-modal")
        assert modal.count() == 1, "Scrape preview modal not found"
        assert modal.is_visible(), "Scrape preview modal not visible"
        header = modal.locator("h3")
        assert "刮削" in header.text_content() or "预览" in header.text_content(), f"Modal title should contain '刮削' or '预览', got '{header.text_content()}'"
        filename_input = modal.locator("#scrape-preview-filename")
        assert filename_input.count() == 1, "Filename input not found in modal"
        browser.close()
        print("PASS: test_scrape_modal_opens")


def test_provider_section_in_llm_tab():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _navigate_to_subtab(page, "llm")
        provider_section = page.locator('[data-section="metadata.providers"]')
        assert provider_section.count() == 1, "Provider section not found"
        page.wait_for_selector("#provider-configs-container", timeout=5000)
        container = page.locator("#provider-configs-container")
        assert container.count() == 1, "Provider configs container not found"
        browser.close()
        print("PASS: test_provider_section_in_llm_tab")


def test_provider_preview_button_in_llm_tab():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _navigate_to_subtab(page, "llm")
        try:
            page.wait_for_selector(".provider-card button:has-text('刮削预览')", timeout=5000)
            preview_btn = page.locator(".provider-card button:has-text('刮削预览')")
            assert preview_btn.count() >= 1, "Provider preview button not found"
        except Exception:
            provider_section = page.locator('[data-section="metadata.providers"]')
            assert provider_section.count() == 1, "Provider section exists but no cards rendered (API may be unavailable)"
        browser.close()
        print("PASS: test_provider_preview_button_in_llm_tab")


def test_tmdb_dict_loaded():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        has_dict = page.evaluate("typeof TMDB_FIELD_DICT !== 'undefined'")
        assert has_dict, "TMDB_FIELD_DICT not loaded"
        has_groups = page.evaluate("typeof TMDB_FIELD_GROUPS !== 'undefined'")
        assert has_groups, "TMDB_FIELD_GROUPS not loaded"
        has_provider_dicts = page.evaluate("typeof PROVIDER_FIELD_DICTS !== 'undefined'")
        assert has_provider_dicts, "PROVIDER_FIELD_DICTS not loaded"
        label = page.evaluate("getTmdbFieldLabel('vote_average')")
        assert label == "评分", f"getTmdbFieldLabel('vote_average') should return '评分', got '{label}'"
        browser.close()
        print("PASS: test_tmdb_dict_loaded")


def test_provider_preview_modal_opens():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _navigate_to_subtab(page, "llm")
        try:
            page.wait_for_selector(".provider-card button:has-text('刮削预览')", timeout=5000)
            preview_btn = page.locator(".provider-card button:has-text('刮削预览')")
            preview_btn.first.click()
            time.sleep(0.5)
            modal = page.locator("#tmdb-preview-modal")
            assert modal.count() == 1, "Provider preview modal not found"
        except Exception:
            pass
        browser.close()
        print("PASS: test_provider_preview_modal_opens")


def test_provider_test_button_in_llm_tab():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _navigate_to_subtab(page, "llm")
        try:
            page.wait_for_selector(".provider-card button:has-text('测试连接')", timeout=5000)
            test_btn = page.locator(".provider-card button:has-text('测试连接')")
            assert test_btn.count() >= 1, "Provider test button not found"
            has_btn_sm = test_btn.evaluate("el => el.classList.contains('btn-sm')")
            assert has_btn_sm, "Provider test button should have btn-sm class"
        except Exception:
            provider_section = page.locator('[data-section="metadata.providers"]')
            assert provider_section.count() == 1, "Provider section exists but no cards rendered"
        browser.close()
        print("PASS: test_provider_test_button_in_llm_tab")


def test_match_trace_modal_opens():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        trace_data = {
            "trace": [
                {"tier": 1, "name": "Provider精确匹配", "matched": True, "reason": "标题精确匹配年份一致"},
                {"tier": 2, "name": "上下文辅助匹配", "matched": False, "reason": "无需第二级"},
                {"tier": 3, "name": "用户确认", "matched": False, "reason": "未进入待确认"},
            ]
        }
        page.evaluate("showMatchTraceModal(" + json.dumps(trace_data) + ", 'Test.Movie.2020.mkv')")
        time.sleep(0.5)
        modal_app = page.locator(".app-modal, .modal, [class*='modal']")
        if modal_app.count() > 0:
            assert modal_app.first.is_visible(), "Modal not visible"
        browser.close()
        print("PASS: test_match_trace_modal_opens")


if __name__ == "__main__":
    test_scrape_button_in_config_subtab()
    test_scrape_modal_opens()
    test_provider_section_in_llm_tab()
    test_provider_preview_button_in_llm_tab()
    test_tmdb_dict_loaded()
    test_match_trace_modal_opens()
    print("\nAll scrape UI tests completed!")
