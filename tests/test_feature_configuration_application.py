from media_importer.features.configuration import (
    build_config_permission_payload,
    build_config_ui_payload,
    build_path_test_payload,
    build_section_config_update,
    build_watcher_status_payload,
)


def test_build_config_ui_payload_masks_sensitive_and_adds_compat_fields():
    payload = build_config_ui_payload(
        {
            "llm": {"api_key": "sk-secret"},
            "source_policy": {"cleanup_source_after_done": False},
        }
    )

    assert payload["config"]["llm"]["api_key"] == "sk-***"  # 前缀保留脱敏
    assert payload["config"]["source_policy"]["cleanup_mode"] == "read_only"
    assert payload["config"]["source_policy"]["delete_source_after_import"] is False
    assert "prompts" not in payload


# Requirement: REQ-20260901-001019-2
def test_build_config_ui_payload_masks_nested_legacy_credentials():
    payload = build_config_ui_payload({
        "hermes": {
            "webhook": {
                "secret": "must-not-leak",
                "access_token": "must-not-leak-either",
            },
        },
        "extension": {"password": "private"},
        "custom": {"client_secret": "private", "session_token": "private"},
    })

    assert payload["config"]["hermes"]["webhook"]["secret"] == "***"
    assert payload["config"]["hermes"]["webhook"]["access_token"] == "***"
    assert payload["config"]["extension"]["password"] == "***"
    assert payload["config"]["custom"]["client_secret"] == "***"
    assert payload["config"]["custom"]["session_token"] == "***"


def test_build_section_config_update_keeps_existing_provider_api_key():
    section_body = build_section_config_update(
        "metadata.providers",
        {
            "metadata": {
                "providers": [
                    {"type": "tmdb", "enabled": True, "api_key": "***"},
                ]
            }
        },
        {
            "metadata": {
                "providers": [{"type": "tmdb", "api_key": "real-key"}],
            }
        },
    )

    provider = section_body["metadata"]["providers"][0]
    assert provider["api_key"] == "real-key"


def test_build_section_config_update_rejects_unknown_section():
    try:
        build_section_config_update("unknown", {"x": 1}, {})
    except KeyError as exc:
        assert "未知的配置区块" in str(exc)
    else:
        raise AssertionError("expected KeyError")


def test_build_config_permission_payload_uses_body_when_provided():
    captured = {}

    def fake_check_permissions(config):
        captured["config"] = config
        return {"all_ok": True, "issues": []}

    result = build_config_permission_payload(
        {"source_dir": "/tmp/source"},
        {"source_dir": "/tmp/old"},
        fake_check_permissions,
    )

    assert result["all_ok"] is True
    assert captured["config"]["source_dir"] == "/tmp/source"


def test_build_path_test_payload_appends_current_user():
    def fake_check_path_permission(path, need_write=True):
        return {"ok": True, "message": f"{path}:{need_write}"}

    result = build_path_test_payload(
        {"path": "/tmp/demo", "need_write": False},
        fake_check_path_permission,
        lambda: "tester",
    )

    assert result["ok"] is True
    assert result["message"] == "/tmp/demo:False"
    assert result["user"] == "tester"


def test_build_watcher_status_payload_handles_empty_and_running_watcher():
    stopped = build_watcher_status_payload(None)
    assert stopped == {"enabled": False, "status": "not_started"}

    class Watcher:
        poll_interval = 15

        def is_running(self):
            return True

    running = build_watcher_status_payload(Watcher())
    assert running["enabled"] is True
    assert running["poll_interval"] == 15
    assert running["status"] == "running"


def test_running_watcher_status_uses_cached_runtime_facts_without_storage_probe(monkeypatch):
    class Watcher:
        poll_interval = 15
        status = {
            "running": True,
            "source_online": True,
            "automatic_allowed": True,
            "blocking_reasons": [],
        }

        def is_running(self):
            return True

    def unexpected_probe(*_args, **_kwargs):
        raise AssertionError("running watcher status must not probe storage")

    monkeypatch.setattr(
        "media_importer.features.configuration.application_service."
        "inspect_processing_support_readiness",
        unexpected_probe,
    )

    status = build_watcher_status_payload(
        Watcher(),
        {"file_watcher": {"enabled": True}},
    )

    assert status["status"] == "running"
    assert status["automatic_allowed"] is True


# Requirement: REQ-20260901-001019-2
def test_build_watcher_status_payload_reports_runtime_blocker(tmp_path):
    config = {
        "source_dir": str(tmp_path / "missing"),
        "file_watcher": {"enabled": True, "poll_interval": 60},
    }

    status = build_watcher_status_payload(None, config)

    assert status["configured_enabled"] is True
    assert status["enabled"] is False
    assert status["status"] == "blocked"
    assert "文件来源" in status["reason"]
