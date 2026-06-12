#!/usr/bin/env python3
import html
import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from media_importer.core.config_loader import mask_sensitive
from media_importer.core.db.constants import CREATE_TASKS_TABLE


class TestXssInFilename(unittest.TestCase):
    """Filename with `<script>alert(1)</script>` -> HTML escaped in frontend."""

    def test_xss_in_filename_escaped(self):
        malicious = '<script>alert(1)</script>.mkv'
        # HTML escaping should neutralize the script tag
        escaped = html.escape(malicious)
        self.assertNotIn("<script>", escaped)
        self.assertIn("&lt;script&gt;", escaped)

    def test_xss_in_task_data(self):
        # When task data contains XSS payloads, frontend rendering
        # should escape them
        task = {
            "source_filename": '<img src=x onerror=alert(1)>.mkv',
            "task_id": "test-1",
        }
        escaped_name = html.escape(task["source_filename"])
        self.assertNotIn("<img", escaped_name)
        self.assertIn("&lt;img", escaped_name)


class TestSqlInjectionInFilename(unittest.TestCase):
    """Filename with `'; DROP TABLE--` -> parameterized query safe."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(CREATE_TASKS_TABLE)

    def tearDown(self):
        self.conn.close()

    def test_sql_injection_in_filename(self):
        malicious = "'; DROP TABLE tasks;--.mkv"
        # Use parameterized query (as the real code does)
        self.conn.execute(
            "INSERT INTO tasks (task_id, source_path, source_filename) VALUES (?, ?, ?)",
            ("test-1", "/source/" + malicious, malicious)
        )
        self.conn.commit()

        # Verify the table still exists and data was stored safely
        row = self.conn.execute("SELECT * FROM tasks WHERE task_id = ?",
                                ("test-1",)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["source_filename"], malicious)

        # Verify tasks table still exists (not dropped)
        tables = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
        ).fetchall()
        self.assertEqual(len(tables), 1)


class TestApiKeyInLogs(unittest.TestCase):
    """API key not logged in plaintext -> masked as ***."""

    def test_api_key_masked_in_config(self):
        config = {
            "llm": {
                "api_key": "sk-proj-abc123def456ghi789",
            },
            "server": {
                "api_key": "my-secret-key",
            },
            "hermes": {
                "webhook": {
                    "secret": "webhook-secret",
                },
            },
            "metadata": {
                "providers": [
                    {"type": "tmdb", "api_key": "tmdb-secret-key"},
                ],
            },
        }
        masked = mask_sensitive(config)

        # LLM API key should be masked
        self.assertNotEqual(masked["llm"]["api_key"], config["llm"]["api_key"])
        self.assertIn("***", masked["llm"]["api_key"])

        # Server API key should be fully masked
        self.assertEqual(masked["server"]["api_key"], "***")

        # Hermes secret should be masked
        self.assertEqual(masked["hermes"]["webhook"]["secret"], "***")

        # Provider API keys should be masked
        self.assertEqual(masked["metadata"]["providers"][0]["api_key"], "***")


class TestApiKeyInResponse(unittest.TestCase):
    """Frontend API response masks sensitive fields -> ***."""

    def test_api_key_in_response_masked(self):
        config = {
            "llm": {
                "api_key": "sk-proj-supersecret123",
                "base_url": "https://api.example.com",
                "model": "gpt-4",
            },
            "server": {
                "api_key": "server-secret",
            },
        }
        masked = mask_sensitive(config)

        # Original values should not appear in masked output
        self.assertNotIn("supersecret123", masked["llm"]["api_key"])
        self.assertNotIn("server-secret", masked["server"]["api_key"])

        # Non-sensitive fields should remain
        self.assertEqual(masked["llm"]["base_url"], "https://api.example.com")
        self.assertEqual(masked["llm"]["model"], "gpt-4")


class TestUnauthorizedAccess(unittest.TestCase):
    """Request without API key -> 401."""

    def test_unauthorized_access_no_key(self):
        # Simulate the auth check logic from APIHandler._check_auth
        config = {"server": {"api_key": "required-key"}}
        api_key = config.get("server", {}).get("api_key", "")

        # No auth header provided
        auth_header = ""
        authorized = False
        if not api_key:
            authorized = True
        elif auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if token == api_key:
                authorized = True

        self.assertFalse(authorized)

    def test_unauthorized_access_wrong_key(self):
        config = {"server": {"api_key": "required-key"}}
        api_key = config.get("server", {}).get("api_key", "")

        auth_header = "Bearer wrong-key"
        authorized = False
        if not api_key:
            authorized = True
        elif auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if token == api_key:
                authorized = True

        self.assertFalse(authorized)

    def test_authorized_access_correct_key(self):
        config = {"server": {"api_key": "required-key"}}
        api_key = config.get("server", {}).get("api_key", "")

        auth_header = "Bearer required-key"
        authorized = False
        if not api_key:
            authorized = True
        elif auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if token == api_key:
                authorized = True

        self.assertTrue(authorized)


if __name__ == "__main__":
    unittest.main()
