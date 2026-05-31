#!/usr/bin/env python3
import json
import sqlite3
from datetime import datetime

CLEANER_RECORDS_TABLE = """
CREATE TABLE IF NOT EXISTS cleaner_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    executed_at TEXT NOT NULL,
    mode TEXT NOT NULL,
    total_files INTEGER DEFAULT 0,
    total_size_mb REAL DEFAULT 0,
    items_json TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now'))
)
"""


def init_cleaner_tables(conn: sqlite3.Connection):
    conn.execute(CLEANER_RECORDS_TABLE)
    conn.commit()


def save_cleaner_record(conn: sqlite3.Connection, record: dict) -> int:
    items_json = json.dumps(record.get("items", []), ensure_ascii=False)
    cursor = conn.execute(
        "INSERT INTO cleaner_records (executed_at, mode, total_files, total_size_mb, items_json) VALUES (?, ?, ?, ?, ?)",
        (
            record.get("executed_at", datetime.now().isoformat()),
            record.get("mode", ""),
            record.get("total_files", 0),
            record.get("total_size_mb", 0),
            items_json,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_cleaner_records(conn: sqlite3.Connection, limit: int = 20, offset: int = 0) -> list:
    cursor = conn.execute(
        "SELECT id, executed_at, mode, total_files, total_size_mb, items_json, created_at FROM cleaner_records ORDER BY id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = cursor.fetchall()
    results = []
    for row in rows:
        items = []
        try:
            items = json.loads(row[5])
        except (json.JSONDecodeError, TypeError):
            pass
        results.append({
            "id": row[0],
            "executed_at": row[1],
            "mode": row[2],
            "total_files": row[3],
            "total_size_mb": row[4],
            "items": items,
            "created_at": row[6],
        })
    return results


def get_cleaner_status(conn: sqlite3.Connection) -> dict:
    cursor = conn.execute("SELECT COUNT(*), COALESCE(SUM(total_files), 0), COALESCE(SUM(total_size_mb), 0) FROM cleaner_records")
    row = cursor.fetchone()
    cursor2 = conn.execute("SELECT executed_at FROM cleaner_records ORDER BY id DESC LIMIT 1")
    last_row = cursor2.fetchone()
    return {
        "total_runs": row[0] if row else 0,
        "total_cleaned_files": row[1] if row else 0,
        "total_cleaned_size_mb": round(row[2], 2) if row else 0,
        "last_executed_at": last_row[0] if last_row else None,
    }
