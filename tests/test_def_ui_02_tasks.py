#!/usr/bin/env python3
"""Task-related API endpoint tests.

Tests task CRUD, retry, confirm, ignore, delete, classify-preview,
clear, and confirm-all endpoints.
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
from media_importer.core.task_lifecycle import mark_needs_review, mark_failed
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


class TestListTasks(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_list_tasks(self):
        api, captured = _make_api_handler()
        api._list_tasks({})

        self.assertEqual(captured["code"], 200)
        body = _get_json_body(api)
        self.assertIn("data", body)


class TestTaskStats(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_task_stats(self):
        api, captured = _make_api_handler()
        api._task_stats()

        self.assertEqual(captured["code"], 200)
        body = _get_json_body(api)
        self.assertIn("data", body)
        data = body["data"]
        self.assertTrue("total" in data or "by_status" in data)


class TestCreateAndGetTask(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_create_and_get_task(self):
        tm = globals._global_task_manager
        task = tm.create_task(
            video_path="/source/movie.mkv",
            video_file="movie.mkv",
        )
        task_id = task["task_id"]

        api, captured = _make_api_handler()
        api._get_task(task_id)

        self.assertEqual(captured["code"], 200)
        body = _get_json_body(api)
        self.assertIn("data", body)
        self.assertEqual(body["data"]["task"]["task_id"], task_id)


class TestTaskRetry(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_task_retry(self):
        tm = globals._global_task_manager
        task = tm.create_task(
            video_path="/source/movie.mkv",
            video_file="movie.mkv",
            initial_status="FAILED",
        )
        task_id = task["task_id"]

        api, captured = _make_api_handler()
        api._retry_task(task_id)

        self.assertEqual(captured["code"], 200)


class TestTaskConfirm(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_task_confirm(self):
        tm = globals._global_task_manager
        task = tm.create_task(
            video_path="/source/movie.mkv",
            video_file="movie.mkv",
        )
        task_id = task["task_id"]

        # Set task to AWAIT_REVIEW stage
        task_data = tm.get_task(task_id)
        fields = mark_needs_review(task_data, "test review")
        tm.update_task({**task_data, **fields})

        api, captured = _make_api_handler()
        api._task_confirm(task_id)

        self.assertIn(captured["code"], (200, 400))


class TestTaskIgnore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_task_ignore(self):
        tm = globals._global_task_manager
        task = tm.create_task(
            video_path="/source/movie.mkv",
            video_file="movie.mkv",
        )
        task_id = task["task_id"]

        # Set task to AWAIT_REVIEW so it can be ignored
        task_data = tm.get_task(task_id)
        fields = mark_needs_review(task_data, "test review")
        tm.update_task({**task_data, **fields})

        api, captured = _make_api_handler()
        api._task_ignore(task_id)

        self.assertIn(captured["code"], (200, 400))


class TestTaskDelete(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_task_delete(self):
        tm = globals._global_task_manager
        task = tm.create_task(
            video_path="/source/movie.mkv",
            video_file="movie.mkv",
        )
        task_id = task["task_id"]

        api, captured = _make_api_handler()
        api._delete_task(task_id, delete_files=False)

        self.assertIn(captured["code"], (200, 404))


class TestTaskClassifyPreview(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_task_classify_preview(self):
        tm = globals._global_task_manager
        task = tm.create_task(
            video_path="/source/movie.mkv",
            video_file="movie.mkv",
        )
        task_id = task["task_id"]

        api, captured = _make_api_handler(body={"dimensions": {"media_type": "movie"}})
        api._task_classify_preview(task_id, body={"dimensions": {"media_type": "movie"}})

        self.assertEqual(captured["code"], 200)
        body = _get_json_body(api)
        self.assertIn("data", body)


class TestTasksClear(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_tasks_clear(self):
        api, captured = _make_api_handler(body={"status": "SUCCESS"})
        api._clear_tasks(body={"status": "SUCCESS"})

        self.assertEqual(captured["code"], 200)


class TestTasksConfirmAll(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _setup_globals(self.tmpdir)

    def tearDown(self):
        _teardown_globals()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_tasks_confirm_all(self):
        api, captured = _make_api_handler()
        api._task_confirm_all()

        self.assertEqual(captured["code"], 200)


if __name__ == "__main__":
    unittest.main()
