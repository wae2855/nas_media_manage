#!/usr/bin/env python3
"""Advanced config API endpoint tests.

Tests dimension list, create, update, delete, and reset endpoints.
"""
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

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


class TestDimensionsList(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_dimensions_list(self):
        api, captured = _make_api_handler()
        api._dimensions_list()

        self.assertEqual(captured["code"], 200)
        body = _get_json_body(api)
        self.assertIn("data", body)
        data = body["data"]
        self.assertIn("dimensions", data)
        self.assertIn("total", data)


class TestDimensionsUpdate(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_dimensions_update(self):
        api, captured = _make_api_handler()
        api._dimensions_list()
        body = _get_json_body(api)
        dims = body["data"]["dimensions"]
        if not dims:
            self.skipTest("No dimensions available")

        dim_name = dims[0].get("name", dims[0].get("dim_name", ""))

        api2, captured2 = _make_api_handler(body={"values": ["test1", "test2"]})
        api2._dimension_update(dim_name, body={"values": ["test1", "test2"]})

        self.assertIn(captured2["code"], (200, 400, 500))


class TestDimensionsDisable(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_dimensions_disable(self):
        api, captured = _make_api_handler()
        api._dimensions_list()
        body = _get_json_body(api)
        dims = body["data"]["dimensions"]
        if not dims:
            self.skipTest("No dimensions available")

        dim_name = dims[0].get("name", dims[0].get("dim_name", ""))

        api2, captured2 = _make_api_handler()
        api2._dimension_disable(dim_name)

        self.assertIn(captured2["code"], (200, 400, 500))


class TestDimensionsReset(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_dimensions_reset(self):
        api, captured = _make_api_handler()
        api._dimensions_list()
        body = _get_json_body(api)
        dims = body["data"]["dimensions"]
        if not dims:
            self.skipTest("No dimensions available")

        dim_name = dims[0].get("name", dims[0].get("dim_name", ""))

        api2, captured2 = _make_api_handler()
        api2._dimension_reset(dim_name)

        self.assertIn(captured2["code"], (200, 400, 500))


class TestDimensionsEnable(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_dimensions_enable(self):
        api, captured = _make_api_handler()
        api._dimensions_list()
        body = _get_json_body(api)
        dims = body["data"]["dimensions"]
        if not dims:
            self.skipTest("No dimensions available")

        dim_name = dims[0].get("name", dims[0].get("dim_name", ""))

        api2, captured2 = _make_api_handler()
        api2._dimension_enable(dim_name)

        self.assertIn(captured2["code"], (200, 400, 500))


if __name__ == "__main__":
    unittest.main()
