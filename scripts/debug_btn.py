from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    errors = []
    page.on("pageerror", lambda err: errors.append(str(err)))
    console_logs = []
    page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))

    page.goto("http://localhost:9855")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    page.locator("nav.bottom-nav button[data-nav='config'][data-view-target='config']").click()
    page.wait_for_timeout(1000)
    page.click("button[data-config-stage='ai']")
    page.wait_for_timeout(1000)

    btn = page.locator("#btn-ai-scrape-demo")
    print(f"Button exists: {btn.count() > 0}")
    print(f"Button visible: {btn.is_visible()}")
    print(f"Button text: {btn.text_content()}")
    print(f"Button disabled: {btn.is_disabled()}")

    print("\n--- Clicking button ---")
    btn.click()
    page.wait_for_timeout(1000)

    modal = page.locator("#ai-scrape-demo-modal")
    print(f"Modal visible after click: {modal.is_visible()}")
    print(f"Modal display style: {modal.evaluate('el => el.style.display')}")

    page.screenshot(path="/tmp/debug_btn_click.png", full_page=True)

    print(f"\n=== JS Errors: {len(errors)} ===")
    for e in errors:
        print(f"  {e}")

    print(f"\n=== Console (last 20) ===")
    for m in console_logs[-20:]:
        print(f"  {m}")

    browser.close()
