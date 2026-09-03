from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def test_completed_fallback_is_labeled_as_organized_result_not_pending_confirmation():
    utils = _read("media_importer/webui/js/cinema-task-utils.js")
    listing = _read("media_importer/webui/js/cinema-task-list.js")

    assert 'task.organization_status === "FALLBACK_PENDING"' in utils
    assert 'text: "待整理"' in utils
    assert 'status === "PENDING"' in utils
    assert "已安全入库，等待整理" in listing
    assert 'key: "reorganize"' in utils


def test_fallback_confirmation_and_reorganization_are_explicit_separate_actions():
    detail = _read("media_importer/webui/js/cinema-task-detail-open.js")
    batch = _read("media_importer/webui/js/cinema-task-batch.js")

    assert "确认放入待整理区" in detail
    assert "fallback_acknowledged = true" in detail
    assert "/reorganize`" in detail
    assert "创建重新整理任务" in detail
    assert "当前仍未匹配正式入库规则" in detail
    assert 'action === "reorganize"' in batch
    assert "!task.used_fallback" in batch


def test_organization_panels_share_existing_responsive_modal_boundary():
    styles = _read("media_importer/webui/css/cinema-pages.css")

    assert ".task-organization-outcome" in styles
    assert ".task-organization-panel" in styles
    assert "minmax(0, 1fr)" in styles
    assert "@media (max-width: 600px)" in styles
