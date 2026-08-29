from __future__ import annotations

import argparse
import importlib.util
import io
import json
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
        "temp_dir": "/var/packages/nas-media-importer/var/tmp",
        "log_dir": "/var/packages/nas-media-importer/var/logs",
        "port": "9855",
        "api_key": "install-key-at-least-16",
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
    assert loaded["temp_dir"] == args.temp_dir
    assert loaded["log_dir"] == args.log_dir
    assert loaded["server"]["port"] == 9855
    assert loaded["server"]["api_key"] == args.api_key
    assert config_path.stat().st_mode & 0o777 == 0o600


def test_initialize_preserves_existing_user_config(tmp_path: Path):
    args = _init_args(tmp_path)
    assert fnos_config.initialize(args) == "created"
    path = Path(args.config)
    path.write_text(path.read_text(encoding="utf-8").replace("/vol2/影视", "/vol3/我的片库"), encoding="utf-8")

    assert fnos_config.initialize(_init_args(tmp_path, library_root="/vol9/不要覆盖")) == "existing"
    assert "/vol3/我的片库" in path.read_text(encoding="utf-8")
    assert "/vol9/不要覆盖" not in path.read_text(encoding="utf-8")


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


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"source_dir": "relative/source"}, "绝对路径"),
        ({"port": "80"}, "1024"),
        ({"api_key": ""}, "API Key"),
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


def _make_fpk(path: Path, forbidden_inner: str | None = None) -> None:
    inner_buffer = io.BytesIO()
    with tarfile.open(fileobj=inner_buffer, mode="w:gz") as inner:
        for name in validate_fpk.INNER_REQUIRED:
            mode = 0o755 if name in validate_fpk.INNER_EXECUTABLE_FILES else 0o644
            _add_bytes(inner, name, b"placeholder", mode)
        if forbidden_inner:
            _add_bytes(inner, forbidden_inner, b"bad")

    manifest = b"appname = nas-media-importer\nversion = 0.3.0\ninstall_dep_apps = python312\n"
    with tarfile.open(path, mode="w:gz") as outer:
        for name in validate_fpk.OUTER_REQUIRED:
            if name == "manifest":
                content = manifest
            elif name == "app.tgz":
                content = inner_buffer.getvalue()
            elif name in validate_fpk.JSON_FILES:
                content = json.dumps([] if name.startswith("wizard/") else {}).encode()
            else:
                content = b"#!/bin/bash\nexit 0\n"
            _add_bytes(outer, name, content, 0o755 if name in validate_fpk.EXECUTABLE_FILES else 0o644)


def test_fpk_validator_accepts_current_contract(tmp_path: Path):
    path = tmp_path / "valid.fpk"
    _make_fpk(path)
    result = validate_fpk.validate(path, "0.3.0")
    assert result["version"] == "0.3.0"
    assert len(result["sha256"]) == 64


def test_fpk_validator_rejects_generated_cache(tmp_path: Path):
    path = tmp_path / "invalid.fpk"
    _make_fpk(path, "server/media_importer/__pycache__/module.cpython-312.pyc")
    with pytest.raises(validate_fpk.ValidationError, match="禁止文件"):
        validate_fpk.validate(path, "0.3.0")


def test_build_script_declares_fnos_runtime_and_visible_failures():
    script = (ROOT / "deploy" / "build_fpk.sh").read_text(encoding="utf-8")
    assert "install_dep_apps      = python312" in script
    assert "/var/apps/python312/target/bin/python3" in script
    assert 'VENV_DIR="${TRIM_PKGVAR}/venv"' in script
    assert "scripts/validate_fpk.py" in script
    upgrade = script.split("create_upgrade_callback()", 1)[1].split("create_uninstall_callback()", 1)[0]
    assert "|| true" not in upgrade
