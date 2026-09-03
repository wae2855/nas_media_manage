from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBUI = ROOT / "media_importer" / "webui"


def _read(relative_path: str) -> str:
    return (WEBUI / relative_path).read_text(encoding="utf-8")


def test_dashboard_uses_business_summary_instead_of_raw_logs():
    dashboard = _read("js/cinema-dashboard.js")

    assert 'requestApi("GET", "/dashboard/summary")' in dashboard
    assert 'requestApi("GET", "/logs' not in dashboard
    assert "running > 0" in dashboard
    assert "review > 0" in dashboard
    assert "progress: Number(data.running_progress || 0)" in dashboard
    assert "setDashboardQueueStrip" in dashboard


def test_dashboard_activity_and_recent_movies_are_bounded():
    app_state = _read("js/cinema-app-state.js")
    dashboard = _read("js/cinema-dashboard.js")
    reel = _read("js/cinema-reel.js")

    assert "items.slice(0, 5)" in app_state
    assert "setReelMovies(data.recent_movies || [])" in dashboard
    assert "}, 4500);" in reel
    assert "pointerdown" in reel
    assert "pointerup" in reel
    assert "prefers-reduced-motion" in reel
    assert "visibilitychange" in reel


def test_mobile_task_recycle_and_modal_contracts_are_present():
    pages = _read("css/cinema-pages.css")
    tasks = _read("js/cinema-task-list.js")
    recycle = _read("js/cinema-recycle.js")

    assert "@media (max-width: 768px)" in pages
    assert "@media (max-width: 600px)" in pages
    assert "height: calc(100dvh - 16px)" in pages
    assert "overflow-x: hidden" in pages
    assert ".cinema-modal-summary div" in pages
    assert "overflow-wrap: anywhere" in pages
    assert "table-layout: fixed" in pages
    assert "flex: 1 1 120px" in pages
    assert "min-height: 44px" in pages
    assert ".recycle-row" in pages
    assert ".task-card" in pages
    assert ".slice(0, 2)" in tasks
    assert "查看全部 ${entries.length} 项判断" in tasks
    assert "toolbar.hidden = count === 0" in recycle


def test_mobile_config_stage_and_simulator_guidance_are_present():
    index = _read("index.html")
    config_css = _read("css/cinema-config.css")
    pages_css = _read("css/cinema-pages.css")
    app_state = _read("js/cinema-app-state.js")

    assert 'id="config-stage-mobile-status"' in index
    assert "左右滑动胶卷查看更多步骤" in index
    assert "config-stage-mobile-status" in config_css
    assert ".match-preview-row" in pages_css
    assert "grid-template-columns: 1fr" in pages_css
    assert "${activeIndex + 1} / ${cards.length}" in app_state


# Requirement: REQ-20260901-001019-2
def test_runtime_version_is_visible_below_service_status():
    index = _read("index.html")
    layout_css = _read("css/cinema-layout.css")
    api_js = _read("js/api.js")

    assert 'class="runtime-meta"' in index
    assert 'id="runtime-version"' in index
    assert ".runtime-version" in layout_css
    assert "payload.data.version" in api_js
    assert 'runtimeVersion.textContent = "v"' in api_js
