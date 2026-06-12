"""
Inspect the path rules editor page to debug why Chinese+English
side-by-side layout is not working.
"""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # Navigate to the app
    page.goto('http://localhost:9855', timeout=15000)
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(2000)

    # Check if components.css is loaded
    print("=== CSS files loaded ===")
    stylesheets = page.locator('link[rel="stylesheet"]').all()
    for s in stylesheets:
        href = s.get_attribute('href') or ''
        print(f"  {href}")

    print()

    # Navigate to config main view first
    print("=== Clicking 配置 nav ===")
    config_nav = page.locator('[data-nav="config"]:visible').first
    config_nav.click()
    page.wait_for_timeout(2000)
    page.wait_for_load_state('networkidle')
    page.screenshot(path='scripts/rules_step1_config.png', full_page=True)

    # Click "入库规则" stage card
    print("\n=== Clicking 入库规则 stage ===")
    rules_stage = page.locator('[data-config-stage="rules"]:visible')
    print(f"  found: {rules_stage.count()}")
    if rules_stage.count() > 0:
        rules_stage.first.click()
        page.wait_for_timeout(2000)
        page.wait_for_load_state('networkidle')

    # Take a screenshot of the current state
    page.screenshot(path='scripts/rules_page_full.png', full_page=True)
    print("\nFull page screenshot saved to scripts/rules_page_full.png")

    # Dump console logs
    console_logs = []
    page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))

    # Log any JS errors
    page.on("pageerror", lambda err: console_logs.append(f"[PAGE ERROR] {err}"))

    # Wait and check again
    page.wait_for_timeout(1000)

    # Try to add a rule by clicking the "+" button
    print("\n=== Adding a rule ===")
    add_btn = page.locator('[data-rule-action="add"]')
    print(f"  add button found: {add_btn.count()}")
    if add_btn.count() > 0:
        add_btn.first.click()
        page.wait_for_timeout(2000)

    page.screenshot(path='scripts/rules_after_add.png', full_page=True)
    print("After add screenshot saved")

    # Check what rule elements exist now
    print("\n=== Rule elements ===")
    for sel in ['.rule-inline-item', '.rule-inline-card', '.rule-card', '.rule-condition-label', '.rule-condition-item',
                '[data-rule-action]', '.rules-inline-list']:
        count = page.locator(sel).count()
        if count > 0:
            print(f"  {sel}: {count}")
            if count <= 2:
                for i, el in enumerate(page.locator(sel).all()):
                    html = el.inner_html()[:300]
                    print(f"    [{i}] {html}")

    # Check the rules-inline-list content
    list_el = page.locator('#rules-inline-list')
    if list_el.count() > 0:
        html = list_el.first.inner_html()
        print(f"\n  #rules-inline-list HTML ({len(html)} chars):")
        print(html[:2000])

    # Click the "edit" button on the first rule
    print("\n=== Closing overlay if any ===")
    # Try to dismiss any open modals
    page.evaluate("""() => {
        const overlays = document.querySelectorAll('.cinema-modal-overlay');
        overlays.forEach(o => { o.style.display = 'none'; });
    }""")
    page.wait_for_timeout(500)

    print("\n=== Clicking edit on first rule ===")
    edit_btn = page.locator('[data-rule-action="edit"]').first
    print(f"  edit button found: {edit_btn.count()}")
    if edit_btn.count() > 0:
        # Force click bypassing overlay
        edit_btn.evaluate("el => el.click()")
        page.wait_for_timeout(2000)

    page.screenshot(path='scripts/rules_edit_mode.png', full_page=True)
    print("Edit mode screenshot saved")

    # Now check what elements exist in edit mode
    print("\n=== Labels in edit modal ===")
    labels_in_modal = page.evaluate("""() => {
        const modal = document.querySelector('.cinema-modal');
        if (!modal) return 'No modal found';
        const labels = modal.querySelectorAll('label.cinema-modal-field');
        return Array.from(labels).map(l => ({
            html: l.innerHTML.substring(0, 300),
            text: l.textContent.substring(0, 80)
        }));
    }""")
    if isinstance(labels_in_modal, str):
        print(f"  {labels_in_modal}")
    else:
        for i, l in enumerate(labels_in_modal):
            print(f"  [{i}] text='{l['text']}'")
            print(f"      html='{l['html'][:200]}'")

    # Check if .cinema-modal-field-code exists
    code_els = page.locator('.cinema-modal-field-code').all()
    print(f"\n  .cinema-modal-field-code count: {len(code_els)}")
    for i, el in enumerate(code_els):
        print(f"  [{i}] text='{el.inner_text()}'")

    browser.close()
    print("\nDone.")