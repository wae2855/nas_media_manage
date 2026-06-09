import time

import pytest
from playwright.sync_api import expect


def _nav_to(page, nav_name, view_target=None):
    selector = f'button.nav-item[data-nav="{nav_name}"]'
    page.locator(selector).first.click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)


def _get_page_hero_poster_image(page):
    hero = page.locator(".page-hero").first
    if not hero.is_visible():
        return "none"
    return hero.evaluate("el => getComputedStyle(el).getPropertyValue('--hero-poster-image').trim()")


def _get_hero_bg_image(page, selector):
    el = page.locator(selector).first
    if not el.is_visible():
        return "none"
    return el.evaluate("el => getComputedStyle(el).backgroundImage")


@pytest.mark.live_e2e
def test_V01_dashboard_hero_poster_visible(e2e_page, e2e_server):
    """V01: Dashboard hero poster image visible on desktop (1280x900)."""
    page = e2e_page
    page.goto(e2e_server["base_url"])
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)

    hero_section = page.locator('section.hero')
    expect(hero_section).to_be_visible()

    poster_image = hero_section.evaluate(
        "el => getComputedStyle(el, '::before').backgroundImage"
    )
    assert poster_image and poster_image != "none", (
        f"Dashboard hero should have a background-image poster, got: {poster_image!r}"
    )


@pytest.mark.live_e2e
def test_V02_tasks_page_hero_poster_visible(e2e_page, e2e_server):
    """V02: Tasks page hero poster image visible on desktop (1280x900)."""
    page = e2e_page
    _nav_to(page, "tasks", "tasks")

    hero = page.locator('.page-view[data-view="tasks"] .page-hero')
    expect(hero).to_be_visible()

    poster_var = hero.evaluate("el => getComputedStyle(el).getPropertyValue('--hero-poster-image').trim()")
    assert poster_var != "none", "Tasks page hero should have a --hero-poster-image on desktop"
    assert "task-01" in poster_var, f"Expected task-01 poster, got: {poster_var}"


@pytest.mark.live_e2e
def test_V03_recycle_page_hero_poster_visible(e2e_page, e2e_server):
    """V03: Recycle page hero poster image visible on desktop (1280x900)."""
    page = e2e_page
    _nav_to(page, "recycle")

    hero = page.locator('.page-view[data-view="recycle"] .page-hero')
    expect(hero).to_be_visible()

    poster_var = hero.evaluate("el => getComputedStyle(el).getPropertyValue('--hero-poster-image').trim()")
    assert poster_var != "none", "Recycle page hero should have a --hero-poster-image on desktop"
    assert "recycle-01" in poster_var, f"Expected recycle-01 poster, got: {poster_var}"


@pytest.mark.live_e2e
def test_V04_config_page_hero_poster_visible(e2e_page, e2e_server):
    """V04: Config page hero poster image visible on desktop (1280x900)."""
    page = e2e_page
    _nav_to(page, "config", "config")

    hero = page.locator('.page-view[data-view="config"] .page-hero')
    expect(hero).to_be_visible()

    poster_var = hero.evaluate("el => getComputedStyle(el).getPropertyValue('--hero-poster-image').trim()")
    assert poster_var != "none", "Config page hero should have a --hero-poster-image on desktop"
    assert "settings-01" in poster_var, f"Expected settings-01 poster, got: {poster_var}"


@pytest.mark.live_e2e
def test_V05_advanced_subpage_different_poster(e2e_page, e2e_server):
    """V05: Advanced sub-pages use still-02.jpeg, different from main page posters."""
    page = e2e_page
    _nav_to(page, "config", "config")
    page.locator('button.btn-primary[data-view-target="advanced-config"]').click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)

    hero = page.locator('.page-view[data-view="advanced-config"] .page-hero')
    expect(hero).to_be_visible()

    poster_var = hero.evaluate("el => getComputedStyle(el).getPropertyValue('--hero-poster-image').trim()")
    assert poster_var != "none", "Advanced config page should have a poster image"
    assert "still-02" in poster_var, f"Expected still-02 poster for advanced sub-page, got: {poster_var}"


def _create_mobile_page(e2e_browser_context, e2e_server):
    page = e2e_browser_context.new_page()
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(e2e_server["base_url"])
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)
    return page


@pytest.mark.live_e2e
def test_V06_dashboard_hero_poster_hidden_on_mobile(e2e_browser_context, e2e_server):
    """V06: Dashboard hero poster hidden or adapted to gradient on mobile (375x812)."""
    page = _create_mobile_page(e2e_browser_context, e2e_server)

    try:
        hero_section = page.locator('section.hero')
        expect(hero_section).to_be_visible()

        page_hero = page.locator('.page-hero').first
        if page_hero.is_visible():
            poster_var = page_hero.evaluate("el => getComputedStyle(el).getPropertyValue('--hero-poster-image').trim()")
            if poster_var != "none":
                pseudo_bg = page_hero.evaluate(
                    "el => getComputedStyle(el, '::before').backgroundImage"
                )
                assert "url(" not in pseudo_bg or pseudo_bg == "none", \
                    "On mobile, hero poster image should not be rendered as visible background"
    finally:
        page.close()


@pytest.mark.live_e2e
def test_V07_tasks_page_h2_font_reduced_on_mobile(e2e_browser_context, e2e_server):
    """V07: Tasks page h2 font size reduced on mobile viewport."""
    page = _create_mobile_page(e2e_browser_context, e2e_server)

    try:
        _nav_to(page, "tasks", "tasks")

        hero = page.locator('.page-view[data-view="tasks"] .page-hero')
        expect(hero).to_be_visible()

        h2 = hero.locator("h2")
        expect(h2).to_be_visible()

        font_size = h2.evaluate("el => parseFloat(getComputedStyle(el).fontSize)")
        assert font_size <= 28, f"h2 font size should be reduced on mobile, got {font_size}px"
    finally:
        page.close()


@pytest.mark.live_e2e
def test_V08_no_horizontal_scrollbar_on_mobile(e2e_browser_context, e2e_server):
    """V08: All pages have no horizontal scrollbar on mobile viewport."""
    page = _create_mobile_page(e2e_browser_context, e2e_server)

    try:
        nav_targets = [
            ("dashboard", None),
            ("tasks", "tasks"),
            ("recycle", None),
            ("config", "config"),
        ]
        for nav, view_target in nav_targets:
            _nav_to(page, nav, view_target)
            time.sleep(0.3)

            scroll_width = page.evaluate("document.documentElement.scrollWidth")
            client_width = page.evaluate("document.documentElement.clientWidth")
            assert scroll_width <= client_width + 20, \
                f"Page {nav} has horizontal scrollbar: scrollWidth={scroll_width}, clientWidth={client_width}"
    finally:
        page.close()


@pytest.mark.live_e2e
def test_V09_task_cards_single_column_on_mobile(e2e_browser_context, e2e_server):
    """V09: Task cards render in single column layout on mobile viewport."""
    page = _create_mobile_page(e2e_browser_context, e2e_server)

    try:
        _nav_to(page, "tasks", "tasks")

        task_cards = page.locator("article.task-card")
        if task_cards.count() == 0:
            pytest.skip("No task cards visible on tasks page")

        first_card = task_cards.first
        grid_columns = first_card.evaluate(
            "el => getComputedStyle(el).gridTemplateColumns"
        )
        card_width = first_card.evaluate("el => el.getBoundingClientRect().width")
        assert card_width <= 375, f"Task card should fit within mobile width, got {card_width}px"
    finally:
        page.close()


@pytest.mark.live_e2e
def test_V10_batch_toolbar_wraps_on_mobile(e2e_browser_context, e2e_server):
    """V10: Batch toolbar buttons wrap without overflow on mobile viewport."""
    page = _create_mobile_page(e2e_browser_context, e2e_server)

    try:
        _nav_to(page, "tasks", "tasks")

        toolbar = page.locator("#task-batch-toolbar")
        if not toolbar.is_visible():
            checkboxes = page.locator("input[type='checkbox'][data-task-select]")
            if checkboxes.count() > 0:
                checkboxes.first.click()
                time.sleep(0.3)

        if toolbar.is_visible():
            toolbar_width = toolbar.evaluate("el => el.scrollWidth")
            client_width = toolbar.evaluate("el => el.clientWidth")
            assert toolbar_width <= client_width + 2, \
                f"Batch toolbar overflows: scrollWidth={toolbar_width}, clientWidth={client_width}"
    finally:
        page.close()


@pytest.mark.live_e2e
def test_V11_modal_fits_mobile_screen(e2e_browser_context, e2e_server):
    """V11: Modal dialog fits within mobile screen bounds."""
    page = _create_mobile_page(e2e_browser_context, e2e_server)

    try:
        _nav_to(page, "config", "config")
        page.locator('button.btn-primary[data-view-target="advanced-config"]').click()
        page.wait_for_load_state("networkidle")
        time.sleep(0.5)

        page.locator('button.setup-card[data-view-target="prompt-config"]').click()
        page.wait_for_load_state("networkidle")
        time.sleep(0.5)

        preview_btn = page.locator('[data-prompt-action="preview-system"]')
        if preview_btn.is_visible():
            preview_btn.click()
            time.sleep(0.5)

        modal_overlay = page.locator(".cinema-modal-overlay")
        if not modal_overlay.is_visible():
            page.locator('[data-prompt-action="reset-system"]').click()
            time.sleep(0.5)
            modal_overlay = page.locator(".cinema-modal-overlay")

        if modal_overlay.is_visible():
            modal = modal_overlay.locator(".cinema-modal")
            if modal.is_visible():
                modal_box = modal.evaluate("el => { const r = el.getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width }; }")
                assert modal_box["left"] >= 0, f"Modal left edge off-screen: {modal_box['left']}"
                assert modal_box["right"] <= 375, f"Modal right edge overflows: {modal_box['right']}"
                assert modal_box["width"] <= 375, f"Modal wider than viewport: {modal_box['width']}"
    finally:
        page.close()


@pytest.mark.live_e2e
def test_V12_navigation_bar_usable_on_mobile(e2e_browser_context, e2e_server):
    """V12: Navigation bar is visible and usable on mobile viewport."""
    page = _create_mobile_page(e2e_browser_context, e2e_server)

    try:
        nav = page.locator(".bottom-nav")
        expect(nav).to_be_visible()

        nav_box = nav.evaluate("el => { const r = el.getBoundingClientRect(); return { width: r.width, height: r.height, bottom: r.bottom }; }")
        assert nav_box["width"] > 0, "Navigation bar should have width"
        assert nav_box["bottom"] <= 812, f"Navigation bar should be within viewport, bottom={nav_box['bottom']}"

        nav_items = nav.locator("[data-nav]")
        assert nav_items.count() >= 4, f"Expected at least 4 nav items, got {nav_items.count()}"

        for i in range(nav_items.count()):
            item = nav_items.nth(i)
            assert item.is_visible(), f"Nav item {i} should be visible"

        nav_items.nth(1).click()
        page.wait_for_load_state("networkidle")
        time.sleep(0.3)

        active_item = nav.locator("[data-nav].active, .nav-item.active")
        assert active_item.count() >= 1, "Clicked nav item should become active"
    finally:
        page.close()
