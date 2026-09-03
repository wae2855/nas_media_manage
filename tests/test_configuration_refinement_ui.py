from pathlib import Path

from media_importer.core.config_validator import validate_config
from media_importer.monitor.file_watcher import FileWatcher

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "media_importer/webui/index.html").read_text(encoding="utf-8")
APP_STATE = (ROOT / "media_importer/webui/js/cinema-app-state.js").read_text(encoding="utf-8")
APP_EVENTS = (ROOT / "media_importer/webui/js/cinema-app-events.js").read_text(encoding="utf-8")
CONFIG_AI = (ROOT / "media_importer/webui/js/cinema-config-ai.js").read_text(
    encoding="utf-8"
)
CONFIG_SAVE = (ROOT / "media_importer/webui/js/cinema-config-save.js").read_text(encoding="utf-8")
CONFIG_PAYLOADS = (
    ROOT / "media_importer/webui/js/cinema-config-payloads.js"
).read_text(encoding="utf-8")
RULES = (ROOT / "media_importer/webui/js/cinema-config-rules.js").read_text(encoding="utf-8")
FNOS_DIRECTORIES = (
    ROOT / "media_importer/webui/js/cinema-fnos-directories.js"
).read_text(encoding="utf-8")
REEL = (ROOT / "media_importer/webui/js/cinema-reel.js").read_text(encoding="utf-8")
DIRECTORY_LOADER = (
    ROOT / "media_importer/webui/js/cinema-directory-loader.js"
).read_text(encoding="utf-8")
ADVANCED_PAGES = (
    ROOT / "media_importer/webui/partials/advanced-pages.html"
).read_text(encoding="utf-8")
CSS_PAGES = (ROOT / "media_importer/webui/css/cinema-pages.css").read_text(
    encoding="utf-8"
)
CSS_CONFIG = (ROOT / "media_importer/webui/css/cinema-config.css").read_text(
    encoding="utf-8"
)


def test_source_cleaner_is_nested_under_selected_mode_and_complex_rules_use_modal():
    assert 'id="source-cleaner-mode-child"' in INDEX
    assert "placeSourceCleanerUnderModeChoice" in APP_STATE
    assert "openSourceCleanerRulesModal" in APP_STATE
    assert "openLlmConfigModal" in APP_STATE
    assert 'data-source-cleaner-rules' in INDEX
    assert 'data-source-llm-config' in INDEX


# Requirement: REQ-20260901-020743 / ADR-0019
def test_source_disposal_is_a_nested_mutually_exclusive_choice_with_danger_ack():
    assert 'id="source-disposal-panel"' in INDEX
    assert 'name="cfg-source-disposal" value="local_recycle"' in INDEX
    assert 'name="cfg-source-disposal" value="permanent_delete"' in INDEX
    assert "移入本地回收区（推荐）" in INDEX
    assert "永久删除来源" in INDEX
    assert "toggleSourceDisposalUi" in APP_STATE
    assert "confirmPermanentSourceDeletion" in CONFIG_SAVE
    assert 'id="confirm-source-permanent-delete"' in CONFIG_SAVE
    assert "_confirm_source_permanent_delete" in CONFIG_SAVE
    assert "disposal_mode: disposalMode" in CONFIG_PAYLOADS
    assert "sourcePolicy.disposal_mode || \"local_recycle\"" in DIRECTORY_LOADER


def test_clear_source_copy_hides_internal_source_unit_tuning_from_basic_page():
    assert "入库后清空来源" in INDEX
    assert "成功后回收整组来源" not in INDEX
    assert 'id="cfg-source-unit-settle"' not in INDEX
    assert 'id="cfg-source-unit-incomplete-patterns"' not in INDEX


def test_rule_editor_cannot_be_dismissed_by_clicking_backdrop():
    rule_editor = RULES[RULES.index("const overlay = showAppModal") :]
    assert "dismissOnBackdrop: false" in rule_editor


# Requirement: REQ-20260831-224737
def test_rule_editor_exposes_supported_clickable_path_template_tokens():
    for token in (
        "{title_cn}",
        "{title_en}",
        "{year}",
        "{media_type}",
        "{season}",
        "{episode}",
    ):
        assert token in RULES
    assert "{dimension.${dim.name}}" in RULES
    assert '<details class="rule-template-assistant"' in RULES
    assert '<details class="rule-template-assistant" open' not in RULES
    assert "插入模板变量" in RULES
    assert 'data-rule-template-token="${escapeHtml(item.token)}"' in RULES
    assert "input.selectionStart" in RULES
    assert "input.setSelectionRange(caret, caret)" in RULES


def test_rule_template_has_nested_help_dialog_without_closing_editor():
    assert 'data-rule-template-help' in RULES
    assert 'layer.className = "rule-template-help-overlay"' in RULES
    assert "入库路径模板怎么填写" in RULES
    assert "不要以 / 开头" in RULES
    assert "不能包含 .." in RULES
    assert "影片不能直接放在片库根" in RULES
    assert "movies/{title_cn}" in RULES
    help_source = RULES[RULES.index("function showRuleTemplateHelp") : RULES.index("function openRuleEditor")]
    assert "showAppModal" not in help_source
    assert "removeAppModal" not in help_source


# Requirement: REQ-20260831-224737
def test_fnos_authorization_completion_has_bounded_poll_and_full_refresh():
    assert "FNOS_AUTH_REFRESH_DELAYS_MS" in FNOS_DIRECTORIES
    assert "setFnosAuthorizationRefreshState(true)" in FNOS_DIRECTORIES
    assert "waitForFnosAuthorizedPaths(expectedPaths)" in FNOS_DIRECTORIES
    assert "await loadDirectoryConfig()" in FNOS_DIRECTORIES
    assert "授权状态已更新" in FNOS_DIRECTORIES
    assert "fnOS 授权同步较慢" in FNOS_DIRECTORIES


def test_automation_poll_interval_is_editable_and_saved():
    assert 'id="cfg-auto-watcher-poll-interval"' in INDEX
    for seconds in (30, 60, 120, 300, 600):
        assert f'<option value="{seconds}"' in INDEX
    assert '<option value="300" selected>5 分钟（默认）</option>' in INDEX
    assert "watcherCfg.poll_interval || 300" in DIRECTORY_LOADER
    assert "configured.poll_interval || 300" in CONFIG_SAVE
    assert 'document.getElementById("cfg-auto-watcher-poll-interval")' in CONFIG_SAVE
    assert "poll_interval: pollInterval" in CONFIG_SAVE


# Requirement: REQ-20260901-001019-2
def test_automation_switch_applies_immediately_and_reads_backend_runtime_status():
    assert "更改后立即生效" in INDEX
    assert 'data-config-save="automation"' not in INDEX
    assert 'id="automation-runtime-status"' in INDEX
    assert "关闭桌面窗口或手机页面不会停止整理" in INDEX
    assert 'requestApi("GET", "/watcher/status")' in CONFIG_SAVE
    assert "fnOS 后台服务正在自动整理" in CONFIG_SAVE
    assert "设置已保存，但后台暂未运行" in CONFIG_SAVE
    assert "runtime.reason" in CONFIG_SAVE
    assert "saveAutomationConfig();" in APP_EVENTS
    assert "automationInterval.addEventListener" in APP_EVENTS
    assert "loadWatcherRuntimeStatus();" in DIRECTORY_LOADER


# Requirement: REQ-20260831-235616
def test_tmdb_card_explains_exact_credential_rate_and_connectivity_contract():
    assert "API Key（v3 auth）" in RULES
    assert "不要填写 API Read Access Token" in RULES
    assert "没有固定的每日调用次数" in RULES
    assert "约 40 次/秒" in RULES
    assert "可能需要代理" in RULES
    assert "https://www.themoviedb.org/settings/api" in RULES
    assert "https://api.themoviedb.org/3/configuration" in RULES
    assert "This product uses the TMDB API" in RULES


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
    assert malformed.poll_interval == 300
    assert FileWatcher({"source_dir": str(source)}).poll_interval == 300


def test_advanced_settings_are_a_reel_stage_without_legacy_home_navigation():
    assert 'data-config-stage="advanced"' in INDEX
    assert 'data-config-panel="advanced"' in INDEX
    assert 'data-view-target="advanced-config"' not in INDEX
    assert "mountAdvancedSettingsInTrack();" in REEL
    assert "attachAdvancedFilmNavigation();" not in REEL
    for view in ("naming-config", "dimensions-config", "system-settings"):
        assert f'view: "{view}"' in APP_STATE
    assert 'view: "security-config"' not in APP_STATE
    assert 'data-view="security-config"' not in ADVANCED_PAGES
    assert "cfg-server_api_key-inline" not in ADVANCED_PAGES
    assert "cfg-server_port-inline" not in ADVANCED_PAGES
    assert "buildServerConfigPayload" not in CONFIG_PAYLOADS
    assert "saveSecurityConfig" not in CONFIG_SAVE
    assert "cfg-server_api_key-inline" not in DIRECTORY_LOADER


def test_config_reel_uses_stable_numeric_stage_image_names():
    for index in range(1, 9):
        assert f'assets/config-stage/{index:02d}.jpeg' in INDEX

    for legacy_name in ("start", "source", "temp", "scrape", "rules", "ai", "recycle"):
        assert f'assets/config-stage/{legacy_name}.jpeg' not in INDEX


# Requirement: REQ-20260901-020743
def test_storage_stage_precedes_source_stage_in_reel_and_dom_order():
    storage_card = INDEX.index('data-config-stage="storage"')
    source_card = INDEX.index('data-config-stage="source"')
    assert storage_card < source_card
    assert 'data-config-stage="storage">\n                        <span class="config-stage-img"><img src="assets/config-stage/02.jpeg"' in INDEX
    assert 'data-config-stage="source">\n                        <span class="config-stage-img"><img src="assets/config-stage/03.jpeg"' in INDEX
    assert 'data-config-stage-jump="storage">先检查存储目录' in INDEX
    assert "syncConfigPanelDomOrder" in REEL
    assert '["start", "storage", "source", "scrape", "rules", "ai", "advanced", "recycle"]' in REEL


def test_selected_config_reel_frame_shows_the_image_at_full_brightness():
    assert ".config-stage-card:hover .config-stage-img img" in CSS_CONFIG
    assert "brightness(0.82)" in CSS_CONFIG
    active_rule = CSS_CONFIG[CSS_CONFIG.index(".config-stage-card.active .config-stage-img img") :]
    assert "filter: none;" in active_rule.split("}", 1)[0]


def test_recycle_and_config_heroes_share_the_task_background_image():
    task_image = 'url("../assets/config-stage/task.png")'
    assert CSS_PAGES.count(task_image) >= 3


def test_config_hero_camera_has_task_level_brightness_without_right_mask():
    config_hero = CSS_PAGES[
        CSS_PAGES.index('.page-view[data-view="config"] .page-hero {') :
        CSS_PAGES.index('.page-view[data-view="advanced-config"] .page-hero,')
    ]
    assert "--hero-poster-size: contain;" in config_hero
    assert "--hero-layer-opacity: 1.0;" in config_hero
    assert "rgba(18, 12, 5, 0) 68%" in config_hero
    assert "rgba(20,16,12,0.84)" not in config_hero


def test_recycle_hero_camera_has_task_level_brightness_without_right_mask():
    recycle_hero = CSS_PAGES[
        CSS_PAGES.index('.page-view[data-view="recycle"] .page-hero {') :
        CSS_PAGES.index('.page-view[data-view="dashboard"] .page-hero {')
    ]
    assert "--hero-poster-size: contain;" in recycle_hero
    assert "--hero-layer-opacity: 1.0;" in recycle_hero
    assert "rgba(18, 12, 5, 0) 68%" in recycle_hero
    assert "rgba(12,18,28,0.82)" not in recycle_hero


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
    assert "已设置为后台自动整理" in APP_STATE
    assert "已设置为不自动整理" in APP_STATE


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
    assert "配置检查未完成" in DIRECTORY_LOADER
    assert "data-startup-readiness>重新检查" in DIRECTORY_LOADER


# Requirement: REQ-20260831-214244
def test_final_stage_uses_plain_configuration_check_language_and_rule_navigation():
    assert INDEX.count("data-startup-readiness>配置检查</button>") == 2
    assert "运行开场检查" not in INDEX
    assert 'target === "rules"' in APP_EVENTS
    assert 'setConfigStage("rules")' in APP_EVENTS
    for phrase in ("等待配置检查", "配置检查通过", "配置检查发现阻塞项"):
        assert phrase in INDEX + DIRECTORY_LOADER


# Requirement: REQ-20260831-214244
def test_storage_check_does_not_render_rule_assignment_issues():
    storage_renderer = DIRECTORY_LOADER[
        DIRECTORY_LOADER.index("function renderStorageReadiness") :
        DIRECTORY_LOADER.index("function resetStartupReadinessView")
    ]
    for forbidden in (
        "_library_migration_error",
        "旧规则待设置",
        "renderLibraryRuleAssignmentIssues",
        "data-library-assignment-action",
    ):
        assert forbidden not in storage_renderer


# Requirement: REQ-20260830-180954
def test_first_open_guides_missing_required_directories_without_redirecting_ready_users():
    assert "function requiredDirectorySetupStage" in DIRECTORY_LOADER
    assert 'setView("config", "config")' in DIRECTORY_LOADER
    assert "setConfigStage(stage)" in DIRECTORY_LOADER
    assert "首次使用：请先完成目录选择" in DIRECTORY_LOADER
    assert "guideSetup: true" in REEL


def test_start_page_support_card_is_optional_and_has_stable_qr_asset_path():
    assert 'class="developer-support-card"' in INDEX
    assert "END CREDITS · 支持独立开发" in INDEX
    assert "问题反馈和建议不以打赏为前提" in INDEX
    assert 'src="assets/support/developer-reward-qr.png"' in INDEX
    assert 'src="assets/support/developer-wechat-qr.png"' in INDEX
    assert "<object" not in INDEX[INDEX.index('class="developer-support-card"') : INDEX.index('data-config-panel="source"')]
    assert "使用中遇到问题，或有功能建议，也欢迎加我微信交流" in INDEX
    assert "请开发者喝杯咖啡" in INDEX
    assert "使用交流与建议" in INDEX


def test_start_page_explains_the_four_step_media_journey():
    assert 'class="setup-process-timeline"' in INDEX
    assert 'aria-label="影音整理四步流程"' in INDEX
    assert INDEX.count('class="setup-process-step"') == 4
    for label in ("获取电影文件", "刮削电影资料", "分拣归类", "写入片库"):
        assert label in INDEX
    assert "按选择保留或处理来源文件" in INDEX
