from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# Requirement: REQ-20260904-122646
def test_task_concurrency_control_has_safe_frontend_limit():
    html = (ROOT / "media_importer/webui/partials/advanced-pages.html").read_text()
    payloads = (ROOT / "media_importer/webui/js/cinema-config-payloads.js").read_text()
    loader = (ROOT / "media_importer/webui/js/cinema-directory-loader.js").read_text()

    assert 'id="cfg-task_queue-max_concurrent-inline" min="1" max="2" step="1"' in html
    assert "普通 NAS 推荐 1" in html
    assert "Math.min(2, Math.max(1, rawTaskConcurrency))" in payloads
    assert "taskConcurrencyInput.value = String(maxConcurrent)" in payloads
    assert "Math.min(" in loader and "max_concurrent" in loader
