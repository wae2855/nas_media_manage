#!/usr/bin/env python3
"""Static file serving and page routing tests.

Tests that index.html, JS, and CSS files are served correctly.
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
from media_importer.api.static_server import StaticServerMixin, WEBUI_DIR
from media_importer.core.metrics import Metrics
from media_importer.features.tasks import TaskManager


class _MockHeaders(dict):
    def get(self, key, default=None):
        return super().get(key.lower(), default)


class _FakeServer:
    def __init__(self):
        self._BaseServer__shutdown_request = False
        self.socket = MagicMock()


def _make_api_handler():
    api = APIHandler.__new__(APIHandler)
    api.requestline = "GET / HTTP/1.1"
    api.command = "GET"
    api.path = "/"
    api.request_version = "HTTP/1.1"
    api._headers_buffer = []
    api.client_address = ("127.0.0.1", 12345)
    api.server = _FakeServer()
    api.headers = _MockHeaders({"content-length": "0"})
    api.rfile = io.BytesIO(b"")
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


class TestIndexHtml(unittest.TestCase):
    """GET / -> 200, HTML content."""

    def test_index_html(self):
        if not os.path.isfile(os.path.join(WEBUI_DIR, "index.html")):
            self.skipTest("index.html not found in webui directory")

        api, captured = _make_api_handler()
        api._serve_static_file("index.html")

        self.assertEqual(captured["code"], 200)
        api.wfile.seek(0)
        content = api.wfile.read()
        self.assertGreater(len(content), 0)
        self.assertIn(b"<", content)


class TestStaticJs(unittest.TestCase):
    """GET /js/cinema-app.js -> 200."""

    def test_static_js(self):
        js_path = os.path.join(WEBUI_DIR, "js", "cinema-app.js")
        if not os.path.isfile(js_path):
            self.skipTest("cinema-app.js not found in webui directory")

        api, captured = _make_api_handler()
        api._serve_static_file("js/cinema-app.js")

        self.assertEqual(captured["code"], 200)


class TestStaticCss(unittest.TestCase):
    """GET /css/ -> 200 for individual CSS files."""

    def test_static_css_file(self):
        css_dir = os.path.join(WEBUI_DIR, "css")
        if not os.path.isdir(css_dir):
            self.skipTest("CSS directory not found in webui")

        css_files = [f for f in os.listdir(css_dir) if f.endswith(".css")]
        if not css_files:
            self.skipTest("No CSS files found in webui directory")

        api, captured = _make_api_handler()
        api._serve_static_file(f"css/{css_files[0]}")

        self.assertEqual(captured["code"], 200)


class TestStaticFileNotFound(unittest.TestCase):
    """GET nonexistent file -> 404."""

    def test_static_not_found(self):
        api, captured = _make_api_handler()
        api._serve_static_file("nonexistent_file_xyz.html")

        self.assertEqual(captured["code"], 404)


class TestStaticPathTraversal(unittest.TestCase):
    """Path traversal attempt -> 403."""

    def test_path_traversal(self):
        api, captured = _make_api_handler()
        api._serve_static_file("../../etc/passwd")

        self.assertEqual(captured["code"], 403)


if __name__ == "__main__":
    unittest.main()
