from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DETAIL_JS = ROOT / "media_importer/webui/js/cinema-task-detail-open.js"
TASK_DETAIL_JS = ROOT / "media_importer/webui/js/cinema-task-detail.js"
PAGES_CSS = ROOT / "media_importer/webui/css/cinema-pages.css"
BATCH_JS = ROOT / "media_importer/webui/js/cinema-task-batch.js"
INDEX_HTML = ROOT / "media_importer/webui/index.html"


def test_manual_scrape_offers_type_language_year_and_twenty_results():
    script = DETAIL_JS.read_text(encoding="utf-8")

    assert 'id="scrape-search-media-type"' in script
    assert 'id="scrape-search-language"' in script
    assert 'id="scrape-search-year"' in script
    assert "搜索前 20 条" in script
    assert "limit: 20" in script


def test_candidate_application_queues_processing_and_refreshes_details():
    script = DETAIL_JS.read_text(encoding="utf-8")
    candidate_block = script.split("function renderScrapeCandidateDetail", 1)[1]

    assert "/scrape-apply`" in candidate_block
    assert "使用这份资料" in candidate_block
    assert "已按人工选择加入处理队列" in candidate_block
    assert "正在提交处理" in candidate_block
    assert "await openTaskDetailImpl(taskId, true)" in candidate_block


def test_manual_scrape_modal_has_mobile_internal_layout_without_horizontal_pan():
    css = PAGES_CSS.read_text(encoding="utf-8")

    assert ".manual-scrape-toolbar" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert ".tmdb-preview-panels" in css
    assert "flex-direction: column;" in css
    assert ".tmdb-preview-left" in css
    assert "width: 100%;" in css


def test_task_detail_shows_planned_subtitle_name_and_unknown_language():
    script = TASK_DETAIL_JS.read_text(encoding="utf-8")

    assert "planned_filename" in script
    assert "计划文件名" in script
    assert 'und: "未识别"' in script


def test_tv_candidate_previews_deselectable_same_series_batch_before_apply():
    script = DETAIL_JS.read_text(encoding="utf-8")

    assert "/scrape-series-preview`" in script
    assert "发现同剧另外 " in script
    assert 'data-series-batch-task="' in script
    assert "仅应用当前集" in script
    assert "related_task_ids: relatedTaskIds" in script
    assert "进入处理队列" in script
    assert "处理中 · 本次不改写" in script


def test_series_batch_apply_has_visible_busy_state_and_interaction_lock():
    script = DETAIL_JS.read_text(encoding="utf-8")
    css = PAGES_CSS.read_text(encoding="utf-8")

    assert 'setAttribute("aria-busy", "true")' in script
    assert 'querySelectorAll("button, input")' in script
    assert "正在应用并提交 " in script
    assert '<span class="spinner"' in script
    assert '.series-batch-preview[aria-busy="true"]' in css


def test_batch_reidentify_includes_failed_and_await_review_only():
    script = BATCH_JS.read_text(encoding="utf-8")
    html = INDEX_HTML.read_text(encoding="utf-8")
    retry_block = script.split('if (action === "batch-retry")', 1)[1]

    assert "批量重新识别" in html
    assert 'taskStatusOf(t) === "FAILED"' in retry_block
    assert 'taskStageOf(t) === "AWAIT_REVIEW"' in retry_block
    assert "使用当前版本规则重新刮削" in retry_block
    assert "/retry`" in retry_block
