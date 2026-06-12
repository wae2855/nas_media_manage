#!/usr/bin/env python3
"""Config-related API endpoint tests.

Tests config get, validate, save section, test-llm, test-hermes,
path test, and provider test endpoints.
"""
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from media_importer.api import globals
from media_importer.api.handler import APIHandler
from media_importer.core.metrics import Metrics
from media_importer.features.tasks import TaskManager


class _MockHeaders(dict):
    def get(self, key, default=None):
        return super().get(key.lower(), default)


class _FakeServer:
    def __init__(self):
        self._BaseServer__shutdown_request = False
        self.socket = MagicMock()


def _make_api_handler(body=None):
    body_bytes = json.dumps(body or {}).encode("utf-8") if body else b""
    api = APIHandler.__new__(APIHandler)
    api.requestline = "GET / HTTP/1.1"
    api.command = "GET"
    api.path = "/"
    api.request_version = "HTTP/1.1"
    api._headers_buffer = []
    api.client_address = ("127.0.0.1", 12345)
    api.server = _FakeServer()
    api.headers = _MockHeaders({"content-length": str(len(body_bytes))})
    api.rfile = io.BytesIO(body_bytes)
    api.wfile = io.BytesIO()
    api._request_id = "test-req"
    api.query_params = {}

    _captured = {"code": None}

    def _send_response(code, message=None):
        _captured["code"] = code

    api.send_response = _send_response
    api.send_header = lambda k, v: None
    api.end_headers = lambda: None
    api.flush = lambda: None

    return api, _captured


def _get_json_body(api):
    api.wfile.seek(0)
    raw = api.wfile.read()
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _setup_globals(tmpdir):
    config = {
        "source_dir": tmpdir,
        "temp_dir": tmpdir,
        "log_dir": tmpdir,
        "source_policy": {"recycle_dir": os.path.join(tmpdir, "recycle")},
        "llm": {"api_key": "sk-test-key-123", "base_url": "http://localhost:8000", "model": "test-model"},
        "hermes": {"enabled": False, "webhook": {"base_url": "", "route_name": "", "secret": "my-secret"}},
        "server": {"api_key": "server-secret-key"},
        "video_extensions": [".mkv", ".mp4"],
        "subtitle_extensions": [".srt"],
        "metadata": {"providers": [{"type": "tmdb", "api_key": "tmdb-key-123", "enabled": True}]},
    }
    globals._config = config
    data_dir = os.path.join(tmpdir, "data")
    os.makedirs(data_dir, exist_ok=True)
    globals._global_task_manager = TaskManager(data_dir, config)
    globals._global_metrics = Metrics()
    globals._global_logger = MagicMock()
    globals._global_notifier = None
    globals._global_watcher = None
    globals._config_dirty = False

    pipeline = MagicMock()
    pipeline.is_paused.return_value = False
    pipeline.config = config
    globals._global_pipeline = pipeline
    return config


def _teardown_globals():
    globals._config = None
    globals._global_pipeline = None
    globals._global_task_manager = None
    globals._global_metrics = None
    globals._global_logger = None
    globals._global_notifier = None
    globals._global_watcher = None
    globals._config_dirty = False


class TestGetConfig(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_get_config(self):
        api, captured = _make_api_handler()
        api._config()

        self.assertEqual(captured["code"], 200)
        body = _get_json_body(api)
        self.assertIn("data", body)

    def test_sensitive_fields_masked(self):
        api, captured = _make_api_handler()
        api._config()

        body = _get_json_body(api)
        data_str = json.dumps(body)
        # The raw API key should NOT appear in the response
        self.assertNotIn("sk-test-key-123", data_str)
        self.assertNotIn("server-secret-key", data_str)
        self.assertNotIn("tmdb-key-123", data_str)


class TestConfigValidate(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_config_validate(self):
        api, captured = _make_api_handler()
        api._config_validate()

        self.assertEqual(captured["code"], 200)
        body = _get_json_body(api)
        self.assertIn("data", body)


class TestSaveConfigSection(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_config_section_invalid_section(self):
        api, captured = _make_api_handler(body={"section": "nonexistent", "data": {}})
        api._config_save_section(body={"section": "nonexistent", "data": {}})

        self.assertIn(captured["code"], (400, 500))


class TestTestLLM(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("media_importer.features.configuration.test_llm_api", return_value=(False, "mock failure"))
    def test_test_llm(self, mock_llm):
        api, captured = _make_api_handler(
            body={"base_url": "http://test", "api_key": "test-key", "model": "test"}
        )
        api._config_test_llm(body={"base_url": "http://test", "api_key": "test-key", "model": "test"})

        self.assertEqual(captured["code"], 200)
        body = _get_json_body(api)
        self.assertIn("data", body)
        self.assertIn("success", body["data"])


class TestTestHermes(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("media_importer.features.configuration.test_hermes_webhook", return_value=(False, "mock failure"))
    def test_test_hermes(self, mock_hermes):
        api, captured = _make_api_handler(
            body={"base_url": "http://test", "route_name": "test", "secret": "test"}
        )
        api._config_test_hermes(body={"base_url": "http://test", "route_name": "test", "secret": "test"})

        self.assertEqual(captured["code"], 200)
        body = _get_json_body(api)
        self.assertIn("data", body)
        self.assertIn("success", body["data"])


class TestPathTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_path_test_valid(self):
        api, captured = _make_api_handler(body={"path": self.tmpdir})
        api._path_test(body={"path": self.tmpdir})

        self.assertEqual(captured["code"], 200)
        body = _get_json_body(api)
        self.assertIn("data", body)

    def test_path_test_missing_path(self):
        api, captured = _make_api_handler(body={})
        api._path_test(body={})

        self.assertIn(captured["code"], (400, 500))


class TestProviderTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_provider_test_unconfigured(self):
        api, captured = _make_api_handler(body={})
        api._provider_test(body={}, provider_type="tmdb")

        self.assertEqual(captured["code"], 200)
        body = _get_json_body(api)
        self.assertIn("data", body)
        self.assertIn("success", body["data"])


if __name__ == "__main__":
    unittest.main()
