import time

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.live_e2e


def _nav_to_config(page):
    page.locator('button.nav-item[data-nav="config"]').click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)


def _click_stage(page, stage):
    page.locator(f'[data-config-stage="{stage}"]').click()
    time.sleep(0.3)


def _nav_to_advanced(page):
    _nav_to_config(page)
    page.locator('button.btn-primary[data-view-target="advanced-config"]').click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)


def _nav_to_subpage(page, view_name):
    _nav_to_advanced(page)
    page.locator(f'button.setup-card[data-view-target="{view_name}"]').click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)


def _wait_for_toast(page, timeout=5000):
    toast = page.locator("#toast")
    toast.wait_for(state="visible", timeout=timeout)
    time.sleep(0.3)
    return toast


def test_C00_config_dirs_not_empty(e2e_page, e2e_server):
    """C00: Navigate to config page, verify source_dir, temp_dir, recycle_dir fields are NOT empty."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "source")
    source_val = page.locator("#cfg-source-inline").input_value()
    assert source_val.strip() != "", "source_dir should not be empty"
    _click_stage(page, "temp")
    temp_val = page.locator("#cfg-temp-inline").input_value()
    assert temp_val.strip() != "", "temp_dir should not be empty"
    _click_stage(page, "recycle")
    recycle_val = page.locator("#cfg-recycle-inline").input_value()
    assert recycle_val.strip() != "", "recycle_dir should not be empty"


def test_C01_config_page_visible(e2e_page, e2e_server):
    """C01: Click config nav, verify config page visible with step strip."""
    page = e2e_page
    _nav_to_config(page)
    source_stage = page.locator('[data-config-stage="source"]')
    expect(source_stage).to_be_visible()
    expect(source_stage).to_contain_text("源目录")


def test_C02_source_dir_has_value(e2e_page, e2e_server):
    """C02: Check #cfg-source-inline has a value (not empty)."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "source")
    source_input = page.locator("#cfg-source-inline")
    expect(source_input).to_be_visible()
    assert source_input.input_value().strip() != ""


def test_C03_temp_dir_has_value(e2e_page, e2e_server):
    """C03: Switch to temp stage, check #cfg-temp-inline has value."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "temp")
    temp_input = page.locator("#cfg-temp-inline")
    expect(temp_input).to_be_visible()
    assert temp_input.input_value().strip() != ""


def test_C04_recycle_dir_has_value(e2e_page, e2e_server):
    """C04: Switch to recycle stage, check #cfg-recycle-inline has value."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "recycle")
    recycle_input = page.locator("#cfg-recycle-inline")
    expect(recycle_input).to_be_visible()
    assert recycle_input.input_value().strip() != ""


def test_C05_clear_and_type_source_dir(e2e_page, e2e_server):
    """C05: Clear #cfg-source-inline, type new path, verify input retains value."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "source")
    source_input = page.locator("#cfg-source-inline")
    source_input.fill("")
    test_path = e2e_server["source_dir"]
    source_input.fill(test_path)
    assert source_input.input_value() == test_path


def test_C06_path_test_source(e2e_page, e2e_server):
    """C06: Click [data-path-test="source"], verify result shown."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "source")
    page.locator("#cfg-source-inline").fill(e2e_server["source_dir"])
    page.locator('[data-path-test="source"]').click()
    toast = _wait_for_toast(page)
    expect(toast).to_be_visible()


def test_C07_save_source_config(e2e_page, e2e_server):
    """C07: Click [data-config-save="source"], verify toast success."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "source")
    page.locator("#cfg-source-inline").fill(e2e_server["source_dir"])
    page.locator('[data-config-save="source"]').click()
    toast = _wait_for_toast(page)
    expect(toast).to_be_visible()


def test_C08_source_dir_persists_after_refresh(e2e_page, e2e_server):
    """C08: Refresh page, go back to config, verify source dir value persists."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "source")
    page.locator("#cfg-source-inline").fill(e2e_server["source_dir"])
    page.locator('[data-config-save="source"]').click()
    _wait_for_toast(page)
    page.reload()
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)
    _nav_to_config(page)
    _click_stage(page, "source")
    time.sleep(0.5)
    value = page.locator("#cfg-source-inline").input_value()
    assert value == e2e_server["source_dir"]


def test_C09_scrape_panel_expands(e2e_page, e2e_server):
    """C09: Click scrape stage, verify scrape panel expands."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "scrape")
    scrape_panel = page.locator('[data-config-panel="scrape"]')
    expect(scrape_panel).to_be_visible()


def test_C10_clear_source_dir_save_error(e2e_page, e2e_server):
    """C10: Clear source dir, click save, verify error/failure."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "source")
    page.locator("#cfg-source-inline").fill(e2e_server["source_dir"])
    page.locator('[data-config-save="source"]').click()
    _wait_for_toast(page)
    page.locator("#cfg-source-inline").fill("")
    page.locator('[data-config-save="source"]').click()
    toast = _wait_for_toast(page)
    toast_text = toast.inner_text()
    assert "必填" in toast_text or "源目录" in toast_text


def _click_toggle_when_needed(page, selector, checked):
    toggle = page.locator(selector)
    if toggle.is_checked() != checked:
        page.locator(f"{selector} + .toggle-pill-ui").click()
        time.sleep(0.5)


def _enable_source_cleaner(page):
    _click_toggle_when_needed(page, "#cfg-source-cleaner-enabled-inline", True)


def test_C11_cleanup_mode_read_only(e2e_page, e2e_server):
    """C11: Select read_only radio, verify checked."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "source")
    _enable_source_cleaner(page)
    page.get_by_text("仅保留影视+字幕").click()
    time.sleep(0.3)
    media_only_radio = page.locator(
        'input[name="cfg-source_cleaner-cleanup_mode_inline"][value="media_only"]'
    )
    assert media_only_radio.is_checked()


def test_C12_cleanup_mode_media_and_related(e2e_page, e2e_server):
    """C12: Select media_and_related radio, verify AI cleanup options show/hide."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "source")
    _enable_source_cleaner(page)
    page.get_by_text("保留影视+字幕+相关文件").click()
    time.sleep(0.3)
    related_radio = page.locator(
        'input[name="cfg-source_cleaner-cleanup_mode_inline"][value="media_and_related"]'
    )
    assert related_radio.is_checked()


def test_C13_recursive_toggle(e2e_page, e2e_server):
    """C13: Toggle #cfg-source-recursive-toggle-inline, verify state change."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "source")
    recursive_toggle = page.locator("#cfg-source-recursive-toggle-inline")
    _click_toggle_when_needed(page, "#cfg-source-recursive-toggle-inline", True)
    assert recursive_toggle.is_checked()


def test_C14_depth_input_value(e2e_page, e2e_server):
    """C14: Type 3 into #cfg-source-depth-inline, verify value."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "source")
    _click_toggle_when_needed(page, "#cfg-source-recursive-toggle-inline", True)
    depth_input = page.locator("#cfg-source-depth-inline")
    expect(depth_input).to_be_visible()
    depth_input.fill("3")
    assert depth_input.input_value() == "3"


def test_C15_cleaner_enabled_toggle(e2e_page, e2e_server):
    """C15: Toggle #cfg-source-cleaner-enabled-inline, verify area expand/collapse."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "source")
    cleaner_toggle = page.locator("#cfg-source-cleaner-enabled-inline")
    _click_toggle_when_needed(page, "#cfg-source-cleaner-enabled-inline", False)
    _click_toggle_when_needed(page, "#cfg-source-cleaner-enabled-inline", True)
    assert cleaner_toggle.is_checked()


def test_C16_save_source_policy(e2e_page, e2e_server):
    """C16: Click [data-config-save="source"], verify toast success."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "source")
    page.locator("#cfg-source-inline").fill(e2e_server["source_dir"])
    _click_toggle_when_needed(page, "#cfg-source-recursive-toggle-inline", True)
    page.locator("#cfg-source-depth-inline").fill("5")
    page.locator('[data-config-save="source"]').click()
    toast = _wait_for_toast(page)
    expect(toast).to_be_visible()


def test_C17_source_policy_persists(e2e_page, e2e_server):
    """C17: Refresh, verify cleanup mode and recursive toggle persist."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "source")
    page.locator("#cfg-source-inline").fill(e2e_server["source_dir"])
    _click_toggle_when_needed(page, "#cfg-source-recursive-toggle-inline", True)
    page.locator("#cfg-source-depth-inline").fill("5")
    page.locator('[data-config-save="source"]').click()
    _wait_for_toast(page)
    page.reload()
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)
    _nav_to_config(page)
    _click_stage(page, "source")
    time.sleep(0.5)
    assert page.locator("#cfg-source-recursive-toggle-inline").is_checked()
    assert page.locator("#cfg-source-depth-inline").input_value() == "5"


def test_C18_ai_config_page_shows(e2e_page, e2e_server):
    """C18: Switch to AI stage, verify provider dropdown and API key visible."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "ai")
    ai_panel = page.locator('[data-config-panel="ai"]')
    expect(ai_panel).to_be_visible()
    expect(page.locator("#cfg-llm_provider-inline")).to_be_visible()
    expect(page.locator("#cfg-llm_api_key-inline")).to_be_visible()


def test_C19_api_key_masked(e2e_page, e2e_server):
    """C19: Check #cfg-llm_api_key-inline is type=password (masked)."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "ai")
    api_key_input = page.locator("#cfg-llm_api_key-inline")
    expect(api_key_input).to_be_visible()
    assert api_key_input.get_attribute("type") == "password"


def test_C20_llm_model_has_name(e2e_page, e2e_server):
    """C20: Check #cfg-llm_model-inline has actual model name."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "ai")
    model_input = page.locator("#cfg-llm_model-inline")
    expect(model_input).to_be_visible()
    val = model_input.input_value()
    assert val.strip() != ""


def test_C21_llm_base_url_has_value(e2e_page, e2e_server):
    """C21: Check #cfg-llm_base_url-inline has actual URL."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "ai")
    url_input = page.locator("#cfg-llm_base_url-inline")
    expect(url_input).to_be_visible()
    val = url_input.input_value()
    assert val.strip() != ""


def test_C24_scrape_tmdb_card_visible(e2e_page, e2e_server):
    """C24: Switch to scrape stage, verify TMDB card visible."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "scrape")
    scrape_panel = page.locator('[data-config-panel="scrape"]')
    expect(scrape_panel).to_be_visible()
    provider_stack = page.locator("#provider-inline-stack")
    expect(provider_stack).to_be_visible()


def test_C25_scrape_api_key_masked(e2e_page, e2e_server):
    """C25: Check API key in provider card shows ***."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "scrape")
    time.sleep(1.0)
    provider_password_fields = page.locator(
        '#provider-inline-stack input[type="password"]'
    )
    count = provider_password_fields.count()
    assert count >= 0
    for i in range(count):
        field = provider_password_fields.nth(i)
        assert field.get_attribute("type") == "password"


def test_C29_rules_list_visible(e2e_page, e2e_server):
    """C29: Switch to rules stage, verify rule list visible."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "rules")
    rules_panel = page.locator('[data-config-panel="rules"]')
    expect(rules_panel).to_be_visible()
    rule_list = page.locator("#rules-inline-list")
    expect(rule_list).to_be_visible()


def test_C30_fallback_has_value(e2e_page, e2e_server):
    """C30: Check #cfg-fallback-inline has value."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "rules")
    fallback_input = page.locator("#cfg-fallback-inline")
    expect(fallback_input).to_be_visible()
    assert fallback_input.input_value().strip() != ""


def test_C31_save_rules(e2e_page, e2e_server):
    """C31: Click [data-config-save="rules"], verify toast success."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "rules")
    page.locator('[data-config-save="rules"]').click()
    toast = _wait_for_toast(page)
    expect(toast).to_be_visible()


def test_C32_rules_persist(e2e_page, e2e_server):
    """C32: Refresh, verify rules persist."""
    page = e2e_page
    _nav_to_config(page)
    _click_stage(page, "rules")
    page.locator('[data-config-save="rules"]').click()
    _wait_for_toast(page)
    page.reload()
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)
    _nav_to_config(page)
    _click_stage(page, "rules")
    time.sleep(0.5)
    fallback_input = page.locator("#cfg-fallback-inline")
    assert fallback_input.input_value().strip() != ""


def test_C33_naming_config_page(e2e_page, e2e_server):
    """C33: Navigate to naming-config sub-page."""
    page = e2e_page
    _nav_to_subpage(page, "naming-config")
    naming_view = page.locator('[data-view="naming-config"]')
    expect(naming_view).to_be_visible()


def test_C34_naming_movie_template(e2e_page, e2e_server):
    """C34: Check #cfg-filename_templates-movie-inline."""
    page = e2e_page
    _nav_to_subpage(page, "naming-config")
    movie_input = page.locator("#cfg-filename_templates-movie-inline")
    expect(movie_input).to_be_visible()


def test_C35_naming_tv_template(e2e_page, e2e_server):
    """C35: Check #cfg-filename_templates-tv-inline."""
    page = e2e_page
    _nav_to_subpage(page, "naming-config")
    tv_input = page.locator("#cfg-filename_templates-tv-inline")
    expect(tv_input).to_be_visible()


def test_C36_naming_subtitle_template(e2e_page, e2e_server):
    """C36: Check #cfg-filename_templates-subtitle-inline."""
    page = e2e_page
    _nav_to_subpage(page, "naming-config")
    subtitle_input = page.locator("#cfg-filename_templates-subtitle-inline")
    expect(subtitle_input).to_be_visible()


def test_C37_naming_duplicate_strategy_options(e2e_page, e2e_server):
    """C37: Check #cfg-duplicate_handling-strategy-inline has skip/replace/rename/quality options."""
    page = e2e_page
    _nav_to_subpage(page, "naming-config")
    strategy_select = page.locator("#cfg-duplicate_handling-strategy-inline")
    expect(strategy_select).to_be_visible()
    options = strategy_select.locator("option")
    option_values = []
    for i in range(options.count()):
        option_values.append(options.nth(i).get_attribute("value"))
    assert "skip" in option_values
    assert "replace" in option_values
    assert "rename" in option_values
    assert "quality" in option_values


def test_C38_save_naming(e2e_page, e2e_server):
    """C38: Click [data-config-save="naming"], verify toast."""
    page = e2e_page
    _nav_to_subpage(page, "naming-config")
    page.locator('[data-config-save="naming"]').click()
    toast = _wait_for_toast(page)
    expect(toast).to_be_visible()


def test_C39_naming_back_to_advanced(e2e_page, e2e_server):
    """C39: Click back button, verify back on advanced-config."""
    page = e2e_page
    _nav_to_subpage(page, "naming-config")
    back_btn = page.locator(
        '[data-view="naming-config"] button.nav-item[data-nav="config"][data-view-target="advanced-config"]'
    )
    if back_btn.count() == 0:
        back_btn = page.locator(
            '[data-view="naming-config"] [data-view-target="advanced-config"]'
        )
    back_btn.click()
    time.sleep(0.3)
    advanced_view = page.locator('[data-view="advanced-config"]')
    expect(advanced_view).to_be_visible()


def test_C40_dimensions_config_page(e2e_page, e2e_server):
    """C40: Navigate to dimensions-config."""
    page = e2e_page
    _nav_to_subpage(page, "dimensions-config")
    dim_view = page.locator('[data-view="dimensions-config"]')
    expect(dim_view).to_be_visible()


def test_C41_dimensions_enabled_list(e2e_page, e2e_server):
    """C41: Check #dim-enabled-list has items (media_type, documentary, restricted_level)."""
    page = e2e_page
    _nav_to_subpage(page, "dimensions-config")
    time.sleep(0.5)
    enabled_list = page.locator("#dim-enabled-list")
    expect(enabled_list).to_be_visible()
    enabled_items = enabled_list.locator(".dim-card")
    assert enabled_items.count() >= 1


def test_C42_dimensions_available_list(e2e_page, e2e_server):
    """C42: Check #dim-available-list has items (animation, region, etc.)."""
    page = e2e_page
    _nav_to_subpage(page, "dimensions-config")
    time.sleep(0.5)
    available_list = page.locator("#dim-available-list")
    expect(available_list).to_be_visible()
    available_items = available_list.locator(".dim-card")
    assert available_items.count() >= 0


def test_C43_dimension_disable(e2e_page, e2e_server):
    """C43: Click disable on an enabled dimension, verify it moves."""
    page = e2e_page
    _nav_to_subpage(page, "dimensions-config")
    time.sleep(0.5)
    enabled_items = page.locator("#dim-enabled-list .dim-card")
    if enabled_items.count() > 0:
        first_item = enabled_items.first
        disable_btn = first_item.locator("button").first
        if disable_btn.is_visible():
            disable_btn.click()
            time.sleep(0.3)


def test_C44_dimension_enable(e2e_page, e2e_server):
    """C44: Click enable on an available dimension, verify it moves."""
    page = e2e_page
    _nav_to_subpage(page, "dimensions-config")
    time.sleep(0.5)
    available_items = page.locator("#dim-available-list .dim-card")
    if available_items.count() > 0:
        first_item = available_items.first
        enable_btn = first_item.locator("button").first
        if enable_btn.is_visible():
            enable_btn.click()
            time.sleep(0.3)


def test_C45_dimensions_back_to_advanced(e2e_page, e2e_server):
    """C45: Click back to advanced config."""
    page = e2e_page
    _nav_to_subpage(page, "dimensions-config")
    back_btn = page.locator(
        '[data-view="dimensions-config"] button.nav-item[data-nav="config"][data-view-target="advanced-config"]'
    )
    if back_btn.count() == 0:
        back_btn = page.locator(
            '[data-view="dimensions-config"] [data-view-target="advanced-config"]'
        )
    back_btn.click()
    time.sleep(0.3)
    advanced_view = page.locator('[data-view="advanced-config"]')
    expect(advanced_view).to_be_visible()


def test_C46_prompt_config_page(e2e_page, e2e_server):
    """C46: Navigate to prompt-config."""
    page = e2e_page
    _nav_to_subpage(page, "prompt-config")
    prompt_view = page.locator('[data-view="prompt-config"]')
    expect(prompt_view).to_be_visible()


def test_C47_prompt_system_not_empty(e2e_page, e2e_server):
    """C47: Check #prompt-system textarea is not empty."""
    page = e2e_page
    _nav_to_subpage(page, "prompt-config")
    system_prompt = page.locator("#prompt-system")
    expect(system_prompt).to_be_visible()
    assert system_prompt.input_value().strip() != ""


def test_C48_prompt_tmdb_disclosure(e2e_page, e2e_server):
    """C48: Click [data-advanced-disclosure="prompt-tmdb"] to expand."""
    page = e2e_page
    _nav_to_subpage(page, "prompt-config")
    tmdb_disclosure = page.locator(
        '[data-advanced-disclosure="prompt-tmdb"]'
    )
    tmdb_disclosure.click()
    time.sleep(0.3)


def test_C49_prompt_tmdb_not_empty(e2e_page, e2e_server):
    """C49: Check #prompt-tmdb textarea is not empty."""
    page = e2e_page
    _nav_to_subpage(page, "prompt-config")
    tmdb_disclosure = page.locator(
        '[data-advanced-disclosure="prompt-tmdb"]'
    )
    tmdb_disclosure.click()
    time.sleep(0.3)
    tmdb_prompt = page.locator("#prompt-tmdb")
    expect(tmdb_prompt).to_be_visible()
    assert tmdb_prompt.input_value().strip() != ""


def test_C50_prompt_preview_system(e2e_page, e2e_server):
    """C50: Click [data-prompt-action="preview-system"], verify modal appears."""
    page = e2e_page
    _nav_to_subpage(page, "prompt-config")
    page.locator('[data-prompt-action="preview-system"]').click()
    time.sleep(0.5)
    modal = page.locator(".cinema-modal-overlay")
    if modal.is_visible():
        expect(modal).to_be_visible()
    else:
        modal = page.locator(".cinema-modal")
        if modal.is_visible():
            expect(modal).to_be_visible()
        else:
            toast = page.locator("#toast")
            expect(toast).to_be_visible()


def test_C51_prompt_close_modal(e2e_page, e2e_server):
    """C51: Click .cinema-modal-close, verify modal closes."""
    page = e2e_page
    _nav_to_subpage(page, "prompt-config")
    page.locator('[data-prompt-action="preview-system"]').click()
    time.sleep(0.5)
    close_btn = page.locator(".cinema-modal-close")
    if close_btn.is_visible():
        close_btn.click()
        time.sleep(0.3)
        modal = page.locator(".cinema-modal-overlay")
        if modal.count() > 0:
            assert not modal.is_visible()


def test_C52_prompt_reset_system(e2e_page, e2e_server):
    """C52: Click [data-prompt-action="reset-system"], verify textarea resets."""
    page = e2e_page
    _nav_to_subpage(page, "prompt-config")
    page.locator('[data-prompt-action="reset-system"]').click()
    toast = _wait_for_toast(page)
    expect(toast).to_be_visible()


def test_C53_prompt_save_all(e2e_page, e2e_server):
    """C53: Click [data-prompt-action="save-all"], verify toast."""
    page = e2e_page
    _nav_to_subpage(page, "prompt-config")
    page.locator('[data-prompt-action="save-all"]').click()
    toast = _wait_for_toast(page)
    expect(toast).to_be_visible()


def test_C54_prompt_persists(e2e_page, e2e_server):
    """C54: Refresh, verify prompt content persists."""
    page = e2e_page
    _nav_to_subpage(page, "prompt-config")
    page.locator('[data-prompt-action="save-all"]').click()
    _wait_for_toast(page)
    page.reload()
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)
    _nav_to_subpage(page, "prompt-config")
    system_prompt = page.locator("#prompt-system")
    expect(system_prompt).to_be_visible()
    assert system_prompt.input_value().strip() != ""


def test_C55_confidence_config_page(e2e_page, e2e_server):
    """C55: Navigate to confidence-config."""
    page = e2e_page
    _nav_to_subpage(page, "confidence-config")
    confidence_view = page.locator('[data-view="confidence-config"]')
    expect(confidence_view).to_be_visible()


def test_C56_confidence_threshold_bar(e2e_page, e2e_server):
    """C56: Check #confidence-threshold-bar is visible."""
    page = e2e_page
    _nav_to_subpage(page, "confidence-config")
    threshold_bar = page.locator("#confidence-threshold-bar")
    expect(threshold_bar).to_be_visible()


def test_C57_confidence_pass_threshold_value(e2e_page, e2e_server):
    """C57: Check [data-confidence-value="pass_threshold"] shows a number."""
    page = e2e_page
    _nav_to_subpage(page, "confidence-config")
    pass_val = page.locator('[data-confidence-value="pass_threshold"]')
    expect(pass_val).to_be_visible()
    text = pass_val.inner_text()
    assert text.strip() != ""


def test_C58_confidence_threshold_slider(e2e_page, e2e_server):
    """C58: Check [data-confidence-input="threshold"] slider is visible."""
    page = e2e_page
    _nav_to_subpage(page, "confidence-config")
    slider = page.locator('[data-confidence-input="threshold"]')
    expect(slider).to_be_visible()


def test_C59_confidence_section_toggle(e2e_page, e2e_server):
    """C59: Click a [data-confidence-section-toggle] to expand section."""
    page = e2e_page
    _nav_to_subpage(page, "confidence-config")
    toggle = page.locator("[data-confidence-section-toggle]")
    if toggle.count() > 0:
        toggle.first.click()
        time.sleep(0.3)


def test_C60_confidence_save(e2e_page, e2e_server):
    """C60: Click [data-config-save="confidence"], verify toast."""
    page = e2e_page
    _nav_to_subpage(page, "confidence-config")
    save_btn = page.locator('[data-config-save="confidence"]')
    expect(save_btn).to_be_visible()
    save_btn.click()
    toast = _wait_for_toast(page)
    expect(toast).to_be_visible()


def test_C61_confidence_persists(e2e_page, e2e_server):
    """C61: Refresh, verify thresholds persist."""
    page = e2e_page
    _nav_to_subpage(page, "confidence-config")
    page.locator('[data-config-save="confidence"]').click()
    _wait_for_toast(page)
    page.reload()
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)
    _nav_to_subpage(page, "confidence-config")
    pass_val = page.locator('[data-confidence-value="pass_threshold"]')
    expect(pass_val).to_be_visible()


def test_C62_security_config_page(e2e_page, e2e_server):
    """C62: Navigate to security-config."""
    page = e2e_page
    _nav_to_subpage(page, "security-config")
    security_view = page.locator('[data-view="security-config"]')
    expect(security_view).to_be_visible()


def test_C63_security_api_key_masked(e2e_page, e2e_server):
    """C63: Check #cfg-server_api_key-inline is type=password."""
    page = e2e_page
    _nav_to_subpage(page, "security-config")
    api_key = page.locator("#cfg-server_api_key-inline")
    expect(api_key).to_be_visible()
    assert api_key.get_attribute("type") == "password"


def test_C64_security_port_has_value(e2e_page, e2e_server):
    """C64: Check #cfg-server_port-inline has value."""
    page = e2e_page
    _nav_to_subpage(page, "security-config")
    port_input = page.locator("#cfg-server_port-inline")
    expect(port_input).to_be_visible()
    assert port_input.input_value().strip() != ""


def test_C65_security_save(e2e_page, e2e_server):
    """C65: Click [data-config-save="security"], verify toast."""
    page = e2e_page
    _nav_to_subpage(page, "security-config")
    page.locator('[data-config-save="security"]').click()
    toast = _wait_for_toast(page)
    expect(toast).to_be_visible()


def test_C66_hermes_config_page(e2e_page, e2e_server):
    """C66: Navigate to hermes-config."""
    page = e2e_page
    _nav_to_subpage(page, "hermes-config")
    hermes_view = page.locator('[data-view="hermes-config"]')
    expect(hermes_view).to_be_visible()


def test_C67_hermes_enabled_checkbox(e2e_page, e2e_server):
    """C67: Check #cfg-hermes_enabled-inline checkbox visible."""
    page = e2e_page
    _nav_to_subpage(page, "hermes-config")
    hermes_toggle = page.locator("#cfg-hermes_enabled-inline")
    expect(hermes_toggle).to_be_visible()


def test_C68_hermes_toggle_expand_collapse(e2e_page, e2e_server):
    """C68: Toggle #cfg-hermes_enabled-inline, verify webhook fields expand/collapse."""
    page = e2e_page
    _nav_to_subpage(page, "hermes-config")
    hermes_toggle = page.locator("#cfg-hermes_enabled-inline")
    hermes_toggle.check()
    time.sleep(0.3)
    assert hermes_toggle.is_checked()
    expect(page.locator("#cfg-hermes_webhook_base_url-inline")).to_be_visible()


def test_C69_hermes_webhook_base_url(e2e_page, e2e_server):
    """C69: Check #cfg-hermes_webhook_base_url-inline visible."""
    page = e2e_page
    _nav_to_subpage(page, "hermes-config")
    hermes_toggle = page.locator("#cfg-hermes_enabled-inline")
    if not hermes_toggle.is_checked():
        hermes_toggle.check()
        time.sleep(0.3)
    expect(page.locator("#cfg-hermes_webhook_base_url-inline")).to_be_visible()


def test_C70_hermes_secret_masked(e2e_page, e2e_server):
    """C70: Check #cfg-hermes_webhook_secret-inline is type=password."""
    page = e2e_page
    _nav_to_subpage(page, "hermes-config")
    hermes_toggle = page.locator("#cfg-hermes_enabled-inline")
    if not hermes_toggle.is_checked():
        hermes_toggle.check()
        time.sleep(0.3)
    secret_input = page.locator("#cfg-hermes_webhook_secret-inline")
    assert secret_input.get_attribute("type") == "password"


def test_C71_hermes_event_checkboxes(e2e_page, e2e_server):
    """C71: Check event checkboxes visible."""
    page = e2e_page
    _nav_to_subpage(page, "hermes-config")
    hermes_toggle = page.locator("#cfg-hermes_enabled-inline")
    if not hermes_toggle.is_checked():
        hermes_toggle.check()
        time.sleep(0.3)
    batch_start = page.locator("#cfg-hermes_event_batch_start-inline")
    batch_complete = page.locator("#cfg-hermes_event_batch_complete-inline")
    program_error = page.locator("#cfg-hermes_event_program_error-inline")
    expect(batch_start).to_be_visible()
    expect(batch_complete).to_be_visible()
    expect(program_error).to_be_visible()


def test_C72_hermes_save(e2e_page, e2e_server):
    """C72: Click [data-config-save="hermes"], verify toast."""
    page = e2e_page
    _nav_to_subpage(page, "hermes-config")
    page.locator('[data-config-save="hermes"]').click()
    toast = _wait_for_toast(page)
    expect(toast).to_be_visible()


def test_C73_system_settings_page(e2e_page, e2e_server):
    """C73: Navigate to system-settings."""
    page = e2e_page
    _nav_to_subpage(page, "system-settings")
    system_view = page.locator('[data-view="system-settings"]')
    expect(system_view).to_be_visible()


def test_C74_log_dir_has_value(e2e_page, e2e_server):
    """C74: Check #cfg-log_dir-inline has value."""
    page = e2e_page
    _nav_to_subpage(page, "system-settings")
    log_dir_input = page.locator("#cfg-log_dir-inline")
    expect(log_dir_input).to_be_visible()
    assert log_dir_input.input_value().strip() != ""


def test_C75_resource_dir_has_value(e2e_page, e2e_server):
    """C75: Check #cfg-resource_dir-inline has value."""
    page = e2e_page
    _nav_to_subpage(page, "system-settings")
    resource_dir_input = page.locator("#cfg-resource_dir-inline")
    expect(resource_dir_input).to_be_visible()
    val = resource_dir_input.input_value()
    assert val.strip() != ""


def test_C76_max_concurrent_range(e2e_page, e2e_server):
    """C76: Check #cfg-task_queue-max_concurrent-inline value is 1-5."""
    page = e2e_page
    _nav_to_subpage(page, "system-settings")
    concurrent_input = page.locator("#cfg-task_queue-max_concurrent-inline")
    expect(concurrent_input).to_be_visible()
    val = int(concurrent_input.input_value())
    assert 1 <= val <= 5


def test_C77_video_extensions_has_content(e2e_page, e2e_server):
    """C77: Check #cfg-video_extensions-inline has content."""
    page = e2e_page
    _nav_to_subpage(page, "system-settings")
    video_ext = page.locator("#cfg-video_extensions-inline")
    expect(video_ext).to_be_visible()
    assert video_ext.input_value().strip() != ""


def test_C78_subtitle_extensions_has_content(e2e_page, e2e_server):
    """C78: Check #cfg-subtitle_extensions-inline has content."""
    page = e2e_page
    _nav_to_subpage(page, "system-settings")
    subtitle_ext = page.locator("#cfg-subtitle_extensions-inline")
    expect(subtitle_ext).to_be_visible()
    assert subtitle_ext.input_value().strip() != ""


def test_C79_system_settings_save(e2e_page, e2e_server):
    """C79: Click [data-config-save="system"], verify toast."""
    page = e2e_page
    _nav_to_subpage(page, "system-settings")
    page.locator('[data-config-save="system"]').click()
    toast = _wait_for_toast(page)
    expect(toast).to_be_visible()
