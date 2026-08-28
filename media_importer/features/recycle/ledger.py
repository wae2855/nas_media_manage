import json
import os
import sqlite3
import uuid
from typing import Optional

from media_importer.infrastructure.db import _sqlite_conn_lock


def _canonical_root(recycle_dir: str) -> str:
    if not recycle_dir or not os.path.isdir(recycle_dir):
        return ""
    return os.path.realpath(recycle_dir)


def path_within_recycle_root(recycle_dir: str, candidate: str) -> bool:
    root = _canonical_root(recycle_dir)
    if not root or not candidate:
        return False
    canonical = os.path.realpath(candidate)
    try:
        return os.path.commonpath((root, canonical)) == root and canonical != root
    except ValueError:
        return False


def import_valid_sidecars(conn: sqlite3.Connection, recycle_dir: str) -> int:
    """Import valid legacy sidecars without ever trusting their path as an API ID."""
    root = _canonical_root(recycle_dir)
    if not root:
        return 0

    imported = 0
    with _sqlite_conn_lock:
        for dirpath, _dirnames, filenames in os.walk(root):
            for filename in filenames:
                is_dir_meta = filename.endswith(".dir.meta")
                is_file_meta = filename.endswith(".meta") and not is_dir_meta
                if not is_dir_meta and not is_file_meta:
                    continue

                meta_path = os.path.join(dirpath, filename)
                data_path = meta_path[:-9] if is_dir_meta else meta_path[:-5]
                if not path_within_recycle_root(root, meta_path):
                    continue
                if not path_within_recycle_root(root, data_path):
                    continue
                canonical_data = os.path.realpath(data_path)
                if is_dir_meta and not os.path.isdir(canonical_data):
                    continue
                if is_file_meta and not os.path.isfile(canonical_data):
                    continue

                try:
                    with open(meta_path, "r", encoding="utf-8") as file_obj:
                        meta = json.load(file_obj)
                except (OSError, json.JSONDecodeError, TypeError):
                    continue

                original_path = meta.get("original_path", "")
                moved_at = meta.get("moved_at", "")
                if not isinstance(original_path, str) or not os.path.isabs(original_path):
                    continue
                if not isinstance(moved_at, str) or not moved_at:
                    continue

                size_mb = meta.get("total_size_mb", 0) if is_dir_meta else meta.get("file_size_mb", 0)
                try:
                    size_bytes = max(0, int(float(size_mb or 0) * 1024 * 1024))
                except (TypeError, ValueError):
                    size_bytes = 0

                cursor = conn.execute(
                    """INSERT OR IGNORE INTO recycle_items
                       (item_id, recycle_path, original_path, metadata_path,
                        source_zone, reason, task_id, moved_at, is_dir,
                        size_bytes, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE')""",
                    (
                        uuid.uuid4().hex,
                        canonical_data,
                        original_path,
                        os.path.realpath(meta_path),
                        str(meta.get("source_zone", "other")),
                        str(meta.get("reason", "")),
                        str(meta.get("task_id", "")),
                        moved_at,
                        1 if is_dir_meta else 0,
                        size_bytes,
                    ),
                )
                imported += max(cursor.rowcount, 0)
        conn.commit()
    return imported


def list_active_items(conn: sqlite3.Connection) -> list[dict]:
    with _sqlite_conn_lock:
        rows = conn.execute(
            "SELECT * FROM recycle_items WHERE status='ACTIVE' ORDER BY moved_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_active_item(conn: sqlite3.Connection, item_id: str) -> Optional[dict]:
    if not isinstance(item_id, str) or not item_id:
        return None
    with _sqlite_conn_lock:
        row = conn.execute(
            "SELECT * FROM recycle_items WHERE item_id=? AND status='ACTIVE'",
            (item_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def mark_item_status(conn: sqlite3.Connection, item_id: str, status: str) -> None:
    with _sqlite_conn_lock:
        conn.execute(
            "UPDATE recycle_items SET status=?, updated_at=CURRENT_TIMESTAMP WHERE item_id=?",
            (status, item_id),
        )
        conn.commit()


__all__ = [
    "get_active_item",
    "import_valid_sidecars",
    "list_active_items",
    "mark_item_status",
    "path_within_recycle_root",
]
