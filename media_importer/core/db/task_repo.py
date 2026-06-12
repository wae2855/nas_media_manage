import sqlite3
import json
import uuid
from datetime import datetime

from .connection import _sqlite_conn_lock, _row_to_dict, _rows_to_dicts
from .constants import VALID_STATUSES
from .subtitle_repo import get_subtitles_by_task


def create_task(conn: sqlite3.Connection, source_path: str, source_filename: str,
                file_size_mb: float = 0, task_id: str = None) -> dict:
    tid = task_id or uuid.uuid4().hex[:12]
    now = datetime.now().isoformat()
    with _sqlite_conn_lock:
        conn.execute(
            """INSERT INTO tasks
               (task_id, source_path, source_filename, file_size_mb, status,
                created_at, last_seen_at, total_steps)
               VALUES (?, ?, ?, ?, 'PENDING', ?, ?, 10)""",
            (tid, source_path, source_filename, file_size_mb, now, now)
        )
        conn.commit()
    return get_task(conn, tid)


def get_task(conn: sqlite3.Connection, task_id: str) -> dict:
    with _sqlite_conn_lock:
        cur = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,))
        row = _row_to_dict(cur.fetchone())
    if row and row.get('scrape_result'):
        try:
            row['scrape_result'] = json.loads(row['scrape_result'])
        except (json.JSONDecodeError, TypeError):
            pass
    if row and row.get('scrape_dimensions'):
        try:
            row['scrape_dimensions'] = json.loads(row['scrape_dimensions'])
        except (json.JSONDecodeError, TypeError):
            pass
    if row and row.get('dedup_result'):
        try:
            row['dedup_result'] = json.loads(row['dedup_result'])
        except (json.JSONDecodeError, TypeError):
            pass
    if row and row.get('scrape_trace'):
        try:
            row['scrape_trace'] = json.loads(row['scrape_trace'])
        except (json.JSONDecodeError, TypeError):
            pass
    if row:
        subs = get_subtitles_by_task(conn, task_id)
        row['subtitle_files'] = [s.get('target_path', '') or s.get('source_path', '')
                                  for s in subs]
        row['subtitle_source_files'] = [s.get('source_path', '') for s in subs]
        row['subtitle_total'] = len(subs)
        row['subtitle_success'] = sum(1 for s in subs if s.get('status') == 'SUCCESS')
    return row


def find_by_source_path(conn: sqlite3.Connection, source_path: str) -> dict:
    with _sqlite_conn_lock:
        cur = conn.execute(
            "SELECT * FROM tasks WHERE source_path=? ORDER BY created_at DESC LIMIT 1",
            (source_path,)
        )
        return _row_to_dict(cur.fetchone())


def find_by_source_filename(conn: sqlite3.Connection, source_filename: str
                            ) -> list:
    with _sqlite_conn_lock:
        cur = conn.execute(
            "SELECT * FROM tasks WHERE source_filename=? ORDER BY created_at DESC",
            (source_filename,)
        )
        return _rows_to_dicts(cur.fetchall())


def find_by_fingerprint(conn: sqlite3.Connection, fingerprint: str,
                        status_filter: str = None) -> dict:
    if not fingerprint:
        return None
    with _sqlite_conn_lock:
        if status_filter:
            cur = conn.execute(
                "SELECT * FROM tasks WHERE source_fingerprint=? AND status=? ORDER BY created_at DESC LIMIT 1",
                (fingerprint, status_filter)
            )
        else:
            cur = conn.execute(
                "SELECT * FROM tasks WHERE source_fingerprint=? ORDER BY created_at DESC LIMIT 1",
                (fingerprint,)
            )
        return _row_to_dict(cur.fetchone())


def list_tasks(conn: sqlite3.Connection, page: int = 1, page_size: int = 20,
               status: str = None, statuses: list = None, stage: str = None) -> tuple:
    offset = (page - 1) * page_size
    conditions = []
    params = []
    if statuses:
        placeholders = ",".join("?" * len(statuses))
        conditions.append(f"t.status IN ({placeholders})")
        params.extend(statuses)
    elif status:
        status = status.strip().upper()
        if status != "ALL" and status in VALID_STATUSES:
            conditions.append("t.status=?")
            params.append(status)
    if stage:
        stage = stage.strip().upper()
        conditions.append("t.stage=?")
        params.append(stage)
    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    count_sql = "SELECT COUNT(*) FROM tasks t" + where_clause
    data_sql = ("SELECT t.task_id, t.source_path, t.source_filename, t.status, t.stage, "
                "t.percentage, t.file_size_mb, t.retry_count, "
                "t.scrape_title_cn, t.scrape_title_en, t.scrape_year, "
                "t.scrape_media_type, t.scrape_season, t.scrape_episode, "
                "t.scrape_confidence, t.scrape_trace, t.import_path, t.final_filename, "
                "t.skip_reason, t.error_message, t.import_success, "
                "t.confirm_status, t.video_path, t.file_location, "
                "t.import_video_path, t.provider_type, t.provider_id, "
                "t.created_at, t.started_at, t.completed_at, "
                "(SELECT COUNT(*) FROM task_subtitles ts WHERE ts.task_id=t.task_id) AS subtitle_total, "
                "(SELECT COUNT(*) FROM task_subtitles ts WHERE ts.task_id=t.task_id AND ts.status='SUCCESS') AS subtitle_success "
                "FROM tasks t" + where_clause +
                " ORDER BY t.created_at DESC LIMIT ? OFFSET ?")
    with _sqlite_conn_lock:
        total = conn.execute(count_sql, params).fetchone()[0]
        rows = _rows_to_dicts(
            conn.execute(data_sql, params + [page_size, offset]).fetchall()
        )
    for row in rows:
        if row.get('scrape_trace'):
            try:
                row['scrape_trace'] = json.loads(row['scrape_trace'])
            except (json.JSONDecodeError, TypeError):
                pass
    total_pages = max(1, (total + page_size - 1) // page_size)
    return rows, total, total_pages


def update_task(conn: sqlite3.Connection, task_id: str, **fields) -> dict:
    valid_columns = {
        "source_path", "source_filename", "file_size_mb", "status",
        "stage", "retry_count", "created_at", "started_at", "completed_at",
        "last_seen_at", "current_step", "total_steps", "step_name",
        "percentage", "bytes_copied", "total_bytes",
        "scrape_result", "scrape_title_cn", "scrape_title_en",
        "scrape_year", "scrape_media_type", "scrape_season",
        "scrape_episode", "scrape_dimensions", "scrape_confidence",
        "scrape_trace",
        "classify_result", "import_path", "final_filename",
        "dedup_result", "dedup_existing_file", "import_video_path",
        "video_path", "file_location", "import_success", "confirm_status", "confirmed_at",
        "skip_reason", "error_code", "error_message",
        "provider_type", "provider_id",
        "source_fingerprint", "source_file_size", "source_mtime",
    }
    update_fields = {}
    for k, v in fields.items():
        if k in valid_columns:
            if k in ("scrape_result", "scrape_dimensions", "dedup_result", "scrape_trace"):
                if isinstance(v, (dict, list)):
                    update_fields[k] = json.dumps(v, ensure_ascii=False)
                else:
                    update_fields[k] = v
            else:
                update_fields[k] = v
    if not update_fields:
        return get_task(conn, task_id)
    set_clause = ", ".join(f"{k}=?" for k in update_fields)
    params = list(update_fields.values()) + [task_id]
    with _sqlite_conn_lock:
        conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE task_id=?",
            params
        )
        conn.commit()
    return get_task(conn, task_id)


def count_by_status(conn: sqlite3.Connection) -> dict:
    counts = {s: 0 for s in VALID_STATUSES}
    with _sqlite_conn_lock:
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status"
        ).fetchall()
    for row in rows:
        s = row["status"]
        if s in counts:
            counts[s] = row["cnt"]
    return counts


def count_by_status_and_stage(conn: sqlite3.Connection) -> dict:
    result = {s: 0 for s in VALID_STATUSES}
    stage_counts = {}
    with _sqlite_conn_lock:
        rows = conn.execute(
            "SELECT status, stage, COUNT(*) as cnt FROM tasks GROUP BY status, stage"
        ).fetchall()
    for row in rows:
        s = row["status"]
        st = row["stage"] or ""
        if s in result:
            result[s] += row["cnt"]
        if st:
            stage_counts.setdefault(s, {})[st] = row["cnt"]
    result["_by_stage"] = stage_counts
    return result


def delete_task(conn: sqlite3.Connection, task_id: str) -> bool:
    with _sqlite_conn_lock:
        conn.execute("DELETE FROM task_subtitles WHERE task_id=?", (task_id,))
        conn.execute("DELETE FROM tasks WHERE task_id=?", (task_id,))
        conn.commit()
    return True


def clear_tasks(conn: sqlite3.Connection, status: str = None, stage: str = None) -> int:
    with _sqlite_conn_lock:
        conditions = []
        params = []
        if status and status in VALID_STATUSES:
            conditions.append("status=?")
            params.append(status)
        if stage:
            stage = stage.strip().upper()
            conditions.append("stage=?")
            params.append(stage)
        if conditions:
            where = " WHERE " + " AND ".join(conditions)
            cur = conn.execute(
                f"SELECT task_id FROM tasks{where}", params
            )
            tids = [row["task_id"] for row in cur.fetchall()]
            if tids:
                conn.execute("DELETE FROM task_subtitles WHERE task_id IN ({})".format(
                    ",".join("?" * len(tids))), tids)
                conn.execute(f"DELETE FROM tasks{where}", params)
        else:
            conn.execute("DELETE FROM task_subtitles")
            conn.execute("DELETE FROM tasks")
        conn.commit()
        return conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]


def has_running_tasks(conn: sqlite3.Connection) -> bool:
    with _sqlite_conn_lock:
        cur = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status='PENDING' AND stage='RUNNING'"
        )
        return cur.fetchone()[0] > 0


def count_by_specific_status(conn: sqlite3.Connection, status: str) -> int:
    with _sqlite_conn_lock:
        cur = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status=?",
            (status,)
        )
        return cur.fetchone()[0]


def find_failed_too_many(conn: sqlite3.Connection, max_retries: int) -> list:
    with _sqlite_conn_lock:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status='FAILED' AND retry_count>=?",
            (max_retries,)
        ).fetchall()
        return _rows_to_dicts(rows)


def get_next_pending(conn: sqlite3.Connection) -> dict:
    with _sqlite_conn_lock:
        cur = conn.execute(
            "SELECT task_id FROM tasks WHERE status='PENDING' AND stage='QUEUED' ORDER BY created_at ASC LIMIT 1"
        )
        row = cur.fetchone()
    if row is None:
        return None
    return get_task(conn, row["task_id"])


def list_all_tasks(conn: sqlite3.Connection, limit: int = 500) -> list:
    with _sqlite_conn_lock:
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return _rows_to_dicts(rows)


def count_all_tasks(conn: sqlite3.Connection) -> int:
    with _sqlite_conn_lock:
        return conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
