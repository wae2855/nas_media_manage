#!/usr/bin/env python3
"""Dashboard-related API endpoint tests.

Tests health, metrics, run, and queue endpoints by exercising
the handler functions directly with mock request objects.
"""
import io
import json
import os
import shutil
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
from http.server import BaseHTTPRequestHandler

from media_importer.api import globals
from media_importer.api.handler import APIHandler
from media_importer.core.db import init_db
from media_importer.core.metrics import Metrics, get_metrics
from media_importer.features.tasks import TaskManager


class _MockHeaders(dict):
    def get(self, key, default=None):
        return super().get(key.lower(), default)


class _FakeServer:
    """Fake server object to satisfy BaseHTTPRequestHandler.__init__."""
    def __init__(self):
        self._BaseServer__shutdown_request = False
        self.socket = MagicMock()


def _make_api_handler(body=None):
    """Create an APIHandler with mock I/O for testing.

    Returns (api, capture_dict) where capture_dict tracks response_code and body.
    """
    body_bytes = json.dumps(body or {}).encode("utf-8") if body else b""

    # Build a fake request socket
    import socket
    fake_sock = MagicMock(spec=socket.socket)
    fake_sock.makefile.return_value = io.BytesIO(
        b"GET / HTTP/1.1\r\nHost: localhost\r\nContent-Length: " +
        str(len(body_bytes)).encode() + b"\r\n\r\n" + body_bytes
    )

    server = _FakeServer()
    client_addr = ("127.0.0.1", 12345)

    # Create the handler - this calls __init__ which reads from rfile
    # We'll bypass __init__ and set attributes manually
    api = APIHandler.__new__(APIHandler)
    api.requestline = "GET / HTTP/1.1"
    api.command = "GET"
    api.path = "/"
    api.request_version = "HTTP/1.1"
    api._headers_buffer = []
    api.client_address = client_addr
    api.server = server
    api.headers = _MockHeaders({"content-length": str(len(body_bytes))})
    api.rfile = io.BytesIO(body_bytes)
    api.wfile = io.BytesIO()
    api._request_id = "test-req"
    api.query_params = {}

    # Override send_response to capture the code
    _captured = {"code": None}

    def _send_response(code, message=None):
        _captured["code"] = code

    api.send_response = _send_response
    api.send_header = lambda k, v: None
    api.end_headers = lambda: None
    api.flush = lambda: None

    return api, _captured


def _get_json_body(api):
    """Extract the JSON body written to the mock handler's wfile."""
    api.wfile.seek(0)
    raw = api.wfile.read()
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _setup_globals(tmpdir):
    """Set up globals module with test config, task_manager, metrics, etc."""
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
    pipeline.pause.return_value = None
    pipeline.resume.return_value = None
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


class TestHealthEndpoint(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_health_endpoint(self):
        api, captured = _make_api_handler()
        api._health()

        self.assertEqual(captured["code"], 200)
        body = _get_json_body(api)
        self.assertIn("data", body)
        data = body["data"]
        self.assertIn("status", data)
        self.assertIn(data["status"], ("ok", "degraded"))


class TestMetricsEndpoint(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_metrics_endpoint(self):
        api, captured = _make_api_handler()
        api._metrics()

        self.assertEqual(captured["code"], 200)
        body = _get_json_body(api)
        self.assertIn("data", body)
        data = body["data"]
        expected_keys = [
            "total_tasks", "success_tasks", "failed_tasks",
            "success_rate", "avg_processing_time_seconds",
            "total_llm_calls", "queue_paused", "uptime",
        ]
        for key in expected_keys:
            self.assertIn(key, data, f"Missing metric key: {key}")


class TestRunScan(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_run_scan(self):
        api, captured = _make_api_handler()
        api._run_batch()

        self.assertIn(captured["code"], (200, 202))
        body = _get_json_body(api)
        self.assertIn("code", body)


class TestQueuePause(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_queue_pause(self):
        api, captured = _make_api_handler()
        api._queue_pause()

        self.assertEqual(captured["code"], 200)
        body = _get_json_body(api)
        self.assertIn("code", body)


class TestQueueResume(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_queue_resume(self):
        api, captured = _make_api_handler()
        api._queue_resume()

        self.assertEqual(captured["code"], 200)
        body = _get_json_body(api)
        self.assertIn("code", body)


class TestQueueRetryAll(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_queue_retry_all(self):
        api, captured = _make_api_handler()
        api._queue_retry_all()

        self.assertEqual(captured["code"], 200)
        body = _get_json_body(api)
        self.assertIn("code", body)


class TestQueueStatus(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_queue_status(self):
        api, captured = _make_api_handler()
        api._queue_status()

        self.assertEqual(captured["code"], 200)
        body = _get_json_body(api)
        self.assertIn("data", body)
        data = body["data"]
        # Queue status returns 'paused' field
        self.assertTrue("paused" in data or "is_paused" in data)


if __name__ == "__main__":
    unittest.main()
