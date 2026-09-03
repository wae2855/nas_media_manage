from pathlib import Path

WEBUI = Path(__file__).resolve().parents[1] / "media_importer" / "webui"


def test_rules_page_exposes_multiple_library_root_manager():
    html = (WEBUI / "index.html").read_text(encoding="utf-8")
    assert 'id="library-roots-list"' in html
    assert 'data-library-root-action="add"' in html
    assert 'id="cfg-fallback-root-inline"' in html
    assert 'id="cfg-library-root-inline"' not in html


def test_rule_editor_binds_each_rule_to_a_library_root():
    source = (WEBUI / "js" / "cinema-config-rules.js").read_text(encoding="utf-8")
    assert 'id="rule-library-root-input"' in source
    assert "library_root_id: libraryRootId" in source


def test_directory_picker_enforces_fnos_acl_and_keeps_non_fnos_fallback():
    source = (WEBUI / "js" / "cinema-fnos-directories.js").read_text(encoding="utf-8")
    callback = (WEBUI / "fnos-auth-callback.html").read_text(encoding="utf-8")
    html = (WEBUI / "index.html").read_text(encoding="utf-8")
    assert "/config/fnos-folders" in source
    assert "/app-auth/pick-shared-file" in source
    assert "/app-auth/authorize-shared-file" in source
    assert "FNOS_AUTH_PENDING_KEY" in source
    assert 'event.origin !== location.origin' in source
    assert "本地开发可手动填写" in source
    assert 'id="fnos-directory-authorization"' not in html
    assert 'id="storage-readiness-grid"' in html
    assert 'type: "nmmi:fnos-auth-result"' in callback
    assert 'localStorage.setItem("nmmi-fnos-auth-result"' in callback
    assert "FNOS_AUTH_RESULT_KEY" in source
    assert 'window.addEventListener("storage"' in source
    assert 'window.addEventListener("focus"' in source
    assert "localOnly" in source


def test_storage_ledger_supports_dynamic_unbounded_library_rows():
    loader = (WEBUI / "js" / "cinema-directory-loader.js").read_text(encoding="utf-8")
    save = (WEBUI / "js" / "cinema-config-save.js").read_text(encoding="utf-8")
    source = (WEBUI / "js" / "cinema-fnos-directories.js").read_text(encoding="utf-8")
    assert "添加第一个目标片库" in loader
    assert "数量不设上限" in loader
    assert 'String(item.id || "").startsWith("target:")' in loader
    assert "saveLibraryRootsConfig" in save
    assert "_migrate_legacy_library_rules" not in save
    assert "暂存并继续选择" not in source
    assert "片库已选好，去设置规则" not in source
    assert 'data-library-assignment-action="open-rules"' not in loader


def test_rules_never_fall_back_to_default_library_assignment():
    rules = (WEBUI / "js" / "cinema-config-rules.js").read_text(encoding="utf-8")
    save = (WEBUI / "js" / "cinema-config-save.js").read_text(encoding="utf-8")
    payloads = (WEBUI / "js" / "cinema-config-payloads.js").read_text(encoding="utf-8")
    assert "rule.library_root_id || defaultLibraryRootId()" not in rules
    assert "rule.library_root_id || defaultLibraryRootId()" not in save
    assert 'fallback_library_root_id:\n      document.getElementById("cfg-fallback-root-inline")?.value || ""' in payloads


def test_storage_check_always_keeps_the_normal_add_library_entry():
    loader = (WEBUI / "js" / "cinema-directory-loader.js").read_text(encoding="utf-8")
    assert "_library_migration_error" not in loader
    assert 'class="storage-add-library"' in loader
    assert "旧规则待设置" not in loader


def test_storage_rows_group_status_with_path_details():
    loader = (WEBUI / "js" / "cinema-directory-loader.js").read_text(encoding="utf-8")
    styles = (WEBUI / "css" / "cinema-config.css").read_text(encoding="utf-8")
    assert 'class="storage-card-detail"' in loader
    assert "grid-template-columns: 220px minmax(260px, 1fr) minmax(230px, auto);" in styles
    assert "grid-template-columns: 54px minmax(0, 1fr);" in styles
    assert ".storage-card-detail strong" in styles


def test_storage_check_is_the_only_directory_editing_surface():
    index = (WEBUI / "index.html").read_text(encoding="utf-8")
    advanced = (WEBUI / "partials" / "advanced-pages.html").read_text(encoding="utf-8")
    loader = (WEBUI / "js" / "cinema-directory-loader.js").read_text(encoding="utf-8")
    payloads = (WEBUI / "js" / "cinema-config-payloads.js").read_text(encoding="utf-8")
    directories = (WEBUI / "js" / "cinema-fnos-directories.js").read_text(encoding="utf-8")

    assert 'id="cfg-source-inline"' not in index
    assert 'id="cfg-log_dir-inline"' not in advanced
    assert 'id="cfg-resource_dir-inline"' not in advanced
    assert "所有目录统一在【存储检查】" in index
    assert 'if (!String(config?.source_dir || "").trim()) return "storage";' in loader
    assert '["source", "recycle", "log", "resource"]' in loader
    assert 'source_dir: normalizePathValue(' not in payloads
    assert 'log_dir: normalizePathValue(' not in payloads
    assert "saveStorageDirectoryRole" in directories
    assert 'temp: { title: "选择本地中转目录"' not in directories
