from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# Requirement: REQ-20260901-010051
def test_task_progress_ui_has_stage_mapping_and_truthful_byte_bar():
    utils = (ROOT / "media_importer/webui/js/cinema-task-utils.js").read_text(
        encoding="utf-8"
    )

    assert 'import_verify_source: ["校验待入库文件"' in utils
    assert 'import_transfer: ["写入目标片库"' in utils
    assert 'import_verify_target: ["校验片库新文件"' in utils
    assert 'source_cleanup_transfer: ["回收来源文件"' in utils
    assert "bytes_copied" in utils and "total_bytes" in utils
    assert "bytePhase" in utils
    assert "流程第 ${progress.flowIndex} / 4 段" in utils


# Requirement: REQ-20260901-010051
def test_task_progress_polling_pauses_for_modal_selection_and_hidden_page():
    task_list = (ROOT / "media_importer/webui/js/cinema-task-list.js").read_text(
        encoding="utf-8"
    )

    assert "document.hidden" in task_list
    assert 'document.querySelector(".cinema-modal-overlay")' in task_list
    assert "selectedTaskIds.size > 0" in task_list
    assert "loadTaskList(false, { silent: true })" in task_list
    assert "2500" in task_list


# Requirement: REQ-20260901-010051
def test_silent_task_polling_reconciles_cards_without_rebuilding_the_list():
    task_list = (ROOT / "media_importer/webui/js/cinema-task-list.js").read_text(
        encoding="utf-8"
    )

    assert "patchTaskListCards" in task_list
    assert "data-task-render-key" in task_list
    assert "renderTaskList({ incremental: silent })" in task_list
    assert "listVisibleTaskPages" in task_list
    assert "host.innerHTML = cardsHtml + loadMoreHtml" in task_list


# Requirement: REQ-20260901-010051
def test_task_progress_mobile_layout_has_no_horizontal_flow_grid():
    styles = (ROOT / "media_importer/webui/css/cinema-pages.css").read_text(
        encoding="utf-8"
    )

    assert ".task-progress-flow" in styles
    assert "grid-template-columns: 1fr;" in styles
    assert ".task-live-progress-head" in styles
