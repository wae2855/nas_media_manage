from __future__ import annotations

import argparse
import importlib.util
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fnos_config = _load("fnos_config", ROOT / "deploy" / "fnos_config.py")
validate_fpk = _load("validate_fpk", ROOT / "scripts" / "validate_fpk.py")


def _init_args(tmp_path: Path, **overrides) -> argparse.Namespace:
    values = {
        "config": str(tmp_path / "config.yaml"),
        "template": str(ROOT / "config.yaml.example"),
        "source_dir": "/vol1/网盘 下载",
        "library_root": "/vol2/影视",
        "recycle_dir": "/vol2/回收/影音整理",
        "log_dir": "/var/packages/nas-media-importer/var/logs",
        "resource_dir": "/var/packages/nas-media-importer/var/resources",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_initialize_creates_loadable_config_with_install_values(tmp_path: Path):
    args = _init_args(tmp_path)

    assert fnos_config.initialize(args) == "created"

    config_path = Path(args.config)
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert loaded["source_dir"] == args.source_dir
    assert loaded["library_root"] == args.library_root
    assert loaded["source_policy"]["recycle_dir"] == args.recycle_dir
    assert "temp_dir" not in loaded
    assert loaded["log_dir"] == args.log_dir
    assert loaded["resource_dir"] == args.resource_dir
    assert loaded["server"]["port"] == 14591
    assert loaded["server"]["api_key"] == ""
    assert loaded["file_watcher"]["poll_interval"] == 300
    assert config_path.stat().st_mode & 0o777 == 0o600


def test_initialize_can_defer_external_directories_to_first_web_start(tmp_path: Path):
    args = _init_args(tmp_path, source_dir="", library_root="", recycle_dir="")

    assert fnos_config.initialize(args) == "created"

    loaded = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    assert loaded["source_dir"] == ""
    assert loaded["library_root"] == ""
    assert loaded["library_roots"] == []
    assert loaded["default_library_root_id"] == ""
    assert loaded["fallback_library_root_id"] == ""
    assert all("library_root_id" not in rule for rule in loaded["path_rules"])
    assert loaded["source_policy"]["recycle_dir"] == ""
    assert "temp_dir" not in loaded
    assert loaded["resource_dir"] == args.resource_dir
    assert loaded["file_watcher"]["enabled"] is False


# Requirement: REQ-20260901-001019-2
def test_fnos_desktop_ui_is_only_a_proxy_to_the_persistent_backend_service():
    cmd_main = (ROOT / "deploy/nas-media-importer/cmd/main").read_text(encoding="utf-8")
    desktop_cgi = (ROOT / "deploy/nas-media-importer/app/ui/index.cgi").read_text(
        encoding="utf-8"
    )

    assert 'PID_FILE="${TRIM_PKGVAR}/app.pid"' in cmd_main
    assert 'serve --host 127.0.0.1 >> "${LOG_FILE}" 2>&1 &' in cmd_main
    assert 'TARGET_URL="http://${BACKEND_HOST}:${BACKEND_PORT}' in desktop_cgi
    assert "stop_process" not in desktop_cgi


def test_initialize_preserves_existing_user_config(tmp_path: Path):
    args = _init_args(tmp_path)
    assert fnos_config.initialize(args) == "created"
    path = Path(args.config)
    existing = path.read_text(encoding="utf-8")
    existing = existing.replace("/vol2/影视", "/vol3/我的片库")
    existing = existing.replace("poll_interval: 300", "poll_interval: 60")
    path.write_text(existing, encoding="utf-8")

    assert fnos_config.initialize(_init_args(tmp_path, library_root="/vol9/不要覆盖")) == "existing"
    assert "/vol3/我的片库" in path.read_text(encoding="utf-8")
    assert "/vol9/不要覆盖" not in path.read_text(encoding="utf-8")
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["file_watcher"]["poll_interval"] == 60


def test_update_port_changes_only_server_port(tmp_path: Path):
    args = _init_args(tmp_path)
    fnos_config.initialize(args)
    path = Path(args.config)
    before = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert fnos_config.update_port(argparse.Namespace(config=str(path), port="19855")) == "updated"

    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert after["server"]["port"] == 19855
    before["server"]["port"] = 19855
    assert after == before


# Requirement: REQ-20260830-180954
def test_migrate_managed_service_changes_only_fnos_owned_fields(tmp_path: Path):
    args = _init_args(tmp_path)
    fnos_config.initialize(args)
    path = Path(args.config)
    legacy = yaml.safe_load(path.read_text(encoding="utf-8"))
    legacy["server"]["port"] = 9855
    legacy["server"]["api_key"] = "legacy-secret"
    legacy["source_dir"] = "/vol9/保留来源"
    legacy["library_roots"] = [
        {"id": "disk-a", "name": "硬盘 A", "path": "/vol8/片库", "enabled": True}
    ]
    legacy["source_policy"]["recycle_dir"] = "/vol7/回收"
    path.write_text(yaml.safe_dump(legacy, allow_unicode=True, sort_keys=False), encoding="utf-8")
    before = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert fnos_config.migrate_managed_service(argparse.Namespace(config=str(path))) == "updated"

    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert after["server"]["port"] == 14591
    assert after["server"]["api_key"] == ""
    before["server"]["port"] = 14591
    before["server"]["api_key"] = ""
    assert after == before
    assert fnos_config.migrate_managed_service(argparse.Namespace(config=str(path))) == "unchanged"


def test_migrate_managed_service_adds_missing_resource_dir_without_overwriting_user_paths(tmp_path: Path):
    args = _init_args(tmp_path)
    fnos_config.initialize(args)
    path = Path(args.config)
    legacy = yaml.safe_load(path.read_text(encoding="utf-8"))
    legacy.pop("resource_dir")
    legacy["temp_dir"] = "/vol9/已取消的旧字段"
    path.write_text(yaml.safe_dump(legacy, allow_unicode=True, sort_keys=False), encoding="utf-8")

    managed_resource = "/var/packages/nas-media-importer/var/resources"
    result = fnos_config.migrate_managed_service(
        argparse.Namespace(config=str(path), resource_dir=managed_resource)
    )

    assert result == "updated"
    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert after["resource_dir"] == managed_resource
    assert "temp_dir" not in after


def test_reinstall_rebinds_only_old_package_private_defaults(tmp_path: Path):
    args = _init_args(tmp_path)
    fnos_config.initialize(args)
    path = Path(args.config)
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["temp_dir"] = "/vol2/@appdata/nas-media-importer/tmp"
    config["log_dir"] = "/vol2/@appdata/nas-media-importer/logs"
    config["resource_dir"] = "/vol2/@appdata/nas-media-importer/resources"
    config["source_dir"] = "/vol9/保留来源"
    config["source_policy"]["recycle_dir"] = "/vol8/保留回收"
    config["library_roots"] = [
        {"id": "movies", "name": "电影", "path": "/vol7/保留片库", "enabled": True}
    ]
    path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")

    result = fnos_config.migrate_managed_service(argparse.Namespace(
        config=str(path),
        log_dir="/vol3/@appdata/nas-media-importer/logs",
        resource_dir="/vol3/@appdata/nas-media-importer/resources",
    ))

    assert result == "updated"
    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "temp_dir" not in after
    assert after["log_dir"].startswith("/vol3/@appdata/")
    assert after["resource_dir"].startswith("/vol3/@appdata/")
    assert after["source_dir"] == "/vol9/保留来源"
    assert after["source_policy"]["recycle_dir"] == "/vol8/保留回收"
    assert after["library_roots"][0]["path"] == "/vol7/保留片库"


def test_reinstall_preserves_user_selected_service_directories(tmp_path: Path):
    args = _init_args(tmp_path)
    fnos_config.initialize(args)
    path = Path(args.config)
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config.update({
        "temp_dir": "/vol9/custom/removed-temp",
        "log_dir": "/vol9/custom/logs",
        "resource_dir": "/vol9/custom/resources",
    })
    path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")

    fnos_config.migrate_managed_service(argparse.Namespace(
        config=str(path),
        log_dir="/vol3/@appdata/nas-media-importer/logs",
        resource_dir="/vol3/@appdata/nas-media-importer/resources",
    ))

    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "temp_dir" not in after
    assert after["log_dir"] == "/vol9/custom/logs"
    assert after["resource_dir"] == "/vol9/custom/resources"


def test_reinstall_does_not_treat_old_private_path_in_comment_as_field_value(tmp_path: Path):
    args = _init_args(tmp_path)
    fnos_config.initialize(args)
    path = Path(args.config)
    content = path.read_text(encoding="utf-8")
    content = re.sub(
        r'(?m)^log_dir:.*$',
        'log_dir: "/vol9/custom/logs"  # 曾使用 /vol2/@appdata/nas-media-importer/logs',
        content,
    )
    path.write_text(content, encoding="utf-8")

    fnos_config.migrate_managed_service(argparse.Namespace(
        config=str(path),
        log_dir="/vol3/@appdata/nas-media-importer/logs",
    ))

    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert after["log_dir"] == "/vol9/custom/logs"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"source_dir": "relative/source"}, "绝对路径"),
    ],
)
def test_initialize_rejects_invalid_input_without_partial_config(tmp_path: Path, override: dict, message: str):
    args = _init_args(tmp_path, **override)
    with pytest.raises(fnos_config.ConfigError, match=message):
        fnos_config.initialize(args)
    assert not Path(args.config).exists()


def _add_bytes(archive: tarfile.TarFile, name: str, content: bytes, mode: int = 0o644) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mode = mode
    archive.addfile(info, io.BytesIO(content))


def _make_fpk(
    path: Path,
    forbidden_inner: str | None = None,
    wizard_field: str | None = None,
    unsafe_contract: bool = False,
    runtime_version: str = "0.3.0",
    stale_automation_contract: bool = False,
) -> None:
    inner_buffer = io.BytesIO()
    with tarfile.open(fileobj=inner_buffer, mode="w:gz") as inner:
        for name in validate_fpk.INNER_REQUIRED:
            mode = 0o755 if name in validate_fpk.INNER_EXECUTABLE_FILES else 0o644
            content = b"placeholder"
            if name == "server/VERSION":
                content = (runtime_version + "\n").encode()
            elif name == "server/config.yaml.example":
                content = (
                    b'duplicate_handling:\n  enabled: true\n  strategy: "quality"\n'
                    if unsafe_contract else
                    b'duplicate_handling:\n  enabled: true\n  strategy: "confirm"\n'
                )
            elif name.endswith("/services/dedup.py"):
                content = b"def _recycle_duplicate():\n    pass\n" if unsafe_contract else b"STRATEGY = 'confirm'\n"
            elif name.endswith("/services/file_operations.py"):
                content = (
                    b"safe_delete(dest_video, allowed_dirs)\nos.replace(staged_video, dest_video)\n"
                    if unsafe_contract else
                    b"SAFE_REPLACE = True\nincoming_paths = []\n"
                    b"if hash_file(existing_path) != expected_fingerprint:\n    pass\n"
                    b"if claimed_fingerprint != expected_fingerprint:\n    pass\n"
                )
            elif name.endswith("/tasks/delete_service.py"):
                content = b"DELETE = True\n" if unsafe_contract else b"def _task_references_library_file():\n    pass\n"
            elif name.endswith("/tasks/file_lifecycle_service.py"):
                content = b"RENAME = True\n" if unsafe_contract else b"path_in_library = True\n"
            elif name.endswith("/source_files/source_units.py"):
                content = (
                    b"SOURCE_UNIT = True\n"
                    if unsafe_contract else
                    b'canonical_path(unit["source_root"])\nimport_roots=configured_library_roots(config)\n'
                )
            elif name.endswith("/core/task_manager.py"):
                content = (
                    b"TASK_MANAGER = True\n"
                    if unsafe_contract else
                    b"protected_paths = []\npath_in_library = True\n"
                )
            elif name.endswith("/infrastructure/filesystem/safety.py"):
                content = (
                    b"def verified_copy():\n    os.replace(partial, dest)\n"
                    if unsafe_contract else
                    b"O_NOFOLLOW = True\ndef _publish_file_noreplace():\n    pass\n"
                    b"os.path.lexists(partial)\nprefix=\".write_test_\"\n"
                )
            elif name.endswith("/features/recycle/manager.py"):
                content = (
                    b'with open(meta_path, "w"):\n    pass\n'
                    if unsafe_contract else
                    b"O_NOFOLLOW = True\ndef _write_json_exclusive():\n    pass\n"
                )
            elif name.endswith("/features/recycle/browser.py"):
                content = (
                    b"os.rename(recycle_path, original_path)\n"
                    if unsafe_contract else
                    b"safe_move(recycle_path, original_path)\n"
                )
            elif name.endswith("/core/logger.py"):
                content = (
                    b"RotatingFileHandler = True\n"
                    if unsafe_contract else
                    b"O_NOFOLLOW = True\nSafeRotatingFileHandler = True\n"
                )
            elif name.endswith("/features/scraping/thumbnail_cache.py"):
                content = (
                    b"def prune_thumbnail_cache():\n    os.remove(path)\n"
                    if unsafe_contract else
                    b"def _safe_thumbnail_root(root):\n    return os.path.islink(root)\n"
                )
            elif name.endswith("/features/scraping/thumbnail_downloader.py"):
                content = (
                    b'with open(dest_path, "wb"):\n    pass\n'
                    if unsafe_contract else
                    b"O_EXCL = True\ndef _safe_thumbnail_dir():\n    pass\n"
                )
            elif name.endswith("/features/source_cleaning/application_service.py"):
                content = (
                    b"SOURCE_CLEANING = True\n"
                    if unsafe_contract else
                    b"inspect_storage_readiness = True\n"
                )
            elif name.endswith("/monitor/file_watcher.py"):
                content = (
                    b"WATCHER = True\n"
                    if unsafe_contract else
                    b"def _source_ready_for_scan():\n    pass\n"
                    b"def _processing_support_ready():\n    pass\n"
                )
            elif name.endswith("/configuration/storage_readiness.py"):
                content = (
                    "item.update(message='远程来源仅允许人工任务', automatic=False)\n"
                    if stale_automation_contract else
                    "item.update(message='网盘来源当前在线')\n"
                    "automatic_blocking = []\n"
                    'result = {"automatic_allowed": state == "READY" and not automatic_blocking}\n'
                ).encode()
            elif name.endswith("/configuration/application_service.py"):
                content = (
                    b"status = 'not_started'\n"
                    if stale_automation_contract else
                    b"configured_enabled = True\n"
                )
            elif name.endswith("/api/config_save.py"):
                content = (
                    b"SAVE = True\n"
                    if unsafe_contract else
                    b"captured_storage_identities = True\n"
                )
            _add_bytes(inner, name, content, mode)
        _add_bytes(inner, "server/wheelhouse/offline-placeholder-1-py3-none-any.whl", b"placeholder")
        if forbidden_inner:
            _add_bytes(inner, forbidden_inner, b"bad")

    manifest = b"appname = nas-media-importer\nversion = 0.3.0\nservice_port = 14591\ninstall_dep_apps = python312\nmicro_app = true\ndisable_authorization_path = false\n"
    with tarfile.open(path, mode="w:gz") as outer:
        for name in validate_fpk.OUTER_REQUIRED:
            if name == "manifest":
                content = manifest
            elif name == "app.tgz":
                content = inner_buffer.getvalue()
            elif name in validate_fpk.JSON_FILES:
                content = json.dumps(
                    ([{"items": [{"field": wizard_field}]}] if wizard_field and name == "wizard/install" else [])
                    if name.startswith("wizard/") else
                    {"api-scope": ["trim.file.sharedAccess"]} if name == "config/resource" else {}
                ).encode()
            else:
                content = (
                    b"#!/bin/bash\npython server.py serve --host 0.0.0.0\n"
                    if name == "cmd/main" and unsafe_contract else
                    b"#!/bin/bash\npython server.py serve --host 127.0.0.1\n"
                    if name == "cmd/main" else
                    b"#!/bin/bash\nexit 0\n"
                )
            _add_bytes(outer, name, content, 0o755 if name in validate_fpk.EXECUTABLE_FILES else 0o644)


def test_fpk_validator_accepts_current_contract(tmp_path: Path):
    path = tmp_path / "valid.fpk"
    _make_fpk(path)
    result = validate_fpk.validate(path, "0.3.0")
    assert result["version"] == "0.3.0"
    assert len(result["sha256"]) == 64


def test_fpk_validator_rejects_manifest_runtime_version_mismatch(tmp_path: Path):
    path = tmp_path / "version-mismatch.fpk"
    _make_fpk(path, runtime_version="0.3.1")

    with pytest.raises(validate_fpk.ValidationError, match="运行时版本与 manifest 不一致"):
        validate_fpk.validate(path, "0.3.0")


def test_fpk_validator_rejects_stale_remote_watcher_contract(tmp_path: Path):
    path = tmp_path / "stale-watcher.fpk"
    _make_fpk(path, stale_automation_contract=True)

    with pytest.raises(validate_fpk.ValidationError) as exc_info:
        validate_fpk.validate(path, "0.3.0")

    message = str(exc_info.value)
    assert "网盘来源自动扫描" in message
    assert "配置意图与真实运行状态" in message


def test_fpk_validator_rejects_generated_cache(tmp_path: Path):
    path = tmp_path / "invalid.fpk"
    _make_fpk(path, "server/media_importer/__pycache__/module.cpython-312.pyc")
    with pytest.raises(validate_fpk.ValidationError, match="禁止文件"):
        validate_fpk.validate(path, "0.3.0")


def test_fpk_validator_rejects_user_managed_server_fields_in_wizard(tmp_path: Path):
    path = tmp_path / "invalid-wizard.fpk"
    _make_fpk(path, wizard_field="wizard_api_key")
    with pytest.raises(validate_fpk.ValidationError, match="暴露托管字段"):
        validate_fpk.validate(path, "0.3.0")


# Requirement: REQ-20260831-004019
def test_fpk_validator_rejects_old_automatic_replace_and_public_listener(tmp_path: Path):
    path = tmp_path / "unsafe.fpk"
    _make_fpk(path, unsafe_contract=True)

    with pytest.raises(validate_fpk.ValidationError) as exc_info:
        validate_fpk.validate(path, "0.3.0")

    message = str(exc_info.value)
    assert "127.0.0.1" in message
    assert "confirm" in message
    assert "自动处置" in message
    assert "永久删除" in message
    assert "内容哈希" in message
    assert "任务删除" in message
    assert "任务重命名" in message
    assert "来源单元" in message
    assert "视频和字幕" in message
    assert "无条件覆盖" in message
    assert "长复制后" in message
    assert "原子门禁" in message
    assert "断点复制" in message
    assert "写权限" in message
    assert "回收记录" in message
    assert "回收恢复" in message
    assert "日志文件" in message
    assert "缩略图" in message
    assert "持久化挂载身份" in message
    assert "源清理" in message
    assert "自动扫描" in message


def test_build_script_declares_fnos_runtime_and_visible_failures():
    script = (ROOT / "deploy" / "build_fpk.sh").read_text(encoding="utf-8")
    cli = (ROOT / "media_importer" / "media_importer.py").read_text(encoding="utf-8")
    assert "install_dep_apps      = python312" in script
    assert 'VERSION_FILE="${PROJECT_DIR}/VERSION"' in script
    assert 'RELEASE_LEDGER_TOOL="${PROJECT_DIR}/scripts/release_ledger.py"' in script
    assert '"${RELEASE_LEDGER_TOOL}" preflight' in script
    assert '"${RELEASE_LEDGER_TOOL}" record-build' in script
    assert 'cp "${VERSION_FILE}" "${PKG_DIR}/app/server/VERSION"' in script
    assert "构建参数版本" in script
    assert "/var/apps/python312/target/bin/python3" in script
    assert 'VENV_DIR="${TRIM_PKGVAR}/venv"' in script
    assert "--no-index --find-links" in script
    assert "requirements-fnos.lock" in script
    assert "THIRD_PARTY_NOTICES.md" in script
    assert "import sys, yaml, guessit" in script
    assert "micro_app             = true" in script
    assert "disable_authorization_path = false" in script
    assert '"trim.file.sharedAccess"' in script
    assert "wizard_source_dir" not in script
    assert "wizard_api_key" not in script
    assert "wizard_port" not in script
    assert 'service_port          = 14591' in script
    command_main = script.split("create_cmd_main()", 1)[1].split("create_install_callback()", 1)[0]
    assert "serve --host 127.0.0.1" in command_main
    assert "serve --host 0.0.0.0" not in command_main
    assert 'get("port", 14591)' in cli
    assert '"field": "wizard_api_key"' not in script
    assert '"field": "wizard_port"' not in script
    assert "scripts/validate_fpk.py" in script
    upgrade = script.split("create_upgrade_callback()", 1)[1].split("create_uninstall_callback()", 1)[0]
    assert "|| true" not in upgrade
    assert "migrate-managed-service" in upgrade
    assert "--temp-dir" not in upgrade
    assert '--log-dir "${TRIM_PKGVAR}/logs"' in upgrade
    assert '--resource-dir "${TRIM_PKGVAR}/resources"' in upgrade
    install = script.split("create_install_callback()", 1)[1].split("create_upgrade_callback()", 1)[0]
    assert "migrate-managed-service" in install
    assert "--temp-dir" not in install
    assert '--log-dir "${DATA_DIR}/logs"' in install
    assert '--resource-dir "${DATA_DIR}/resources"' in install
    cgi = script.split("create_ui_cgi()", 1)[1].split("main()", 1)[0]
    assert re.search(r'BACKEND_PORT\s*=\s*"14591"', cgi)
    assert "TRIM_PKGVAR" not in cgi
    assert "TRIM_SERVICE_PORT" not in cgi


def test_build_script_rejects_a_version_that_differs_from_version_fact():
    completed = subprocess.run(
        [str(ROOT / "deploy" / "build_fpk.sh"), "0.0.1"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert f"与 VERSION {expected} 不一致" in completed.stderr
