import json
import sqlite3
import uuid
from datetime import datetime
from typing import Optional

from .connection import _row_to_dict, _rows_to_dicts, _sqlite_conn_lock
from .constants import VALID_STATUSES
from .subtitle_repo import get_subtitles_by_task


def create_task(conn: sqlite3.Connection, source_path: str, source_filename: str,
                file_size_mb: float = 0, task_id: Optional[str] = None,
                source_unit_id: str = "") -> dict:
    tid = task_id or uuid.uuid4().hex[:12]
    now = datetime.now().isoformat()
    with _sqlite_conn_lock:
        conn.execute(
            """INSERT INTO tasks
               (task_id, source_path, source_filename, file_size_mb, status,
                created_at, last_seen_at, total_steps, source_unit_id)
               VALUES (?, ?, ?, ?, 'PENDING', ?, ?, 10, ?)""",
            (tid, source_path, source_filename, file_size_mb, now, now, source_unit_id)
        )
        conn.commit()
    return get_task(conn, tid)  # type: ignore[return-value]


def get_task(conn: sqlite3.Connection, task_id: str) -> Optional[dict]:
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
    if row and row.get('match_concerns'):
        try:
            row['match_concerns'] = json.loads(row['match_concerns'])
        except (json.JSONDecodeError, TypeError):
            pass
    if row and row.get('match_trace'):
        try:
            row['match_trace'] = json.loads(row['match_trace'])
        except (json.JSONDecodeError, TypeError):
            pass
    if row and row.get('dim_sources'):
        try:
            row['dim_sources'] = json.loads(row['dim_sources'])
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


def find_by_source_path(conn: sqlite3.Connection, source_path: str) -> Optional[dict]:
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
                        status_filter: Optional[str] = None) -> Optional[dict]:
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
               status: Optional[str] = None, statuses: Optional[list] = None, stage: Optional[str] = None) -> tuple:
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
                "t.scrape_trace, t.scrape_result, t.dim_sources, "
                "t.import_path, t.final_filename, t.dedup_result, t.dedup_existing_file, "
                "t.skip_reason, t.error_message, t.import_success, "
                "t.confirm_status, t.video_path, t.file_location, "
                "t.import_video_path, t.provider_type, t.provider_id, "
                "t.thumbnail_path, "
                "t.confirmed_override, t.confirmed_title, t.override_source, "
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
        if row.get('scrape_result'):
            try:
                row['scrape_result'] = json.loads(row['scrape_result'])
            except (json.JSONDecodeError, TypeError):
                pass
        if row.get('dim_sources'):
            try:
                row['dim_sources'] = json.loads(row['dim_sources'])
            except (json.JSONDecodeError, TypeError):
                pass
        if row.get('dedup_result'):
            try:
                row['dedup_result'] = json.loads(row['dedup_result'])
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
        "scrape_episode", "scrape_dimensions",
        "scrape_trace", "match_level", "match_concerns", "match_trace",
        "dim_sources",
        "classify_result", "import_path", "final_filename",
        "dedup_result", "dedup_existing_file", "import_video_path",
        "video_path", "file_location", "import_success", "confirm_status", "confirmed_at",
        "skip_reason", "error_code", "error_message",
        "provider_type", "provider_id",
        "source_fingerprint", "source_file_size", "source_mtime",
        "thumbnail_path",
        "confirmed_override", "confirmed_title", "override_source",
        "source_unit_id", "source_cleanup_status",
    }
    update_fields = {}
    for k, v in fields.items():
        if k in valid_columns:
            if k in ("scrape_result", "scrape_dimensions", "dedup_result", "scrape_trace", "match_concerns", "match_trace", "dim_sources"):
                if isinstance(v, (dict, list)):
                    update_fields[k] = json.dumps(v, ensure_ascii=False)
                else:
                    update_fields[k] = v
            else:
                update_fields[k] = v
    if not update_fields:
        return get_task(conn, task_id)  # type: ignore[return-value]  # type: ignore[return-value]
    set_clause = ", ".join(f"{k}=?" for k in update_fields)
    params = list(update_fields.values()) + [task_id]
    with _sqlite_conn_lock:
        conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE task_id=?",
            params
        )
        conn.commit()
    return get_task(conn, task_id)  # type: ignore[return-value]  # type: ignore[return-value]


def compare_and_update_task(conn: sqlite3.Connection, task_id: str,
                            expect_status: str, expect_stage: str,
                            **fields) -> Optional[dict]:
    """CAS 状态更新（Phase 2 S3）：仅当当前 status/stage 与期望一致才写入。

    返回更新后的 task；状态已被并发修改则返回 None（调用方据此拒绝操作）。
    消除 check-then-act 竞态（并发双 confirm/双 retry 只成功一次）。
    """
    update_fields = _coerce_fields(fields)
    if not update_fields:
        return get_task(conn, task_id)
    set_clause = ", ".join(f"{k}=?" for k in update_fields)
    params = list(update_fields.values()) + [expect_status, expect_stage, task_id]
    with _sqlite_conn_lock:
        cur = conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE status=? AND stage=? AND task_id=?",
            params,
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
    return get_task(conn, task_id)


def _coerce_fields(fields: dict) -> dict:
    """与 update_task 相同的字段序列化规则（提出复用）。"""
    valid_columns = {
        "source_path", "source_filename", "file_size_mb", "status",
        "stage", "retry_count", "created_at", "started_at", "completed_at",
        "last_seen_at", "current_step", "total_steps", "step_name",
        "percentage", "bytes_copied", "total_bytes",
        "scrape_result", "scrape_title_cn", "scrape_title_en",
        "scrape_year", "scrape_media_type", "scrape_season",
        "scrape_episode", "scrape_dimensions",
        "scrape_trace", "match_level", "match_concerns", "match_trace",
        "dim_sources",
        "classify_result", "import_path", "final_filename",
        "dedup_result", "dedup_existing_file", "import_video_path",
        "video_path", "file_location", "import_success", "confirm_status", "confirmed_at",
        "skip_reason", "error_code", "error_message",
        "provider_type", "provider_id",
        "source_fingerprint", "source_file_size", "source_mtime",
        "thumbnail_path",
        "confirmed_override", "confirmed_title", "override_source",
        "source_unit_id", "source_cleanup_status",
    }
    update_fields = {}
    for k, v in fields.items():
        if k in valid_columns:
            if k in ("scrape_result", "scrape_dimensions", "dedup_result", "scrape_trace", "match_concerns", "match_trace", "dim_sources"):
                if isinstance(v, (dict, list)):
                    update_fields[k] = json.dumps(v, ensure_ascii=False)
                else:
                    update_fields[k] = v
            else:
                update_fields[k] = v
    return update_fields


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
    result["_by_stage"] = stage_counts  # type: ignore[assignment]
    return result


def get_dashboard_task_snapshot(
    conn: sqlite3.Connection,
    *,
    day_start: str,
    day_end: str,
    event_limit: int = 30,
    movie_limit: int = 100,
) -> dict:
    """返回首页所需的有界任务事实，不在 DB 层解释产品文案。"""
    event_limit = max(1, min(int(event_limit), 100))
    movie_limit = max(12, min(int(movie_limit), 300))
    with _sqlite_conn_lock:
        grouped_rows = conn.execute(
            "SELECT status, stage, COUNT(*) AS cnt, "
            "COALESCE(AVG(CASE WHEN status='PENDING' AND stage='RUNNING' "
            "THEN percentage END), 0) AS avg_progress "
            "FROM tasks GROUP BY status, stage"
        ).fetchall()
        today_success = conn.execute(
            "SELECT COUNT(*) FROM tasks "
            "WHERE status='SUCCESS' AND import_success=1 "
            "AND completed_at>=? AND completed_at<?",
            (day_start, day_end),
        ).fetchone()[0]
        event_rows = _rows_to_dicts(
            conn.execute(
                "SELECT task_id, source_filename, status, stage, percentage, "
                "scrape_title_cn, scrape_title_en, scrape_year, error_message, "
                "skip_reason, created_at, started_at, completed_at "
                "FROM tasks ORDER BY COALESCE(completed_at, started_at, created_at) DESC "
                "LIMIT ?",
                (event_limit,),
            ).fetchall()
        )
        movie_rows = _rows_to_dicts(
            conn.execute(
                "SELECT task_id, source_filename, scrape_title_cn, scrape_title_en, "
                "scrape_year, provider_type, provider_id, import_video_path, "
                "thumbnail_path, completed_at "
                "FROM tasks WHERE status='SUCCESS' AND import_success=1 "
                "AND completed_at IS NOT NULL AND thumbnail_path<>'' "
                "ORDER BY completed_at DESC LIMIT ?",
                (movie_limit,),
            ).fetchall()
        )
        protected_rows = conn.execute(
            "SELECT thumbnail_path FROM tasks WHERE status='PENDING' "
            "AND stage IN ('RUNNING', 'AWAIT_REVIEW') AND thumbnail_path<>''"
        ).fetchall()

    return {
        "grouped": [dict(row) for row in grouped_rows],
        "today_success": int(today_success or 0),
        "events": event_rows,
        "movies": movie_rows,
        "protected_thumbnail_paths": [row[0] for row in protected_rows if row[0]],
    }


def delete_task(conn: sqlite3.Connection, task_id: str) -> bool:
    with _sqlite_conn_lock:
        conn.execute("DELETE FROM task_subtitles WHERE task_id=?", (task_id,))
        conn.execute("DELETE FROM tasks WHERE task_id=?", (task_id,))
        conn.commit()
    return True


def clear_tasks(conn: sqlite3.Connection, status: Optional[str] = None, stage: Optional[str] = None) -> int:
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


def get_next_pending(conn: sqlite3.Connection) -> Optional[dict]:
    with _sqlite_conn_lock:
        cur = conn.execute(
            "SELECT task_id FROM tasks WHERE status='PENDING' AND stage='QUEUED' ORDER BY created_at ASC LIMIT 1"
        )
        row = cur.fetchone()
    if row is None:
        return None
    return get_task(conn, row["task_id"])


def claim_next_pending(conn: sqlite3.Connection, *, started_at: Optional[str] = None) -> Optional[dict]:
    """原子领取最早的排队任务，并将其推进到 RUNNING。

    单条 ``UPDATE ... RETURNING`` 同时完成选择和状态迁移，避免多个
    ``run_all`` 线程先读到同一任务、再重复处理。条件更新也让其他进程中的
    竞争者只能领取尚处于 PENDING/QUEUED 的任务。
    """
    claimed_at = started_at or datetime.now().isoformat()
    with _sqlite_conn_lock:
        row = conn.execute(
            """
            UPDATE tasks
               SET stage='RUNNING', started_at=?
             WHERE task_id=(
                   SELECT task_id
                     FROM tasks
                    WHERE status='PENDING' AND stage='QUEUED'
                    ORDER BY created_at ASC
                    LIMIT 1
             )
               AND status='PENDING' AND stage='QUEUED'
            RETURNING task_id
            """,
            (claimed_at,),
        ).fetchone()
        conn.commit()
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
