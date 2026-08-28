"""Verify /api/config no longer depends on the deleted _load_prompts_for_ui loader.

These tests cover the post-cleanup state of GET /api/config:
- The handler never calls the removed _load_prompts_for_ui.
- The returned payload has `config` and no longer exposes a `prompts` field.
- The handler implements the unified `(*, body, params, query)` signature.
- No TMDB legacy handler is reachable from the current routes.
"""
import importlib
import inspect
import sys

import pytest

from media_importer.api import config_handlers, globals, tmdb_handlers


@pytest.fixture
def restore_globals_config():
    original = globals._config
    yield
    globals._config = original


def test_config_handler_does_not_call_removed_prompts_loader(restore_globals_config):
    globals._config = {
        "ai_assist": {"api_key": "secret", "model": "gpt-4o-mini"},
        "source_policy": {"cleanup_source_after_done": True},
    }

    mixin = config_handlers.ConfigHandlersMixin()
    called = {"load_prompts": False}

    def fake_load_prompts_for_ui():
        called["load_prompts"] = True
        return {"system_prompt": "x"}

    mixin._load_prompts_for_ui = fake_load_prompts_for_ui

    captured = {}
    mixin.send_response = lambda code: captured.setdefault("code", code)
    mixin.send_header = lambda *args, **kwargs: None
    mixin.end_headers = lambda: None

    class _W:
        def __init__(self):
            self.body = None

        def write(self, data):
            self.body = data

        def flush(self):
            return None

    w = _W()
    mixin.wfile = w

    mixin._config(body={}, params={}, query={})

    assert called["load_prompts"] is False
    assert captured["code"] == 200


def test_config_handler_payload_omits_prompts_field(restore_globals_config):
    globals._config = {
        "ai_assist": {"api_key": "sk-x", "base_url": "http://x", "model": "gpt-4o-mini"},
        "source_policy": {"cleanup_source_after_done": False},
    }

    mixin = config_handlers.ConfigHandlersMixin()

    captured = {}
    mixin.send_response = lambda code: captured.setdefault("code", code)
    mixin.send_header = lambda *args, **kwargs: None
    mixin.end_headers = lambda: None

    class _W:
        def __init__(self):
            self.body = None

        def write(self, data):
            self.body = data

        def flush(self):
            return None

    w = _W()
    mixin.wfile = w

    mixin._config(body={}, params={}, query={})

    body_text = w.body.decode("utf-8") if isinstance(w.body, bytes) else w.body
    assert "prompts" not in body_text
    assert "config" in body_text


def test_config_handler_uses_unified_kwargs_signature():
    sig = inspect.signature(config_handlers.ConfigHandlersMixin._config)
    params = list(sig.parameters.keys())
    assert params == ["self", "body", "params", "query"]


def test_config_handler_resilient_to_legacy_attributes(restore_globals_config):
    """Even if a stale _load_prompts_for_ui exists, the handler must not call it."""
    globals._config = {"ai_assist": {"api_key": "k", "model": "m"}}

    mixin = config_handlers.ConfigHandlersMixin()

    def boom():
        raise AssertionError("_load_prompts_for_ui must not be called by /api/config")

    mixin._load_prompts_for_ui = boom

    mixin.send_response = lambda *args, **kwargs: None
    mixin.send_header = lambda *args, **kwargs: None
    mixin.end_headers = lambda: None

    class _W:
        def write(self, data):
            return None

        def flush(self):
            return None

    mixin.wfile = _W()

    mixin._config(body={}, params={}, query={})


def test_no_legacy_tmdb_handlers_exposed():
    """TMDB preview/search/details are dead legacy methods that the routes file
    does not reference. Their existence on the mixin would invite future
    regressions, so we assert they are gone."""
    assert not hasattr(tmdb_handlers.TMDbHandlersMixin, "_tmdb_preview")
    assert not hasattr(tmdb_handlers.TMDbHandlersMixin, "_tmdb_search")
    assert not hasattr(tmdb_handlers.TMDbHandlersMixin, "_tmdb_details")


def test_no_load_prompts_for_ui_in_api_module(monkeypatch):
    """After cleanup, `_load_prompts_for_ui` must not be present in any loaded
    api/* module."""
    api_modules = [
        name
        for name in list(sys.modules.keys())
        if name.startswith("media_importer.api")
    ]
    for name in api_modules:
        module = importlib.import_module(name)
        assert not hasattr(module, "_load_prompts_for_ui"), (
            f"_load_prompts_for_ui leaked into {name}"
        )


def test_routes_do_not_reference_legacy_tmdb_handlers():
    from media_importer.api import routes

    handler_names = {route.handler_name for route in routes.API_ROUTES}
    assert "_tmdb_preview" not in handler_names
    assert "_tmdb_search" not in handler_names
    assert "_tmdb_details" not in handler_names
    assert "_load_prompts_for_ui" not in handler_names
