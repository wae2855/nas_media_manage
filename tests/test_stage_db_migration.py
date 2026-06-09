#!/usr/bin/env python3
"""DB migration tests for status+stage dual model.

Verifies that _migrate_schema() correctly adds the stage column
and migrates old status values to new status+stage pairs.
"""
import os
import sys
import json
import shutil
import sqlite3
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.core.db.connection import init_db, _migrate_schema
from media_importer.core.db.constants import CREATE_TASKS_TABLE


class TestStageDbMigration(unittest.TestCase):
    """Verify DB migration for stage column."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="test_stage_migrate_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _create_conn(self, name):
        path = os.path.join(self.tmpdir, name)
        if os.path.exists(path):
            os.remove(path)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        # Create tasks table without stage column (old schema)
        old_ddl = CREATE_TASKS_TABLE.replace(
            "stage TEXT DEFAULT 'QUEUED',", ""
        )
        conn.execute(old_ddl)
        conn.commit()
        return conn

    def _insert_old_task(self, conn, status, **extra):
        import uuid
        fields = {"task_id": str(uuid.uuid4())[:8], "source_path": "/test/movie.mkv",
                  "source_filename": "movie.mkv",
                  "file_size_mb": 100.0, "file_location": "source"}
        fields.update(extra)
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        conn.execute(
            f"INSERT INTO tasks ({cols}) VALUES ({placeholders})",
            list(fields.values()),
        )
        tid = conn.execute(
            "SELECT task_id FROM tasks ORDER BY rowid DESC LIMIT 1"
        ).fetchone()[0]
        # Set legacy status
        conn.execute("UPDATE tasks SET status=? WHERE task_id=?", (status, tid))
        conn.commit()
        return tid

    def _get_task(self, conn, tid):
        row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (tid,)).fetchone()
        return dict(row) if row else None

    def test_migration_adds_stage_column(self):
        conn = self._create_conn("test_adds_stage.db")
        _migrate_schema(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        self.assertIn("stage", columns)
        conn.close()

    def test_migration_converts_pending_to_queued(self):
        conn = self._create_conn("test_pending.db")
        tid = self._insert_old_task(conn, "PENDING")
        _migrate_schema(conn)
        task = self._get_task(conn, tid)
        self.assertEqual(task["status"], "PENDING")
        self.assertEqual(task["stage"], "QUEUED")
        conn.close()

    def test_migration_converts_processing_to_running(self):
        conn = self._create_conn("test_processing.db")
        tid = self._insert_old_task(conn, "PROCESSING")
        _migrate_schema(conn)
        task = self._get_task(conn, tid)
        self.assertEqual(task["status"], "PENDING")
        self.assertEqual(task["stage"], "RUNNING")
        conn.close()

    def test_migration_converts_confirming_to_await_review(self):
        conn = self._create_conn("test_confirming.db")
        tid = self._insert_old_task(conn, "CONFIRMING")
        _migrate_schema(conn)
        task = self._get_task(conn, tid)
        self.assertEqual(task["status"], "PENDING")
        self.assertEqual(task["stage"], "AWAIT_REVIEW")
        conn.close()

    def test_migration_converts_needs_review_to_await_review(self):
        conn = self._create_conn("test_needs_review.db")
        tid = self._insert_old_task(conn, "NEEDS_REVIEW")
        _migrate_schema(conn)
        task = self._get_task(conn, tid)
        self.assertEqual(task["status"], "PENDING")
        self.assertEqual(task["stage"], "AWAIT_REVIEW")
        conn.close()

    def test_migration_converts_success_to_done(self):
        conn = self._create_conn("test_success.db")
        tid = self._insert_old_task(conn, "SUCCESS")
        _migrate_schema(conn)
        task = self._get_task(conn, tid)
        self.assertEqual(task["status"], "SUCCESS")
        self.assertEqual(task["stage"], "DONE")
        conn.close()

    def test_migration_converts_failed_to_done(self):
        conn = self._create_conn("test_failed.db")
        tid = self._insert_old_task(conn, "FAILED")
        _migrate_schema(conn)
        task = self._get_task(conn, tid)
        self.assertEqual(task["status"], "FAILED")
        self.assertEqual(task["stage"], "DONE")
        conn.close()

    def test_migration_converts_skipped_to_done(self):
        conn = self._create_conn("test_skipped.db")
        tid = self._insert_old_task(conn, "SKIPPED")
        _migrate_schema(conn)
        task = self._get_task(conn, tid)
        self.assertEqual(task["status"], "SKIPPED")
        self.assertEqual(task["stage"], "DONE")
        conn.close()

    def test_migration_is_idempotent(self):
        conn = self._create_conn("test_idempotent.db")
        tid = self._insert_old_task(conn, "PROCESSING")
        _migrate_schema(conn)
        task1 = self._get_task(conn, tid)
        _migrate_schema(conn)
        task2 = self._get_task(conn, tid)
        self.assertEqual(task1, task2)
        conn.close()

    def test_new_task_default_stage_is_queued(self):
        conn = self._create_conn("test_default.db")
        _migrate_schema(conn)
        conn.execute(
            "INSERT INTO tasks (task_id, source_path, source_filename, file_size_mb, status) "
            "VALUES (?, ?, ?, ?, ?)",
            ("new-task-id", "/test/new.mkv", "new.mkv", 100.0, "PENDING"),
        )
        tid = conn.execute(
            "SELECT task_id FROM tasks ORDER BY rowid DESC LIMIT 1"
        ).fetchone()[0]
        task = self._get_task(conn, tid)
        self.assertEqual(task["stage"], "QUEUED")
        conn.close()


if __name__ == "__main__":
    unittest.main()