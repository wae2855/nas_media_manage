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
    for name in ("source", "temp", "recycle", "logs", "library"):
        path = tmp_path / name
        path.mkdir()
        paths[name] = str(path)
    config_path = tmp_path / "config.yaml"
    config = {
        "source_dir": paths["source"],
        "temp_dir": paths["temp"],
        "log_dir": paths["logs"],
        "fallback_dir": paths["library"],
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
