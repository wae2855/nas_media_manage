from playwright.sync_api import sync_playwright
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


def _navigate_to_confidence(page):
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    _dismiss_api_key_modal(page)
    page.locator("#tab-config").click()
    time.sleep(0.5)
    page.locator("#cfg-subtab-confidence").click()
    time.sleep(0.5)


def _expand_cfg_section(page, section_title_text):
    header = page.locator('.cfg-section-header:has-text("' + section_title_text + '")')
    if header.count() > 0:
        h = header.first
        cls = h.get_attribute("class") or ""
        if "open" not in cls:
            h.click()
            time.sleep(0.3)


def test_confidence_section_visible():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        _navigate_to_confidence(page)

        confidence_section = page.locator('[data-section="confidence"]')
        assert confidence_section.count() == 1, "Confidence section not found in DOM"
        assert confidence_section.is_visible(), "Confidence section not visible after switching to LLM sub-tab"

        browser.close()
        print("PASS: test_confidence_section_visible")


def test_decision_thresholds_visible():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        _navigate_to_confidence(page)

        section = page.locator('[data-section="confidence"]')

        pass_input = section.locator('input[data-key="pass_threshold"]')
        assert pass_input.count() == 1, "pass_threshold input not found"
        assert pass_input.is_visible(), "pass_threshold input not visible"
        assert pass_input.input_value() == "0.8", f"pass_threshold default should be 0.8, got {pass_input.input_value()}"

        confirm_input = section.locator('input[data-key="confirm_threshold"]')
        assert confirm_input.is_visible(), "confirm_threshold input not visible"
        assert confirm_input.input_value() == "0.5"

        review_input = section.locator('input[data-key="review_threshold"]')
        assert review_input.is_visible(), "review_threshold input not visible"
        assert review_input.input_value() == "0.3"

        browser.close()
        print("PASS: test_decision_thresholds_visible")


def test_r_formula_cards():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        _navigate_to_confidence(page)
        _expand_cfg_section(page, "搜索置信度")

        section = page.locator('[data-section="confidence"]')

        r_cards = section.locator(".r-formula-card")
        assert r_cards.count() == 4, f"Expected 4 R formula cards, got {r_cards.count()}"

        selected_r = section.locator(".r-formula-card.selected")
        assert selected_r.count() == 1, f"Expected 1 selected R formula card, got {selected_r.count()}"
        selected_text = selected_r.first.text_content()
        assert "log" in selected_text, f"Default R formula should be log, got: {selected_text}"

        inverse_card = section.locator(".r-formula-card:has-text('inverse')")
        assert inverse_card.count() == 1, "inverse R formula card not found"
        assert inverse_card.first.is_visible(), "inverse card should be visible after expanding section"
        inverse_card.first.click()
        time.sleep(0.3)

        new_selected = section.locator(".r-formula-card.selected")
        assert new_selected.count() == 1
        new_text = new_selected.first.text_content()
        assert "inverse" in new_text, f"After clicking inverse, selected should be inverse, got: {new_text}"

        log_card = section.locator(".r-formula-card:has-text('log')")
        log_card.first.click()
        time.sleep(0.3)

        browser.close()
        print("PASS: test_r_formula_cards")


def test_aggregation_cards():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        _navigate_to_confidence(page)
        _expand_cfg_section(page, "数据置信度")

        section = page.locator('[data-section="confidence"]')

        agg_cards = section.locator(".agg-card")
        assert agg_cards.count() == 3, f"Expected 3 aggregation cards, got {agg_cards.count()}"

        selected_agg = section.locator(".agg-card.selected")
        assert selected_agg.count() == 1, f"Expected 1 selected agg card, got {selected_agg.count()}"
        selected_text = selected_agg.first.text_content()
        assert "geometric_mean" in selected_text or "几何平均" in selected_text, f"Default agg should be geometric_mean, got: {selected_text}"

        min_card = section.locator(".agg-card:has-text('min')")
        assert min_card.count() == 1, "min agg card not found"
        assert min_card.first.is_visible(), "min card should be visible after expanding section"
        min_card.first.click()
        time.sleep(0.3)

        new_selected = section.locator(".agg-card.selected")
        assert new_selected.count() == 1
        new_text = new_selected.first.text_content()
        assert "min" in new_text, f"After clicking min, selected should be min, got: {new_text}"

        browser.close()
        print("PASS: test_aggregation_cards")


def test_ai_only_params_visible():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        _navigate_to_confidence(page)
        _expand_cfg_section(page, "纯AI")

        section = page.locator('[data-section="confidence"]')

        ai_cap_high = section.locator('input[data-key="ai_cap_high_similarity"]')
        assert ai_cap_high.count() == 1, "ai_cap_high_similarity input not found"
        assert ai_cap_high.is_visible(), "ai_cap_high_similarity should be visible after expanding"
        assert ai_cap_high.input_value() == "0.7"

        ai_cap_low = section.locator('input[data-key="ai_cap_low_similarity"]')
        assert ai_cap_low.count() == 1
        assert ai_cap_low.input_value() == "0.3"

        ai_cap_no_title = section.locator('input[data-key="ai_cap_no_title"]')
        assert ai_cap_no_title.count() == 1
        assert ai_cap_no_title.input_value() == "0.3"

        ai_cap_no_match = section.locator('input[data-key="ai_cap_no_match"]')
        assert ai_cap_no_match.count() == 1
        assert ai_cap_no_match.input_value() == "0.2"

        browser.close()
        print("PASS: test_ai_only_params_visible")


def test_source_confidence_defaults():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        _navigate_to_confidence(page)
        _expand_cfg_section(page, "数据置信度")

        section = page.locator('[data-section="confidence"]')

        tmdb_input = section.locator('input[data-key="tmdb_dim_confidence"]')
        assert tmdb_input.count() == 1, "tmdb_dim_confidence input not found"
        tmdb_val = tmdb_input.input_value()
        assert float(tmdb_val) == 1.0, f"tmdb_dim_confidence should be 1.0, got {tmdb_val}"

        file_input = section.locator('input[data-key="file_dim_confidence"]')
        assert file_input.count() == 1
        file_val = file_input.input_value()
        assert float(file_val) == 1.0, f"file_dim_confidence should be 1.0, got {file_val}"

        missing_input = section.locator('input[data-key="dim_missing_confidence"]')
        assert missing_input.count() == 1
        missing_val = missing_input.input_value()
        assert float(missing_val) == 0.5, f"dim_missing_confidence should be 0.5, got {missing_val}"

        browser.close()
        print("PASS: test_source_confidence_defaults")


def test_consult_prompt_generation():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        _navigate_to_confidence(page)

        section = page.locator('[data-section="confidence"]')

        consult_textarea = section.locator("#ai-consult-need")
        if consult_textarea.count() > 0:
            assert consult_textarea.is_visible(), "Consult textarea should be visible"
            consult_textarea.fill("我担心限制级电影被误判为家庭向")
            time.sleep(0.3)

            gen_btn = section.locator("button:has-text('生成咨询提示词')")
            assert gen_btn.count() >= 1, "Generate consult prompt button not found"
            gen_btn.first.click()
            time.sleep(1)

            prompt_output = section.locator("#ai-consult-prompt")
            if prompt_output.count() > 0:
                prompt_text = prompt_output.text_content() or ""
                assert len(prompt_text) > 200, f"Consult prompt too short ({len(prompt_text)} chars), expected > 200"
                print(f"Consult prompt length: {len(prompt_text)}")
            else:
                print("WARN: Consult prompt output element not found (may need section expansion)")
        else:
            print("WARN: Consult textarea not found")

        browser.close()
        print("PASS: test_consult_prompt_generation")


def test_threshold_bar_rendered():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        _navigate_to_confidence(page)

        section = page.locator('[data-section="confidence"]')

        threshold_bar = section.locator("#confidence-threshold-bar")
        assert threshold_bar.count() == 1, "Threshold bar not found"
        assert threshold_bar.is_visible(), "Threshold bar not visible"

        segments = threshold_bar.locator(".threshold-segment")
        assert segments.count() == 4, f"Expected 4 threshold segments, got {segments.count()}"

        seg_texts = [segments.nth(i).text_content() for i in range(segments.count())]
        assert "FAILED" in seg_texts[0], f"First segment should be FAILED, got: {seg_texts[0]}"
        assert "REVIEW" in seg_texts[1], f"Second segment should be REVIEW, got: {seg_texts[1]}"
        assert "CONFIRM" in seg_texts[2], f"Third segment should be CONFIRM, got: {seg_texts[2]}"
        assert "PASS" in seg_texts[3], f"Fourth segment should be PASS, got: {seg_texts[3]}"

        browser.close()
        print("PASS: test_threshold_bar_rendered")


def test_cfg_section_toggle():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        _navigate_to_confidence(page)

        section = page.locator('[data-section="confidence"]')

        search_header = section.locator('.cfg-section-header:has-text("搜索置信度")')
        assert search_header.count() >= 1, "Search confidence header not found"
        search_header = search_header.first

        header_classes = search_header.get_attribute("class") or ""
        was_open = "open" in header_classes

        search_header.click()
        time.sleep(0.3)

        new_classes = search_header.get_attribute("class") or ""
        if was_open:
            assert "open" not in new_classes, "Header should be closed after clicking open header"
        else:
            assert "open" in new_classes, "Header should be open after clicking closed header"

        search_header.click()
        time.sleep(0.3)

        restored_classes = search_header.get_attribute("class") or ""
        if was_open:
            assert "open" in restored_classes, "Header should be restored to open"
        else:
            assert "open" not in restored_classes, "Header should be restored to closed"

        browser.close()
        print("PASS: test_cfg_section_toggle")


def test_chinese_labels_in_formula():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        _navigate_to_confidence(page)

        section = page.locator('[data-section="confidence"]')

        formula = section.locator("#confidence-formula-preview")
        assert formula.count() == 1, "Formula preview not found"

        formula_text = formula.text_content() or ""
        assert "搜索准确度" in formula_text, f"Formula should contain '搜索准确度', got: {formula_text[:200]}"
        assert "数据置信度" in formula_text, f"Formula should contain '数据置信度', got: {formula_text[:200]}"
        assert "最终置信度" in formula_text, f"Formula should contain '最终置信度', got: {formula_text[:200]}"
        assert "自动通过" in formula_text, f"Formula should contain '自动通过', got: {formula_text[:200]}"
        assert "需确认" in formula_text, f"Formula should contain '需确认', got: {formula_text[:200]}"
        assert "需审核" in formula_text, f"Formula should contain '需审核', got: {formula_text[:200]}"

        badge_pass = section.locator(".badge-pass")
        assert badge_pass.count() >= 1, "PASS badge not found"
        assert "自动通过" in badge_pass.first.text_content(), f"PASS badge should say '自动通过', got: {badge_pass.first.text_content()}"

        badge_confirm = section.locator(".badge-confirm")
        assert badge_confirm.count() >= 1, "CONFIRM badge not found"
        assert "需确认" in badge_confirm.first.text_content(), f"CONFIRM badge should say '需确认', got: {badge_confirm.first.text_content()}"

        badge_review = section.locator(".badge-review")
        assert badge_review.count() >= 1, "REVIEW badge not found"
        assert "需审核" in badge_review.first.text_content(), f"REVIEW badge should say '需审核', got: {badge_review.first.text_content()}"

        browser.close()
        print("PASS: test_chinese_labels_in_formula")


def test_dimension_card_title_format():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        _navigate_to_confidence(page)
        _expand_cfg_section(page, "维度敏感度")

        section = page.locator('[data-section="confidence"]')

        dim_cards = section.locator(".dim-card")
        assert dim_cards.count() > 0, "No dimension cards found"

        first_name = dim_cards.first.locator(".dim-card-name")
        assert first_name.count() == 1, "dim-card-name not found"
        name_text = first_name.text_content() or ""

        has_parentheses = "(" in name_text and ")" in name_text
        assert has_parentheses, f"Dimension card name should have format '中文(english)', got: '{name_text}'"

        dim_key = dim_cards.first.locator(".dim-card-key")
        assert dim_key.count() == 1, "dim-card-key span not found"

        browser.close()
        print("PASS: test_dimension_card_title_format")


def test_dimension_card_collapsible():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        _navigate_to_confidence(page)
        _expand_cfg_section(page, "维度敏感度")

        section = page.locator('[data-section="confidence"]')

        dim_cards = section.locator(".dim-card")
        assert dim_cards.count() > 0, "No dimension cards found"

        first_header = dim_cards.first.locator(".dim-card-header")
        first_body = dim_cards.first.locator(".conf-dim-card-body")

        assert first_header.count() == 1, "dim-card-header not found"
        assert first_body.count() == 1, "conf-dim-card-body not found"

        assert not first_body.is_visible(), "conf-dim-card-body should be hidden initially"

        first_header.click()
        time.sleep(0.3)
        assert first_body.is_visible(), "conf-dim-card-body should be visible after clicking header"

        first_header.click()
        time.sleep(0.3)
        assert not first_body.is_visible(), "conf-dim-card-body should be hidden after clicking again"

        browser.close()
        print("PASS: test_dimension_card_collapsible")


def test_source_tag_readability():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        _navigate_to_confidence(page)
        _expand_cfg_section(page, "数据置信度")

        section = page.locator('[data-section="confidence"]')

        tmdb_tag = section.locator(".source-tag.tmdb").first
        if tmdb_tag.count() > 0:
            tmdb_color = tmdb_tag.evaluate("el => getComputedStyle(el).color")
            tmdb_bg = tmdb_tag.evaluate("el => getComputedStyle(el).backgroundColor")
            assert tmdb_color != "rgba(0, 0, 0, 0)", "TMDB tag text should have visible color"
            assert tmdb_bg != "rgba(0, 0, 0, 0)", "TMDB tag should have solid background"
            assert tmdb_bg != tmdb_color, "TMDB tag background and text should differ for contrast"

        ai_tag = section.locator(".source-tag.ai").first
        if ai_tag.count() > 0:
            ai_color = ai_tag.evaluate("el => getComputedStyle(el).color")
            ai_bg = ai_tag.evaluate("el => getComputedStyle(el).backgroundColor")
            assert ai_color != "rgba(0, 0, 0, 0)", "AI tag text should have visible color"
            assert ai_bg != "rgba(0, 0, 0, 0)", "AI tag should have solid background"
            assert ai_bg != ai_color, "AI tag background and text should differ for contrast"

        missing_tag = section.locator(".source-tag.missing").first
        if missing_tag.count() > 0:
            missing_color = missing_tag.evaluate("el => getComputedStyle(el).color")
            missing_bg = missing_tag.evaluate("el => getComputedStyle(el).backgroundColor")
            assert missing_color != "rgba(0, 0, 0, 0)", "Missing tag text should have visible color"
            assert missing_bg != "rgba(0, 0, 0, 0)", "Missing tag should have solid background"
            assert missing_bg != missing_color, "Missing tag background and text should differ for contrast"

        browser.close()
        print("PASS: test_source_tag_readability")


if __name__ == "__main__":
    test_confidence_section_visible()
    test_decision_thresholds_visible()
    test_r_formula_cards()
    test_aggregation_cards()
    test_ai_only_params_visible()
    test_source_confidence_defaults()
    test_consult_prompt_generation()
    test_threshold_bar_rendered()
    test_cfg_section_toggle()
    test_chinese_labels_in_formula()
    test_dimension_card_title_format()
    test_dimension_card_collapsible()
    test_source_tag_readability()
    print("\nAll confidence UI tests completed!")
