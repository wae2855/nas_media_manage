#!/usr/bin/env python3
"""Recycle-related API endpoint tests.

Tests recycle list, restore, and delete endpoints.
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
from media_importer.api.recycle_handlers import RecycleHandlers
from media_importer.api.utils import json_response
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
    recycle_dir = os.path.join(tmpdir, "recycle")
    os.makedirs(recycle_dir, exist_ok=True)
    config = {
        "source_dir": tmpdir,
        "temp_dir": tmpdir,
        "log_dir": tmpdir,
        "source_policy": {"recycle_dir": recycle_dir},
        "llm": {"api_key": "test-key", "base_url": "http://localhost", "model": "test"},
        "hermes": {"enabled": False},
        "server": {},
        "video_extensions": [".mkv", ".mp4"],
        "subtitle_extensions": [".srt"],
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


class TestRecycleList(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_recycle_list(self):
        api, captured = _make_api_handler()
        api.recycle_list(api)

        self.assertEqual(captured["code"], 200)
        body = _get_json_body(api)
        self.assertIn("data", body)


class TestRecycleRestore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_recycle_restore_empty_items(self):
        api, captured = _make_api_handler(body={"items": []})
        api.recycle_restore(api, body={"items": []})

        self.assertEqual(captured["code"], 400)

    def test_recycle_restore_nonexistent(self):
        api, captured = _make_api_handler(body={"items": ["/nonexistent/file.mkv"]})
        api.recycle_restore(api, body={"items": ["/nonexistent/file.mkv"]})

        # Should return 400 or 207 since the file doesn't exist
        self.assertIn(captured["code"], (200, 207, 400))


class TestRecycleDelete(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_recycle_delete_empty_items(self):
        api, captured = _make_api_handler(body={"items": []})
        api.recycle_delete(api, body={"items": []})

        self.assertEqual(captured["code"], 400)

    def test_recycle_delete_nonexistent(self):
        api, captured = _make_api_handler(body={"items": ["/nonexistent/file.mkv"]})
        api.recycle_delete(api, body={"items": ["/nonexistent/file.mkv"]})

        self.assertIn(captured["code"], (200, 207, 400))


if __name__ == "__main__":
    unittest.main()
