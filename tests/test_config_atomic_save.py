from types import SimpleNamespace

import yaml

from media_importer.api.config_save import save_config
from media_importer.features.configuration import config_revision


class _Handler:
    def _filter_sensitive_fields(self, body, _original):
        return body

    def _update_config_safely(self, target, source):
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                self._update_config_safely(target[key], value)
            else:
                target[key] = value


def _state(tmp_path):
    paths = {}
    for name in ("source", "temp", "recycle", "logs", "resources", "library"):
        path = tmp_path / name
        path.mkdir()
        paths[name] = str(path)
    config_path = tmp_path / "config.yaml"
    config = {
        "source_dir": paths["source"],
        "temp_dir": paths["temp"],
        "log_dir": paths["logs"],
        "resource_dir": paths["resources"],
        "library_roots": [
            {"id": "main", "name": "主片库", "path": paths["library"], "enabled": True},
        ],
        "default_library_root_id": "main",
        "library_root": paths["library"],
        "fallback_library_root_id": "main",
        "fallback_dir": "未分类",
        "source_policy": {
            "recycle_dir": paths["recycle"],
            "cleanup_source_after_done": False,
        },
        "metadata": {
            "scrape_mode": "provider_first",
            "providers": [{"type": "tmdb", "enabled": True}],
        },
        "llm": {},
    }
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    config["_config_path"] = str(config_path)
    return SimpleNamespace(
        _config=config,
        _global_task_manager=None,
        _global_logger=None,
        _global_watcher=None,
        _global_pipeline=None,
        _config_dirty=False,
    ), config_path


def _save(state, body):
    responses = []
    save_config(
        _Handler(),
        body,
        globals_module=state,
        respond=lambda _handler, code, **payload: responses.append((code, payload)),
    )
    return responses[-1]


def test_save_uses_revision_and_leaves_no_temp_file(tmp_path):
    state, config_path = _state(tmp_path)
    revision = config_revision(state._config)

    code, _payload = _save(state, {
        "_revision": revision,
        "source_policy": {"cleanup_source_after_done": True},
    })

    assert code == 200
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["source_policy"]["cleanup_source_after_done"] is True
    assert list(tmp_path.glob(".config-*.tmp")) == []


def test_stale_revision_does_not_overwrite_file(tmp_path):
    state, config_path = _state(tmp_path)
    before = config_path.read_text(encoding="utf-8")

    code, payload = _save(state, {
        "_revision": "stale",
        "source_policy": {"cleanup_source_after_done": True},
    })

    assert code == 409
    assert "刷新" in payload["message"]
    assert config_path.read_text(encoding="utf-8") == before


def test_invalid_full_config_is_not_persisted(tmp_path):
    state, config_path = _state(tmp_path)
    before = config_path.read_text(encoding="utf-8")

    code, payload = _save(state, {
        "_revision": config_revision(state._config),
        "source_dir": str(tmp_path / "missing-mount"),
    })

    assert code == 400
    assert "未保存" in payload["message"]
    assert config_path.read_text(encoding="utf-8") == before


# Requirement: REQ-20260831-004019
def test_saving_directory_persists_mount_identity_for_runtime_rechecks(tmp_path):
    state, config_path = _state(tmp_path)

    code, _payload = _save(state, {
        "_revision": config_revision(state._config),
        "source_dir": state._config["source_dir"],
    })

    assert code == 200
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    identities = saved["storage_identities"]
    assert identities["source"]["realpath"] == state._config["source_dir"]
    assert isinstance(identities["source"]["device"], int)
    assert "target:main" in identities
    assert state._config["storage_identities"] == identities


# Requirement: REQ-20260831-004019
def test_explicit_directory_rebind_replaces_stale_identity(tmp_path):
    state, config_path = _state(tmp_path)
    stale = {
        "source": {
            "realpath": state._config["source_dir"],
            "device": -1,
            "mount_source": "stale-mount",
        }
    }
    state._config["storage_identities"] = stale
    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    persisted["storage_identities"] = stale
    config_path.write_text(yaml.safe_dump(persisted, allow_unicode=True), encoding="utf-8")

    code, _payload = _save(state, {
        "_revision": config_revision(state._config),
        "source_dir": state._config["source_dir"],
    })

    assert code == 200
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["storage_identities"]["source"]["device"] != -1
    assert saved["storage_identities"]["source"]["mount_source"] != "stale-mount"


def test_automatic_run_requires_all_green_storage(tmp_path):
    state, config_path = _state(tmp_path)
    identities = {
        "source": {
            "realpath": state._config["source_dir"],
            "device": -1,
            "mount_source": "changed",
        }
    }
    state._config["storage_identities"] = identities
    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    persisted["storage_identities"] = identities
    config_path.write_text(yaml.safe_dump(persisted, allow_unicode=True), encoding="utf-8")
    before = config_path.read_text(encoding="utf-8")

    code, payload = _save(state, {
        "_revision": config_revision(state._config),
        "file_watcher": {"enabled": True},
    })

    assert code == 400
    assert "所有存储检查项达到绿色" in payload["message"]
    assert config_path.read_text(encoding="utf-8") == before


def test_fnos_rejects_saving_external_path_without_acl(tmp_path, monkeypatch):
    state, config_path = _state(tmp_path)
    before = config_path.read_text(encoding="utf-8")

    monkeypatch.setattr(
        "media_importer.features.configuration.fnos_directory_access.build_fnos_directory_capability",
        lambda: {"enforced": True, "available": True, "folders": []},
    )

    code, payload = _save(state, {
        "_revision": config_revision(state._config),
        "source_dir": state._config["source_dir"],
    })

    assert code == 400
    assert "尚未授权给本应用" in payload["message"]
    assert config_path.read_text(encoding="utf-8") == before


def test_unrelated_config_save_is_not_blocked_by_stale_fnos_acl(tmp_path, monkeypatch):
    state, _config_path = _state(tmp_path)
    monkeypatch.setattr(
        "media_importer.features.configuration.fnos_directory_access.build_fnos_directory_capability",
        lambda: {"enforced": True, "available": True, "folders": []},
    )

    code, _payload = _save(state, {
        "_revision": config_revision(state._config),
        "llm": {"enabled": False},
    })

    assert code == 200


def test_legacy_library_rules_migrate_only_with_explicit_confirmation(tmp_path):
    state, config_path = _state(tmp_path)
    first = tmp_path / "disk-a"
    second = tmp_path / "disk-b"
    first.mkdir()
    second.mkdir()
    legacy = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    legacy.pop("library_roots")
    legacy.pop("default_library_root_id")
    legacy["library_root"] = ""
    legacy["path_rules"] = [
        {"template": str(first / "电影" / "{title_cn}")},
        {"template": str(second / "剧集" / "{title_cn}")},
    ]
    legacy["fallback_dir"] = str(first / "未分类")
    config_path.write_text(yaml.safe_dump(legacy, allow_unicode=True), encoding="utf-8")
    state._config = {**legacy, "_config_path": str(config_path)}
    roots = [
        {"id": "a", "name": "电影盘", "path": str(first), "enabled": True},
        {"id": "b", "name": "剧集盘", "path": str(second), "enabled": True},
    ]

    code, payload = _save(state, {
        "_revision": config_revision(state._config),
        "library_roots": roots,
        "default_library_root_id": "a",
    })
    assert code == 400
    assert "未保存" in payload["message"]

    code, _payload = _save(state, {
        "_revision": config_revision(state._config),
        "_migrate_legacy_library_rules": True,
        "library_roots": roots,
        "default_library_root_id": "a",
    })
    assert code == 200
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert [rule["library_root_id"] for rule in saved["path_rules"]] == ["a", "b"]
    assert saved["path_rules"][0]["template"] == "电影/{title_cn}"


def _legacy_library_state(tmp_path):
    state, config_path = _state(tmp_path)
    legacy = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    legacy.pop("library_roots")
    legacy.pop("default_library_root_id")
    legacy["library_root"] = ""
    legacy["path_rules"] = [{"template": str(tmp_path / "legacy-disk" / "{title_cn}")}]
    legacy["fallback_dir"] = str(tmp_path / "legacy-disk" / "未分类")
    config_path.write_text(yaml.safe_dump(legacy, allow_unicode=True), encoding="utf-8")
    state._config = {**legacy, "_config_path": str(config_path)}
    return state, config_path, legacy


def _nested_value(config, path):
    value = config
    for key in path:
        value = value[key]
    return value


def test_unrelated_directory_roles_can_save_while_legacy_library_migration_is_pending(
    tmp_path, monkeypatch,
):
    cases = (
        ("source", ("source_dir",), lambda path: {"source_dir": str(path)}),
        ("temp", ("temp_dir",), lambda path: {"temp_dir": str(path)}),
        (
            "recycle",
            ("source_policy", "recycle_dir"),
            lambda path: {"source_policy": {"recycle_dir": str(path)}},
        ),
        ("log", ("log_dir",), lambda path: {"log_dir": str(path)}),
        ("resource", ("resource_dir",), lambda path: {"resource_dir": str(path)}),
    )

    for role, value_path, payload_for in cases:
        case_root = tmp_path / role
        case_root.mkdir()
        state, config_path, legacy = _legacy_library_state(case_root)
        replacement = case_root / "replacement"
        replacement.mkdir()
        monkeypatch.setattr(
            "media_importer.features.configuration.fnos_directory_access.build_fnos_directory_capability",
            lambda path=str(replacement): {
                "enforced": True,
                "available": True,
                "folders": [path],
            },
        )

        code, payload = _save(state, {
            "_revision": config_revision(state._config),
            **payload_for(replacement),
        })

        assert code == 200, f"{role}: {payload}"
        saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert _nested_value(saved, value_path) == str(replacement)
        assert saved["path_rules"] == legacy["path_rules"]
        assert saved["fallback_dir"] == legacy["fallback_dir"]
        assert "library_roots" not in saved


def test_fresh_setup_can_save_one_directory_role_at_a_time(tmp_path):
    state, config_path = _state(tmp_path)
    fresh = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    fresh["source_dir"] = ""
    fresh["source_policy"]["recycle_dir"] = ""
    fresh["library_roots"] = []
    fresh["library_root"] = ""
    fresh["default_library_root_id"] = ""
    fresh["path_rules"] = [{"template": "电影/{title_cn}"}]
    fresh["fallback_library_root_id"] = ""
    config_path.write_text(yaml.safe_dump(fresh, allow_unicode=True), encoding="utf-8")
    state._config = {**fresh, "_config_path": str(config_path)}
    target = tmp_path / "fresh-target"
    target.mkdir()

    code, _payload = _save(state, {
        "_revision": config_revision(state._config),
        "library_roots": [
            {"id": "first", "name": "第一块盘", "path": str(target), "enabled": True},
        ],
        "default_library_root_id": "first",
        "library_root": str(target),
    })

    assert code == 200
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["library_roots"][0]["id"] == "first"
    assert saved["path_rules"][0]["library_root_id"] == "first"


def test_changed_invalid_value_is_not_hidden_by_same_preexisting_error(tmp_path):
    state, config_path = _state(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["file_watcher"] = {"enabled": False, "poll_interval": 5}
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    state._config = {**config, "_config_path": str(config_path)}

    code, payload = _save(state, {
        "_revision": config_revision(state._config),
        "file_watcher": {"poll_interval": 0},
    })

    assert code == 400
    assert "轮询周期" in payload["message"]


def test_empty_temp_directory_can_be_changed(tmp_path):
    state, config_path = _state(tmp_path)
    replacement = tmp_path / "new-temp"
    replacement.mkdir()

    code, _payload = _save(state, {
        "_revision": config_revision(state._config),
        "temp_dir": str(replacement),
    })

    assert code == 200
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["temp_dir"] == str(replacement)


def test_nonempty_temp_directory_blocks_switch_without_deleting_files(tmp_path):
    state, config_path = _state(tmp_path)
    old_temp = tmp_path / "temp"
    checkpoint = old_temp / "movie.mkv.copying"
    checkpoint.write_bytes(b"unfinished")
    replacement = tmp_path / "new-temp"
    replacement.mkdir()
    before = config_path.read_text(encoding="utf-8")

    code, payload = _save(state, {
        "_revision": config_revision(state._config),
        "temp_dir": str(replacement),
    })

    assert code == 400
    assert "旧中转目录仍有文件" in payload["message"]
    assert checkpoint.read_bytes() == b"unfinished"
    assert config_path.read_text(encoding="utf-8") == before


def test_recoverable_temp_task_blocks_switch_even_when_directory_is_empty(tmp_path):
    state, config_path = _state(tmp_path)
    replacement = tmp_path / "new-temp"
    replacement.mkdir()

    class _Tasks:
        def has_running_tasks(self):
            return False

        def list_all_tasks(self, limit=10000):
            return [{"status": "FAILED", "stage": "DONE", "file_location": "temp"}]

    state._global_task_manager = _Tasks()
    before = config_path.read_text(encoding="utf-8")

    code, payload = _save(state, {
        "_revision": config_revision(state._config),
        "temp_dir": str(replacement),
    })

    assert code == 400
    assert "任务依赖旧中转目录" in payload["message"]
    assert config_path.read_text(encoding="utf-8") == before


def test_fnos_rejects_unapproved_temp_directory(tmp_path, monkeypatch):
    state, config_path = _state(tmp_path)
    replacement = tmp_path / "new-temp"
    replacement.mkdir()
    before = config_path.read_text(encoding="utf-8")
    monkeypatch.setattr(
        "media_importer.features.configuration.fnos_directory_access.build_fnos_directory_capability",
        lambda: {"enforced": True, "available": True, "folders": []},
    )

    code, payload = _save(state, {
        "_revision": config_revision(state._config),
        "temp_dir": str(replacement),
    })

    assert code == 400
    assert "中转目录尚未授权" in payload["message"]
    assert config_path.read_text(encoding="utf-8") == before
