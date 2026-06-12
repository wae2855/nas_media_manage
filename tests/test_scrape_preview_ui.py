from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    errors = []
    page.on("console", lambda msg: errors.append(f"[{msg.type}] {msg.text}") if msg.type in ("error", "warning") else None)

    page.goto("http://localhost:9855/")
    page.wait_for_load_state("networkidle")

    result = page.evaluate("""() => {
        const r = {};

        // Expand AI config via setView
        setView('config-llm', 'config');

        // Force expand collapse bodies
        document.querySelectorAll('.config-collapse-body').forEach(el => {
            el.style.display = 'block';
            el.classList.add('open');
        });

        // Check AI 辅助 title
        const assistCard = document.getElementById('ai-assist-card');
        const assistB = assistCard ? assistCard.querySelector('.config-collapse-header b') : null;
        r.assistTitle = assistB ? assistB.textContent.trim() : '?';

        // Check AI 辅助 usage notes
        const assistBody = document.getElementById('ai-assist-body');
        const assistText = assistBody ? assistBody.textContent : '';
        r.assistHasUsageTitle = assistText.includes('标题清洗');
        r.assistHasUsageClean = assistText.includes('源目录智能清理');
        r.assistHasVendors = assistText.includes('MiniMax') || assistText.includes('DeepSeek');

        // Check AI 搜索增强 title
        const scrapeCard = document.getElementById('ai-scrape-card');
        const scrapeB = scrapeCard ? scrapeCard.querySelector('.config-collapse-header b') : null;
        r.scrapeTitle = scrapeB ? scrapeB.textContent.trim() : '?';

        // Check no web_search toggle
        r.wsToggleExists = !!document.getElementById('cfg-llm_web_search_enabled');

        // Check vendors at top
        const scrapeBody = document.getElementById('ai-scrape-body');
        const scrapeText = scrapeBody ? scrapeBody.textContent : '';
        r.scrapeHasZhipu = scrapeText.includes('智谱 GLM');
        r.scrapeHasQwen = scrapeText.includes('通义千问');
        r.scrapeHasKimi = scrapeText.includes('Kimi');
        r.scrapeHasMCP = scrapeText.includes('MCP');

        // Check usage notes
        r.scrapeHasAiScrape = scrapeText.includes('纯 AI 刮削');
        r.scrapeHasSeries = scrapeText.includes('整剧刮削');
        r.scrapeHasSupplement = scrapeText.includes('维度补缺');

        // Check scrape mode hint
        setView('config-scrape', 'config');
        document.querySelectorAll('.config-collapse-body').forEach(el => {
            el.style.display = 'block';
            el.classList.add('open');
        });
        const modeHint = document.getElementById('cfg-scrape-mode-hint');
        r.modeHint = modeHint ? modeHint.textContent.trim() : '?';

        return r;
    }""")

    passed = True
    print(f"AI 辅助标题: {result['assistTitle']}")
    if 'AI 辅助' not in result['assistTitle']:
        print("FAIL: Expected 'AI 辅助'")
        passed = False

    print(f"AI 辅助使用场景: 标题清洗={'✅' if result['assistHasUsageTitle'] else '❌'}, 源目录清理={'✅' if result['assistHasUsageClean'] else '❌'}, 厂商列表={'✅' if result['assistHasVendors'] else '❌'}")

    print(f"AI 搜索增强标题: {result['scrapeTitle']}")
    if 'AI 搜索增强' not in result['scrapeTitle']:
        print("FAIL: Expected 'AI 搜索增强'")
        passed = False

    print(f"联网搜索开关: {'已删除 ✅' if not result['wsToggleExists'] else '仍存在 ❌'}")
    if result['wsToggleExists']:
        passed = False

    print(f"厂商列表: 智谱={'✅' if result['scrapeHasZhipu'] else '❌'}, 通义={'✅' if result['scrapeHasQwen'] else '❌'}, Kimi={'✅' if result['scrapeHasKimi'] else '❌'}, MCP={'✅' if result['scrapeHasMCP'] else '❌'}")
    print(f"使用场景: 纯AI刮削={'✅' if result['scrapeHasAiScrape'] else '❌'}, 整剧刮削={'✅' if result['scrapeHasSeries'] else '❌'}, 维度补缺={'✅' if result['scrapeHasSupplement'] else '❌'}")

    print(f"刮削模式提示: {result['modeHint']}")
    if 'AI 搜索增强' not in result['modeHint']:
        print("FAIL: Expected 'AI 搜索增强' in mode hint")
        passed = False

    # Test simulator
    page.evaluate("setView('config-simulator', 'config')")
    page.wait_for_timeout(500)

    page.fill("#confidence-sim-filename", "Inception.2010.1080p.BluRay.x264-TRAE.mkv")
    page.click("#btn-confidence-simulate")

    try:
        page.wait_for_function(
            "!document.getElementById('confidence-sim-result').textContent.includes('正在生成')",
            timeout=120000
        )
    except Exception as e:
        print(f"TIMEOUT: {e}")
        page.screenshot(path="/tmp/scrape_preview_timeout.png", full_page=True)
        browser.close()
        exit(1)

    page.wait_for_timeout(1000)

    sim_result = page.evaluate("""() => {
        const el = document.getElementById('confidence-sim-result');
        const text = el.textContent;
        const cards = el.querySelectorAll('.sim-mode-card');
        return {
            cardCount: cards.length,
            hasNetworkError: text.includes('网络请求失败'),
            hasTimeline: text.includes('最终入库判断'),
            providerDesc: cards[0] ? cards[0].querySelector('.sim-mode-desc').textContent.trim() : '?'
        };
    }""")

    print(f"\n=== Simulator ===")
    print(f"Cards: {sim_result['cardCount']}")
    print(f"Network error: {'FAIL' if sim_result['hasNetworkError'] else 'PASS'}")
    print(f"Provider desc: {sim_result['providerDesc']}")
    print(f"Timeline: {'PASS' if sim_result['hasTimeline'] else 'FAIL'}")

    if sim_result['cardCount'] != 2:
        passed = False
    if sim_result['hasNetworkError']:
        passed = False

    print("\n--- Console ---")
    for e in errors:
        print(e)

    page.screenshot(path="/tmp/scrape_preview_result.png", full_page=True)
    browser.close()

    if passed:
        print("\nALL TESTS PASSED")
    else:
        print("\nSOME TESTS FAILED")
        exit(1)
