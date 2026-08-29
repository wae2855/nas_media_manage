from pathlib import Path

from media_importer.core.config_validator import validate_config
from media_importer.monitor.file_watcher import FileWatcher

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "media_importer/webui/index.html").read_text(encoding="utf-8")
APP_STATE = (ROOT / "media_importer/webui/js/cinema-app-state.js").read_text(encoding="utf-8")
CONFIG_AI = (ROOT / "media_importer/webui/js/cinema-config-ai.js").read_text(
    encoding="utf-8"
)
CONFIG_SAVE = (ROOT / "media_importer/webui/js/cinema-config-save.js").read_text(encoding="utf-8")
CONFIG_PAYLOADS = (
    ROOT / "media_importer/webui/js/cinema-config-payloads.js"
).read_text(encoding="utf-8")
RULES = (ROOT / "media_importer/webui/js/cinema-config-rules.js").read_text(encoding="utf-8")
REEL = (ROOT / "media_importer/webui/js/cinema-reel.js").read_text(encoding="utf-8")
DIRECTORY_LOADER = (
    ROOT / "media_importer/webui/js/cinema-directory-loader.js"
).read_text(encoding="utf-8")
ADVANCED_PAGES = (
    ROOT / "media_importer/webui/partials/advanced-pages.html"
).read_text(encoding="utf-8")


def test_source_cleaner_is_nested_under_selected_mode_and_complex_rules_use_modal():
    assert 'id="source-cleaner-mode-child"' in INDEX
    assert "placeSourceCleanerUnderModeChoice" in APP_STATE
    assert "openSourceCleanerRulesModal" in APP_STATE
    assert "openLlmConfigModal" in APP_STATE
    assert 'data-source-cleaner-rules' in INDEX
    assert 'data-source-llm-config' in INDEX


def test_clear_source_copy_hides_internal_source_unit_tuning_from_basic_page():
    assert "入库后清空来源" in INDEX
    assert "成功后回收整组来源" not in INDEX
    assert 'id="cfg-source-unit-settle"' not in INDEX
    assert 'id="cfg-source-unit-incomplete-patterns"' not in INDEX


def test_rule_editor_cannot_be_dismissed_by_clicking_backdrop():
    rule_editor = RULES[RULES.index("const overlay = showAppModal") :]
    assert "dismissOnBackdrop: false" in rule_editor


def test_automation_poll_interval_is_editable_and_saved():
    assert 'id="cfg-auto-watcher-poll-interval"' in INDEX
    for seconds in (30, 60, 120, 300, 600):
        assert f'<option value="{seconds}">' in INDEX
    assert 'document.getElementById("cfg-auto-watcher-poll-interval")' in CONFIG_SAVE
    assert "poll_interval: pollInterval" in CONFIG_SAVE


def test_poll_interval_validation_and_runtime_clamp(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    invalid = validate_config(
        {
            "source_dir": str(source),
            "file_watcher": {"enabled": False, "poll_interval": 5},
        }
    )
    assert any(
        item["item"] == "file_watcher.poll_interval" and item["status"] == "error"
        for item in invalid["details"]
    )

    watcher = FileWatcher(
        {"source_dir": str(source), "file_watcher": {"enabled": True, "poll_interval": 5}}
    )
    assert watcher.poll_interval == 10
    malformed = FileWatcher(
        {
            "source_dir": str(source),
            "file_watcher": {"enabled": True, "poll_interval": "invalid"},
        }
    )
    assert malformed.poll_interval == 60


def test_advanced_settings_are_a_reel_stage_without_legacy_home_navigation():
    assert 'data-config-stage="advanced"' in INDEX
    assert 'data-config-panel="advanced"' in INDEX
    assert 'data-view-target="advanced-config"' not in INDEX
    assert "mountAdvancedSettingsInTrack();" in REEL
    assert "attachAdvancedFilmNavigation();" not in REEL
    for view in ("naming-config", "dimensions-config", "security-config", "system-settings"):
        assert f'view: "{view}"' in APP_STATE


def test_watcher_configuration_has_one_owner_on_automation_stage():
    assert "cfg-file_watcher-enabled-inline" not in ADVANCED_PAGES
    assert "cfg-file_watcher-poll_interval-inline" not in ADVANCED_PAGES
    system_payload = CONFIG_PAYLOADS[
        CONFIG_PAYLOADS.index("function buildAdvancedSystemPayload") :
    ]
    assert "file_watcher:" not in system_payload


def test_llm_card_stays_in_modal_during_configuration_reload():
    llm_placement = APP_STATE[
        APP_STATE.index("function placeLlmSettingsUnderSourcePolicy") :
        APP_STATE.index("function placeSourceCleanerUnderModeChoice")
    ]
    assert 'card?.closest(".cinema-modal-overlay")' in llm_placement


def test_llm_connectivity_result_is_visible_inside_configuration_modal():
    assert 'id="llm-test-result"' in INDEX
    assert 'role="status"' in INDEX
    assert 'showFeedback("testing"' in CONFIG_AI
    assert 'showFeedback("error"' in CONFIG_AI
    assert 'showFeedback(success ? "success" : "error"' in CONFIG_AI
    assert 'triggerEl.textContent = "正在测试..."' in CONFIG_AI


def test_cleaner_merge_strategy_explains_plain_language_before_set_terms():
    assert "双方都判定为垃圾才处理（交集，推荐）" in INDEX
    assert "任意一方判定为垃圾就处理（并集）" in INDEX
    assert "只要有一方认为文件应该保留，就不会处理" in INDEX


def test_automation_copy_describes_background_behavior_and_current_state():
    assert "后台自动整理" in INDEX
    assert "关闭后仍可手动扫描和处理" in INDEX
    assert 'id="cfg-auto-watcher-label"' in INDEX
    assert "后台自动整理已开启" in APP_STATE
    assert "后台自动整理已关闭" in APP_STATE


def test_startup_readiness_status_codes_are_presented_in_chinese():
    for label in ("正常", "无需检查", "需要留意", "需要处理", "检查失败"):
        assert f'label: "{label}"' in DIRECTORY_LOADER
    readiness_renderer = DIRECTORY_LOADER[
        DIRECTORY_LOADER.index("function renderStartupReadiness") :
        DIRECTORY_LOADER.index("async function runStartupReadiness")
    ]
    assert "item.status ||" not in readiness_renderer.split("<span>", 1)[-1]


def test_simulator_is_a_library_setup_tool_without_legacy_advanced_route():
    simulator = ADVANCED_PAGES[
        ADVANCED_PAGES.index('data-view="config-simulator"') :
        ADVANCED_PAGES.index('data-view="metadata-config"')
    ]
    assert "模拟识别与分类" in simulator
    assert "片库搭建验证" in simulator
    assert 'data-view-target="config"' in simulator
    assert "高级配置" not in simulator


def test_startup_readiness_request_failure_is_rendered_inside_final_stage():
    assert "function renderStartupReadinessFailure" in DIRECTORY_LOADER
    assert "开场检查未完成" in DIRECTORY_LOADER
    assert "data-startup-readiness>重新检查" in DIRECTORY_LOADER
