"""Real Chromium checks for the delayed same-series manual scrape interaction."""

from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DETAIL_JS = ROOT / "media_importer/webui/js/cinema-task-detail-open.js"
PAGES_CSS = ROOT / "media_importer/webui/css/cinema-pages.css"


def _open_harness(page, *, apply_code: int = 200, apply_data=None) -> None:
    page.set_content(
        '<div id="scrape-search-overlay">'
        '<div id="scrape-search-detail"></div>'
        '<select id="scrape-search-language"><option value="zh-CN">中文</option></select>'
        "</div>"
    )
    page.add_style_tag(path=str(PAGES_CSS))
    page.evaluate(
        """({applyCode, applyData}) => {
          window.escapeHtml = (value) => String(value ?? "");
          window.showToast = () => {};
          window.openTaskDetailImpl = async () => {};
          window.loadTaskList = async () => {};
          window.loadDashboardOverview = async () => {};
          window.__finishApply = null;
          window.requestApi = async (_method, path) => {
            if (path.endsWith('/scrape-series-preview')) {
              return {code: 200, data: {tasks: [
                {task_id: 'e01', source_filename: '北海鲸梦.S01E01.mkv', season: 1, episode: 1,
                 is_anchor: true, stage: 'AWAIT_REVIEW', handling: 'queue_with_binding', selectable: true},
                {task_id: 'e05', source_filename: '北海鲸梦.S01E05.mkv', season: 1, episode: 5,
                 is_anchor: false, stage: 'QUEUED', handling: 'bind_queued', selectable: true},
                {task_id: 'e04', source_filename: '北海鲸梦.S01E04.mkv', season: 1, episode: 4,
                 is_anchor: false, stage: 'RUNNING', handling: 'processing_unchanged', selectable: false},
              ]}};
            }
            if (path.endsWith('/scrape-apply')) {
              return await new Promise((resolve) => {
                window.__finishApply = () => resolve({code: applyCode, message: 'done', data: applyData});
              });
            }
            throw new Error(`unexpected path: ${path}`);
          };
        }""",
        {"applyCode": apply_code, "applyData": apply_data},
    )
    page.add_script_tag(path=str(DETAIL_JS))
    page.evaluate(
        """() => renderScrapeCandidateDetail({
          id: '86941', title: '北海鲸梦', original_title: 'The North Water',
          year: 2021, media_type: 'tv', provider_type: 'tmdb', overview: ''
        }, 'e01')"""
    )


@pytest.mark.parametrize("viewport", [{"width": 1280, "height": 800}, {"width": 390, "height": 844}])
def test_delayed_series_apply_shows_spinner_and_locks_every_control(viewport):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport=viewport)
        _open_harness(page)

        page.get_by_role("button", name="使用这份资料").click()
        expect(page.locator(".series-batch-preview")).to_be_visible()
        page.get_by_role("button", name="应用所选 2 集").click()

        panel = page.locator(".series-batch-preview")
        expect(panel).to_have_attribute("aria-busy", "true")
        expect(panel.locator(".spinner")).to_be_visible()
        expect(panel.get_by_text("正在应用并提交 2 集...")).to_be_visible()
        assert panel.locator("button:not(:disabled), input:not(:disabled)").count() == 0

        page.evaluate("window.__finishApply()")
        expect(page.locator("#scrape-search-overlay")).to_have_count(0)
        browser.close()


def test_failed_series_apply_restores_candidate_action():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        _open_harness(page, apply_code=400)

        page.get_by_role("button", name="使用这份资料").click()
        page.get_by_role("button", name="应用所选 2 集").click()
        page.evaluate("window.__finishApply()")

        expect(page.get_by_role("button", name="使用这份资料")).to_be_enabled()
        expect(page.locator(".series-batch-preview")).to_have_count(0)
        browser.close()


# Requirement: REQ-20260905-231945
@pytest.mark.parametrize("width", [1280, 390])
def test_partial_series_apply_preserves_per_episode_results(width):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": 844})
        _open_harness(page, apply_data={
            "queued": [{"task_id": "e01"}],
            "failed": [{"task_id": "e05", "error": "state_changed"}],
            "processing_unchanged": [{"task_id": "e04", "reason": "processing_unchanged"}],
            "skipped": [{"task_id": "gone", "reason": "not_in_safe_series_batch"}],
        })
        page.get_by_role("button", name="使用这份资料").click()
        page.get_by_role("button", name="应用所选 2 集").click()
        page.evaluate("window.__finishApply()")
        panel = page.locator(".series-batch-result")
        expect(panel).to_be_visible()
        expect(panel).to_contain_text("北海鲸梦.S01E05.mkv")
        expect(panel).to_contain_text("任务状态已变化")
        expect(panel).to_contain_text("处理中，本次未改写")
        expect(panel).to_contain_text("gone")
        expect(panel.locator(".spinner")).to_have_count(0)
        expect(page.get_by_role("button", name="关闭并刷新任务")).to_be_enabled()
        page.get_by_role("button", name="关闭并刷新任务").click()
        expect(page.locator("#scrape-search-overlay")).to_have_count(0)
        browser.close()
