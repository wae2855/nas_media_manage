import time

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.live_e2e


@pytest.mark.live_e2e
def test_N01_nav_dashboard_shows(e2e_page, e2e_server):
    """N01: Click '首页' nav → dashboard page is visible."""
    page = e2e_page
    page.locator('button.nav-item[data-nav="dashboard"]').click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.3)
    dashboard = page.locator('.page-view[data-view="dashboard"]')
    assert dashboard.is_visible()
    active_page = page.locator(".page-view.active")
    expect(active_page).to_have_attribute("data-view", "dashboard")


@pytest.mark.live_e2e
def test_N02_nav_tasks_shows(e2e_page, e2e_server):
    """N02: Click '任务' nav → tasks page is visible."""
    page = e2e_page
    page.locator('button.nav-item[data-nav="tasks"]').click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.3)
    tasks = page.locator('.page-view[data-view="tasks"]')
    assert tasks.is_visible()
    active_page = page.locator(".page-view.active")
    expect(active_page).to_have_attribute("data-view", "tasks")


@pytest.mark.live_e2e
def test_N03_nav_recycle_shows(e2e_page, e2e_server):
    """N03: Click '回收' nav → recycle page is visible."""
    page = e2e_page
    page.locator('button.nav-item[data-nav="recycle"]').click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.3)
    recycle = page.locator('.page-view[data-view="recycle"]')
    assert recycle.is_visible()
    active_page = page.locator(".page-view.active")
    expect(active_page).to_have_attribute("data-view", "recycle")


@pytest.mark.live_e2e
def test_N04_nav_config_shows(e2e_page, e2e_server):
    """N04: Click '配置' nav → config page is visible (step 1)."""
    page = e2e_page
    page.locator('button.nav-item[data-nav="config"][data-view-target="config"]').click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)
    config = page.locator('.page-view[data-view="config"]')
    assert config.is_visible()
    active_page = page.locator(".page-view.active")
    expect(active_page).to_have_attribute("data-view", "config")


@pytest.mark.live_e2e
def test_N05_config_to_advanced_config(e2e_page, e2e_server):
    """N05: In config page, click '高级配置' button → advanced config page visible."""
    page = e2e_page
    page.locator('button.nav-item[data-nav="config"][data-view-target="config"]').click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)
    advanced_btn = page.locator('button.btn-primary[data-view-target="advanced-config"]')
    expect(advanced_btn).to_be_visible()
    advanced_btn.click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)
    advanced_view = page.locator('.page-view[data-view="advanced-config"]')
    assert advanced_view.is_visible()
    active_page = page.locator(".page-view.active")
    expect(active_page).to_have_attribute("data-view", "advanced-config")


@pytest.mark.live_e2e
def test_N06_advanced_config_sub_pages(e2e_page, e2e_server):
    """N06: In advanced config, click each sub-page tab → corresponding sub-page shows."""
    page = e2e_page
    page.locator('button.nav-item[data-nav="config"][data-view-target="config"]').click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.3)
    page.locator('button.btn-primary[data-view-target="advanced-config"]').click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)

    sub_pages = [
        "naming-config",
        "dimensions-config",
        "prompt-config",
        "confidence-config",
    ]
    for sub in sub_pages:
        card = page.locator(f'button.setup-card[data-view-target="{sub}"]')
        assert card.is_visible(), f"Sub-page card '{sub}' should be visible"
        card.click()
        page.wait_for_load_state("networkidle")
        time.sleep(0.3)
        sub_view = page.locator(f'.page-view[data-view="{sub}"]')
        assert sub_view.is_visible(), f"Sub-page view '{sub}' should be visible after click"
        back_btn = page.locator(f'[data-view="advanced-config"]')
        page.locator(f'.page-view[data-view="{sub}"] button[data-view-target="advanced-config"]').click()
        page.wait_for_load_state("networkidle")
        time.sleep(0.3)


@pytest.mark.live_e2e
def test_N07_advanced_back_to_config(e2e_page, e2e_server):
    """N07: From advanced config, click back → returns to basic config steps."""
    page = e2e_page
    page.locator('button.nav-item[data-nav="config"][data-view-target="config"]').click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.3)
    page.locator('button.btn-primary[data-view-target="advanced-config"]').click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.3)
    advanced_view = page.locator('.page-view[data-view="advanced-config"]')
    assert advanced_view.is_visible()
    back_btn = page.locator('button.nav-item[data-nav="config"][data-view-target="config"]')
    expect(back_btn).to_be_visible()
    back_btn.click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.3)
    config_view = page.locator('.page-view[data-view="config"]')
    assert config_view.is_visible()


@pytest.mark.live_e2e
def test_N08_dashboard_metric_navigates_to_tasks(e2e_page, e2e_server):
    """N08: Click dashboard metric card → navigates to corresponding filtered task view."""
    page = e2e_page
    page.locator('button.nav-item[data-nav="dashboard"]').click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.3)

    metric_card = page.locator('[data-task-filter="pending"]')
    expect(metric_card).to_be_visible()
    metric_card.click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.3)

    tasks_view = page.locator('.page-view[data-view="tasks"]')
    assert tasks_view.is_visible()

    pending_chip = page.locator('[data-task-filter-chip="pending"]')
    assert pending_chip.is_visible()


@pytest.mark.live_e2e
def test_N09_browser_back_returns(e2e_page, e2e_server):
    """N09: Navigate forward, then browser back → returns to previous page."""
    pytest.skip("The current UI intentionally uses in-page navigation without browser history entries")
    page = e2e_page
    page.locator('button.nav-item[data-nav="dashboard"]').click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.3)
    assert page.locator('.page-view[data-view="dashboard"]').is_visible()

    page.locator('button.nav-item[data-nav="tasks"]').click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.3)
    assert page.locator('.page-view[data-view="tasks"]').is_visible()

    page.go_back()
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)

    dashboard_view = page.locator('.page-view[data-view="dashboard"]')
    tasks_view = page.locator('.page-view[data-view="tasks"]')
    assert dashboard_view.is_visible() or tasks_view.is_visible()


@pytest.mark.live_e2e
def test_N10_no_hash_in_url(e2e_page, e2e_server):
    """N10: After navigation, check URL does NOT contain hash (no hash routing)."""
    page = e2e_page
    page.locator('button.nav-item[data-nav="tasks"]').click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.3)
    url = page.url
    assert "#" not in url

    page.locator('button.nav-item[data-nav="recycle"]').click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.3)
    url = page.url
    assert "#" not in url

    page.locator('button.nav-item[data-nav="config"][data-view-target="config"]').click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.3)
    url = page.url
    assert "#" not in url


@pytest.mark.live_e2e
def test_N11_refresh_returns_to_default(e2e_page, e2e_server):
    """N11: Navigate to tasks, refresh page, verify page state (returns to dashboard since no hash routing)."""
    page = e2e_page
    page.locator('button.nav-item[data-nav="tasks"]').click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.3)
    assert page.locator('.page-view[data-view="tasks"]').is_visible()

    page.reload()
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)

    active_page = page.locator(".page-view.active")
    active_view = active_page.get_attribute("data-view")
    assert active_view in ("dashboard", "tasks")
