from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DETAIL_JS = ROOT / "media_importer/webui/js/cinema-task-detail-open.js"
TASK_DETAIL_JS = ROOT / "media_importer/webui/js/cinema-task-detail.js"
PAGES_CSS = ROOT / "media_importer/webui/css/cinema-pages.css"


def test_manual_scrape_offers_type_language_year_and_twenty_results():
    script = DETAIL_JS.read_text(encoding="utf-8")

    assert 'id="scrape-search-media-type"' in script
    assert 'id="scrape-search-language"' in script
    assert 'id="scrape-search-year"' in script
    assert "搜索前 20 条" in script
    assert "limit: 20" in script


def test_candidate_application_refreshes_details_without_auto_import():
    script = DETAIL_JS.read_text(encoding="utf-8")
    candidate_block = script.split("function renderScrapeCandidateDetail", 1)[1]

    assert "/scrape-apply`" in candidate_block
    assert "使用这份资料" in candidate_block
    assert "作品资料已更新，请确认入库预览" in candidate_block
    assert "/confirm`" not in candidate_block
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
