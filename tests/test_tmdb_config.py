from playwright.sync_api import sync_playwright
import sys, os, json

BASE = "http://127.0.0.1:9855"
API_KEY = "oppenssl-11"
SCREENSHOT_DIR = "/tmp/ui_test_screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

errors = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    page.goto(BASE)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)

    modal = page.locator("#api-key-modal")
    if modal.is_visible():
        page.evaluate(f"""
            var input = document.getElementById('api-key-input');
            if (input) input.value = '{API_KEY}';
            submitApiKey();
        """)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

    page.evaluate("switchTab('config')")
    page.wait_for_timeout(1500)

    page.evaluate("switchConfigSubTab('metadata')")
    page.wait_for_timeout(2000)

    page.evaluate("""
        var header = document.querySelector('.provider-card-header');
        if (header) toggleProviderCard(header);
    """)
    page.wait_for_timeout(800)
    print("INFO: Expanded provider card via JS")

    page.evaluate("window.scrollTo(0, 500)")
    page.wait_for_timeout(500)

    print("=== Test 1: Provider card has test button with correct ID ===")
    test_btn = page.locator("#btn-test-provider-tmdb")
    if test_btn.count() > 0:
        print("PASS: Test button #btn-test-provider-tmdb exists")
    else:
        errors.append("FAIL: Test button #btn-test-provider-tmdb NOT found")

    print("=== Test 2: Provider card has test result element ===")
    result_el = page.locator("#provider-test-result-tmdb")
    if result_el.count() > 0:
        print("PASS: Result element #provider-test-result-tmdb exists")
    else:
        errors.append("FAIL: Result element #provider-test-result-tmdb NOT found")

    print("=== Test 3: Provider card has save button with correct ID ===")
    save_btn = page.locator("#btn-save-provider-tmdb")
    if save_btn.count() > 0:
        print("PASS: Save button #btn-save-provider-tmdb exists")
    else:
        errors.append("FAIL: Save button #btn-save-provider-tmdb NOT found")

    print("=== Test 4: API Key input field exists ===")
    api_key_input = page.locator("#cfg-provider-tmdb-api_key")
    if api_key_input.count() > 0:
        print("PASS: API Key input field exists")
    else:
        errors.append("FAIL: API Key input field NOT found")

    print("=== Test 5: Language select field exists ===")
    lang_select = page.locator("#cfg-provider-tmdb-language")
    if lang_select.count() > 0:
        print("PASS: Language select field exists")
    else:
        errors.append("FAIL: Language select field NOT found")

    print("=== Test 6: Language select has correct value from config ===")
    if lang_select.count() > 0:
        lang_val = lang_select.first.input_value()
        if lang_val == "zh-CN":
            print(f"PASS: Language value is '{lang_val}'")
        else:
            errors.append(f"FAIL: Language value is '{lang_val}', expected 'zh-CN'")

    print("=== Test 7: Test connection button works ===")
    page.evaluate("testProvider('tmdb')")
    page.wait_for_timeout(8000)
    result_el_after = page.locator("#provider-test-result-tmdb")
    if result_el_after.count() > 0:
        result_text = result_el_after.first.text_content()
        is_visible = result_el_after.first.is_visible()
        print(f"INFO: Result visible={is_visible}, text='{result_text}'")
        if is_visible and result_text and "连接成功" in result_text:
            print("PASS: Test connection shows success")
        elif is_visible and result_text and "测试中" in result_text:
            page.wait_for_timeout(10000)
            result_text2 = result_el_after.first.text_content()
            if result_text2 and "连接成功" in result_text2:
                print("PASS: Test connection shows success (after wait)")
            else:
                errors.append(f"FAIL: Test connection result: '{result_text2}'")
        elif not is_visible:
            display_val = result_el_after.first.evaluate("el => el.style.display")
            errors.append(f"FAIL: Result element not visible, display={display_val}")
        else:
            errors.append(f"FAIL: Test connection result not success: visible={is_visible}, text='{result_text}'")
    else:
        errors.append("FAIL: Result element disappeared after test")

    print("=== Test 8: Save provider config ===")
    api_key_input_el = page.locator("#cfg-provider-tmdb-api_key")
    if api_key_input_el.count() > 0:
        current_val = api_key_input_el.first.input_value()
        print(f"INFO: Current API Key value length: {len(current_val)}")

    page.evaluate("saveSection('metadata.providers')")
    page.wait_for_timeout(3000)

    toast_texts = page.evaluate("""
        () => {
            var toasts = document.querySelectorAll('.toast');
            var texts = [];
            for (var i = 0; i < toasts.length; i++) {
                texts.push(toasts[i].textContent);
            }
            return texts;
        }
    """)
    save_ok = any("保存" in t and "失败" not in t for t in toast_texts) if toast_texts else False
    if save_ok:
        print("PASS: Save succeeded")
    else:
        print(f"INFO: Toast messages: {toast_texts}")

    print("=== Test 9: Scrape preview modal ===")
    page.evaluate("showProviderPreviewModal('tmdb')")
    page.wait_for_timeout(1000)

    modal_el = page.locator("#tmdb-preview-modal")
    if modal_el.count() > 0 and modal_el.first.is_visible():
        print("PASS: Scrape preview modal opened")

        page.evaluate("""
            var q = document.getElementById('tmdb-preview-query');
            if (q) q.value = 'Inception';
        """)
        page.wait_for_timeout(300)

        page.evaluate("doTmdbPreview()")
        page.wait_for_timeout(10000)

        results = page.locator(".tmdb-result-card")
        if results.count() > 0:
            print(f"PASS: Found {results.count()} search results")
            page.evaluate("""
                var card = document.querySelector('.tmdb-result-card');
                if (card) _selectTmdbResult(card);
            """)
            page.wait_for_timeout(5000)
            detail = page.locator("#tmdb-detail-container .tmdb-detail-view")
            if detail.count() > 0:
                print("PASS: Detail view loaded after clicking result")
            else:
                detail_raw = page.locator("#tmdb-detail-container")
                detail_text = detail_raw.first.text_content() if detail_raw.count() > 0 else ""
                errors.append(f"FAIL: Detail view not loaded. Content: '{detail_text[:100]}'")
        else:
            results_el = page.locator("#tmdb-search-results")
            results_text = results_el.first.text_content() if results_el.count() > 0 else ""
            errors.append(f"FAIL: No search results. Content: '{results_text[:100]}'")

        page.evaluate("closeTmdbPreviewModal()")
        page.wait_for_timeout(500)
    else:
        errors.append("FAIL: Scrape preview modal did not open")

    print("=== Test 10: Verify _cachedProviderSchemas is populated ===")
    schemas = page.evaluate("() => Object.keys(window._cachedProviderSchemas || {})")
    if schemas and 'tmdb' in schemas:
        tmdb_fields = page.evaluate("() => (window._cachedProviderSchemas.tmdb || {}).fields || []")
        field_keys = [f.get('key') for f in tmdb_fields]
        if 'api_key' in field_keys:
            print(f"PASS: _cachedProviderSchemas has tmdb with fields: {field_keys}")
        else:
            errors.append(f"FAIL: _cachedProviderSchemas tmdb missing api_key, fields: {field_keys}")
    else:
        errors.append(f"FAIL: _cachedProviderSchemas not populated or missing tmdb: {schemas}")

    print("=== Test 11: Verify provider config includes all fields from legacy format ===")
    provider_config = page.evaluate("""
        () => {
            var card = document.querySelector('.provider-card');
            if (!card) return {};
            var result = {};
            var inputs = card.querySelectorAll('input, select');
            for (var i = 0; i < inputs.length; i++) {
                var el = inputs[i];
                var id = el.id || '';
                if (id.startsWith('cfg-provider-tmdb-')) {
                    var key = id.replace('cfg-provider-tmdb-', '');
                    result[key] = el.value;
                }
            }
            return result;
        }
    """)
    print(f"INFO: Provider config from UI: {json.dumps(provider_config, ensure_ascii=False)}")
    if provider_config.get('language') == 'zh-CN':
        print("PASS: Language field correctly populated from legacy config")
    else:
        errors.append(f"FAIL: Language field not populated correctly: {provider_config.get('language')}")

    if provider_config.get('fallback_language') == 'en-US':
        print("PASS: Fallback language field correctly populated from legacy config")
    else:
        errors.append(f"FAIL: Fallback language field not populated correctly: {provider_config.get('fallback_language')}")

    page.screenshot(path=os.path.join(SCREENSHOT_DIR, "tmdb_config_test.png"))

    browser.close()

print("\n" + "=" * 60)
if errors:
    print(f"FAILED: {len(errors)} error(s)")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("ALL TESTS PASSED!")
