#!/usr/bin/env python3
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from media_importer.api import globals as api_globals
from media_importer.api.handler import start_server
from media_importer.core.db.task_repo import create_task, update_task
from media_importer.features.configuration import load_config


def find_free_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class IntegrationRecycleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="nas_integration_recycle_")
        cls.source_dir = os.path.join(cls.tmpdir, "source")
        cls.recycle_dir = os.path.join(cls.tmpdir, "recycle")
        cls.temp_dir = os.path.join(cls.tmpdir, "temp")
        cls.log_dir = os.path.join(cls.tmpdir, "logs")
        cls.data_dir = os.path.join(cls.tmpdir, "data")

        for d in [cls.source_dir, cls.recycle_dir, cls.temp_dir, cls.log_dir, cls.data_dir]:
            os.makedirs(d, exist_ok=True)

        cls.config_path = os.path.join(cls.tmpdir, "config.yaml")
        config_content = {
            "source_dir": cls.source_dir,
            "temp_dir": cls.temp_dir,
            "log_dir": cls.log_dir,
            "llm": {
                "api_key": "test-key",
                "model": "test-model",
            },
            "source_policy": {
                "recycle_dir": cls.recycle_dir,
                "cleanup_mode": "full_cleanup",
                "delete_source_after_import": True,
            },
            "metadata": {
                "providers": [
                    {"type": "tmdb", "enabled": False},
                ],
            },
        }
        with open(cls.config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_content, f, allow_unicode=True)

        cls.config = load_config(cls.config_path)
        cls.config["_data_dir"] = cls.data_dir
        cls.config["file_watcher"] = {"enabled": False}

        cls.port = find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls._server_thread = threading.Thread(
            target=start_server,
            args=("127.0.0.1", cls.port, cls.config),
            daemon=True,
        )
        cls._server_thread.start()

        for _ in range(40):
            try:
                resp = urllib.request.urlopen(f"{cls.base_url}/api/health", timeout=2)
                if resp.status == 200:
                    break
            except Exception:
                time.sleep(0.25)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        conn = api_globals._global_task_manager.conn
        conn.execute("DELETE FROM task_subtitles")
        conn.execute("DELETE FROM tasks")
        conn.commit()

    def _api(self, method, path, body=None):
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Content-Type": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="ignore")
            try:
                return json.loads(raw)
            except Exception:
                return {"code": e.code, "message": raw}
        except Exception as e:
            return {"code": 500, "message": str(e)}

    def _create_test_file(self, filename, directory=None):
        directory = directory or self.source_dir
        filepath = os.path.join(directory, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            f.write("test content")
        return filepath

    def _db_create_task(self, source_path, source_filename, **kwargs):
        conn = api_globals._global_task_manager.conn
        task = create_task(conn, source_path=source_path, source_filename=source_filename)
        if kwargs:
            update_task(conn, task["task_id"], **kwargs)
            task = api_globals._global_task_manager.get_task(task["task_id"])
        return task


class ConfigIntegrationTest(IntegrationRecycleTest):

    def test_config_returns_source_policy_with_recycle_fields(self):
        result = self._api("GET", "/api/config")
        config = result["data"]["config"]
        sp = config.get("source_policy", {})
        self.assertIn("cleanup_mode", sp)
        self.assertIn("delete_source_after_import", sp)
        self.assertIn("recycle_dir", sp)
        self.assertEqual(sp["cleanup_mode"], "full_cleanup")
        self.assertTrue(sp["delete_source_after_import"])
        self.assertEqual(sp["recycle_dir"], self.recycle_dir)

    def test_config_returns_recycle_dir_not_quarantine_dir(self):
        result = self._api("GET", "/api/config")
        config = result["data"]["config"]
        sp = config.get("source_policy", {})
        self.assertIn("recycle_dir", sp)
        self.assertNotIn("quarantine_dir", sp)

    def test_config_save_with_quarantine_dir_migrates_to_recycle_dir(self):
        new_recycle = os.path.join(self.tmpdir, "recycle_migrated")
        os.makedirs(new_recycle, exist_ok=True)

        migrate_config_path = os.path.join(self.tmpdir, "config_migrate.yaml")
        migrate_config = {
            "source_dir": self.source_dir,
            "temp_dir": self.temp_dir,
            "log_dir": self.log_dir,
            "llm": {"api_key": "test-key", "model": "test-model"},
            "source_policy": {
                "quarantine_dir": new_recycle,
                "cleanup_mode": "full_cleanup",
                "delete_source_after_import": True,
            },
            "metadata": {"providers": [{"type": "tmdb", "enabled": False}]},
        }
        with open(migrate_config_path, "w", encoding="utf-8") as f:
            yaml.dump(migrate_config, f, allow_unicode=True)

        migrated = load_config(migrate_config_path)
        self.assertEqual(
            migrated["source_policy"]["recycle_dir"], new_recycle,
            "load_config should migrate quarantine_dir to recycle_dir"
        )

        api_globals._config["source_policy"]["recycle_dir"] = self.recycle_dir


class TaskDBIntegrationTest(IntegrationRecycleTest):

    def test_tasks_return_provider_type_and_id(self):
        filepath = self._create_test_file("movie.mkv")
        task = self._db_create_task(
            filepath, "movie.mkv",
            provider_type="tmdb", provider_id="12345"
        )

        result = self._api("GET", "/api/tasks")
        tasks = result["data"]["tasks"]
        self.assertTrue(len(tasks) >= 1)
        found = None
        for t in tasks:
            if t["task_id"] == task["task_id"]:
                found = t
                break
        self.assertIsNotNone(found)
        self.assertEqual(found["provider_type"], "tmdb")
        self.assertEqual(found["provider_id"], "12345")

    def test_task_with_recycle_file_location_returned(self):
        filepath = self._create_test_file("recycled_movie.mkv", directory=self.recycle_dir)
        task = self._db_create_task(
            filepath, "recycled_movie.mkv",
            file_location="recycle", status="FAILED"
        )

        result = self._api("GET", "/api/tasks")
        tasks = result["data"]["tasks"]
        found = None
        for t in tasks:
            if t["task_id"] == task["task_id"]:
                found = t
                break
        self.assertIsNotNone(found)
        self.assertEqual(found["file_location"], "recycle")

    def test_task_with_source_file_location_shows_correctly(self):
        filepath = self._create_test_file("source_movie.mkv")
        task = self._db_create_task(
            filepath, "source_movie.mkv",
            file_location="source", status="PENDING"
        )

        result = self._api("GET", "/api/tasks")
        tasks = result["data"]["tasks"]
        found = None
        for t in tasks:
            if t["task_id"] == task["task_id"]:
                found = t
                break
        self.assertIsNotNone(found)
        self.assertEqual(found["file_location"], "source")

    def test_task_ignore_moves_file_to_recycle(self):
        filepath = self._create_test_file("ignore_movie.mkv")
        task = self._db_create_task(
            filepath, "ignore_movie.mkv",
            file_location="source", status="FAILED"
        )

        self.assertTrue(os.path.exists(filepath))

        result = self._api("POST", f"/api/tasks/{task['task_id']}/ignore")
        self.assertEqual(result["code"], 200)

        updated = api_globals._global_task_manager.get_task(task["task_id"])
        self.assertEqual(updated["status"], "SKIPPED")
        self.assertEqual(updated["file_location"], "recycle")

        recycle_files = os.listdir(self.recycle_dir)
        self.assertTrue(any("ignore_movie" in f for f in recycle_files))


class SafetyIntegrationTest(IntegrationRecycleTest):

    def test_delete_task_with_delete_files_preserves_recycle_file(self):
        filepath = self._create_test_file("delete_me.mkv", directory=self.recycle_dir)
        task = self._db_create_task(
            filepath, "delete_me.mkv",
            file_location="recycle", status="SKIPPED"
        )

        self.assertTrue(os.path.exists(filepath))

        result = self._api("POST", f"/api/tasks/{task['task_id']}/delete",
                           {"delete_files": True})
        self.assertEqual(result["code"], 200)
        self.assertEqual(result["data"]["file_location"], "recycle")

        self.assertTrue(os.path.exists(filepath))

        gone = api_globals._global_task_manager.get_task(task["task_id"])
        self.assertIsNone(gone)

    def test_delete_task_without_delete_files_only_removes_db(self):
        filepath = self._create_test_file("keep_file.mkv", directory=self.recycle_dir)
        task = self._db_create_task(
            filepath, "keep_file.mkv",
            file_location="recycle", status="SKIPPED"
        )

        self.assertTrue(os.path.exists(filepath))

        result = self._api("DELETE", f"/api/tasks/{task['task_id']}")
        self.assertEqual(result["code"], 200)

        self.assertTrue(os.path.exists(filepath))

        gone = api_globals._global_task_manager.get_task(task["task_id"])
        self.assertIsNone(gone)


class FingerprintIntegrationTest(IntegrationRecycleTest):

    def test_duplicate_fingerprint_gets_rename_detected(self):
        fp = "abc123def456"
        filepath1 = self._create_test_file("original.mkv")
        task1 = self._db_create_task(
            filepath1, "original.mkv",
            source_fingerprint=fp, status="SUCCESS", file_location="import"
        )

        filepath2 = self._create_test_file("duplicate.mkv")
        conn = api_globals._global_task_manager.conn
        from media_importer.core.db.task_repo import find_by_fingerprint
        existing = find_by_fingerprint(conn, fp)
        self.assertIsNotNone(existing)
        self.assertEqual(existing["task_id"], task1["task_id"])

        task2 = self._db_create_task(
            filepath2, "duplicate.mkv",
            source_fingerprint=fp, status="PENDING", file_location="source",
            error_code=1, error_message="RENAME_DETECTED"
        )

        result = self._api("GET", "/api/tasks")
        tasks = result["data"]["tasks"]
        task_ids = {t["task_id"] for t in tasks}
        self.assertIn(task1["task_id"], task_ids)
        self.assertIn(task2["task_id"], task_ids)

        t2_detail = self._api("GET", f"/api/tasks/{task2['task_id']}")
        t2 = t2_detail["data"]["task"]
        self.assertEqual(t2.get("source_fingerprint"), fp)

    def test_source_fingerprint_stored_and_returned(self):
        fp = "sha256:deadbeef1234"
        filepath = self._create_test_file("fingerprinted.mkv")
        task = self._db_create_task(
            filepath, "fingerprinted.mkv",
            source_fingerprint=fp, status="PENDING"
        )

        result = self._api("GET", f"/api/tasks/{task['task_id']}")
        returned_task = result["data"]["task"]
        self.assertEqual(returned_task["source_fingerprint"], fp)

        result = self._api("GET", "/api/tasks")
        tasks = result["data"]["tasks"]
        found = None
        for t in tasks:
            if t["task_id"] == task["task_id"]:
                found = t
                break
        self.assertIsNotNone(found)

        detail = self._api("GET", f"/api/tasks/{task['task_id']}")
        detail_task = detail["data"]["task"]
        self.assertEqual(detail_task.get("source_fingerprint"), fp)


if __name__ == "__main__":
    unittest.main()
