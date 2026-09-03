from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def test_task_actions_separate_ending_source_handling_and_record_deletion():
    utils = _read("media_importer/webui/js/cinema-task-utils.js")
    actions = _read("media_importer/webui/js/cinema-task-batch.js")

    assert 'key: "end-task", label: "停止任务"' in utils
    assert 'key: "end-task", label: "不再处理"' in utils
    assert 'key: "delete-record", label: "删除记录"' in utils
    assert "来源文件和目标片库文件都不会改动" in actions
    assert "/dispose`" in actions


def test_end_dialog_explains_target_protection_and_source_choices():
    actions = _read("media_importer/webui/js/cinema-task-batch.js")

    assert "目标片库受保护" in actions
    assert "保留新资源" in actions
    assert "移入本地回收区" in actions
    assert "永久删除这次新资源" in actions
    assert "dismissOnBackdrop: false" in actions


def test_duplicate_conflict_offers_keep_existing_with_source_disposition():
    detail = _read("media_importer/webui/js/cinema-task-detail-open.js")

    assert "保留片库，也保留新资源" in detail
    assert "保留片库，回收新资源" in detail
    assert "保留片库，删除新资源" in detail
    assert "source_disposition: sourceDisposition" in detail
    assert "保留现状，不再整理" in detail


def test_progress_language_describes_decision_before_large_transfer():
    utils = _read("media_importer/webui/js/cinema-task-utils.js")

    assert "识别、规则和重名检查均已完成，开始安全写入" in utils
    assert "正在把来源文件写入目标片库的任务暂存" in utils
    assert "流程第 ${progress.flowIndex} / 4 段" in utils
