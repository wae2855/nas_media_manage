from pathlib import Path

from media_importer.core.config_view import ConfigView
from media_importer.features.configuration.application_service import build_section_config_update

ROOT = Path(__file__).resolve().parents[1]
WEBUI = ROOT / "media_importer" / "webui"


def _read(relative):
    return (WEBUI / relative).read_text(encoding="utf-8")


def test_legacy_duplicate_config_is_runtime_normalized_to_confirm():
    view = ConfigView.from_dict({
        "duplicate_handling": {"enabled": False, "strategy": "quality"},
    })

    assert view.dedup.enabled is True
    assert view.dedup.strategy == "confirm"


def test_import_options_save_cannot_restore_automatic_replacement():
    payload = build_section_config_update(
        "import_options",
        {"duplicate_handling": {"enabled": False, "strategy": "replace"}},
        {},
    )

    assert payload["duplicate_handling"] == {
        "enabled": True,
        "strategy": "confirm",
    }


def test_task_detail_has_three_explicit_conflict_actions_and_no_backdrop_dismiss():
    source = _read("js/cinema-task-detail-open.js")

    assert "片库现有文件未发生任何改动" in source
    assert "保留片库，也保留新资源" in source
    assert "保留片库，回收新资源" in source
    assert "两个都保留" in source
    assert "替换片库文件" in source
    assert 'conflict_action: conflictAction' in source
    assert "dismissOnBackdrop: false" in source


def test_stale_conflict_response_reopens_detail_instead_of_claiming_success():
    source = _read("js/cinema-task-detail-open.js")

    assert "result.data?.requires_conflict_review" in source
    assert "片库文件已发生变化，请重新查看后选择" in source
    assert "await openTaskDetailImpl(taskIdForClosure, true)" in source


def test_conflicts_are_excluded_from_batch_confirm():
    source = _read("js/cinema-task-batch.js")

    assert "!targetLibraryConflictOf(task)" in source
    assert "片库冲突必须打开任务逐项处理，不能批量确认" in source


def test_conflict_comparison_collapses_to_one_column_on_mobile():
    css = _read("css/cinema-pages.css")

    assert ".target-conflict-compare" in css
    assert ".target-conflict-actions" in css
    assert "grid-template-columns: 1fr" in css


def test_storage_setup_does_not_mix_legacy_rule_migration_copy_into_directory_flow():
    loader = _read("js/cinema-directory-loader.js")
    picker = _read("js/cinema-fnos-directories.js")

    assert "升级、保留数据后重装，或中途更换片库路径" not in loader
    assert "旧规则待设置" not in loader
    assert "下一步再为每条规则人工选择片库" not in picker
    assert "暂存并继续选择" not in picker
    assert "添加并保存" in picker
