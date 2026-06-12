#!/usr/bin/env python3
"""Seeding script: 把覆盖所有 status+stage 组合的任务直接写入运行中的
media_importer SQLite 数据库,用于前端任务工作台按钮 / 编辑字段的回归测试。

可重复执行(先清后插)。task_id 使用 'seed-' 前缀避免与服务运行时的真实任务冲突。

使用:
    python scripts/seed_task_test_data.py [--db PATH]

默认 DB 路径: <repo>/data/tasks.db
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "data", "tasks.db")

SEED_PREFIX = "seed-status-stage-"

NOW = datetime.now(timezone.utc).replace(tzinfo=None)


def ts(offset_minutes: int = 0) -> str:
    return (NOW - timedelta(minutes=offset_minutes)).strftime("%Y-%m-%dT%H:%M:%S")


def build_seed_tasks():
    """返回覆盖所有 status+stage 组合的种子任务列表。

    每条任务都包含典型可编辑字段(scrape_result / dimensions / error_message /
    skip_reason / final_filename 等),方便在任务详情中验证可编辑性和保存生效。
    """
    tasks = []

    # 1. PENDING + QUEUED  → 主: 查看; 副: 移入回收
    tasks.append({
        "task_id": SEED_PREFIX + "01-queued-movie",
        "source_path": "/tmp/nas_media_test/source/SEED_queued/Movie.A.2020.mkv",
        "source_filename": "Movie.A.2020.mkv",
        "file_size_mb": 1234.5,
        "status": "PENDING",
        "stage": "QUEUED",
        "retry_count": 0,
        "created_at": ts(30),
        "last_seen_at": ts(30),
        "current_step": 0,
        "total_steps": 10,
        "step_name": "",
        "percentage": 0,
        "scrape_result": json.dumps({
            "title_cn": "",
            "title_en": "",
            "year": "",
            "type": "",
        }, ensure_ascii=False),
        "scrape_title_cn": "",
        "scrape_title_en": "",
        "scrape_year": "",
        "scrape_media_type": "",
        "scrape_season": None,
        "scrape_episode": None,
        "scrape_dimensions": json.dumps({}, ensure_ascii=False),
        "scrape_confidence": 0,
        "classify_result": "",
        "import_path": "",
        "final_filename": "",
        "file_location": "source",
        "confirm_status": "NONE",
    })

    # 2. PENDING + RUNNING → 主: 查看; 无副按钮(运行中不可删)
    tasks.append({
        "task_id": SEED_PREFIX + "02-running-tv",
        "source_path": "/tmp/nas_media_test/source/SEED_running/Show.B.S01E05.mkv",
        "source_filename": "Show.B.S01E05.mkv",
        "file_size_mb": 800.0,
        "status": "PENDING",
        "stage": "RUNNING",
        "retry_count": 0,
        "created_at": ts(20),
        "started_at": ts(2),
        "last_seen_at": ts(0),
        "current_step": 4,
        "total_steps": 10,
        "step_name": "scrape_metadata",
        "percentage": 45,
        "scrape_result": json.dumps({
            "title_cn": "剧集 B",
            "title_en": "Show B",
            "year": "2021",
            "type": "tv",
            "season": 1,
            "episode": 5,
        }, ensure_ascii=False),
        "scrape_title_cn": "剧集 B",
        "scrape_title_en": "Show B",
        "scrape_year": "2021",
        "scrape_media_type": "tv",
        "scrape_season": 1,
        "scrape_episode": 5,
        "scrape_dimensions": json.dumps({
            "quality": "1080p",
            "source": "BluRay",
        }, ensure_ascii=False),
        "scrape_confidence": 0.85,
        "file_location": "temp",
        "confirm_status": "NONE",
    })

    # 3. PENDING + AWAIT_REVIEW (高置信度,正常) → 主: 去确认; 副: 修改
    tasks.append({
        "task_id": SEED_PREFIX + "03-review-high-confidence",
        "source_path": "/tmp/nas_media_test/source/SEED_review/Title.C.2018.mkv",
        "source_filename": "Title.C.2018.mkv",
        "file_size_mb": 4500.0,
        "status": "PENDING",
        "stage": "AWAIT_REVIEW",
        "retry_count": 0,
        "created_at": ts(60),
        "started_at": ts(50),
        "last_seen_at": ts(40),
        "current_step": 7,
        "total_steps": 10,
        "step_name": "await_review",
        "percentage": 70,
        "scrape_result": json.dumps({
            "title_cn": "标题 C",
            "title_en": "Title C",
            "year": "2018",
            "type": "movie",
            "overview": "测试用电影,置信度较高。",
        }, ensure_ascii=False),
        "scrape_title_cn": "标题 C",
        "scrape_title_en": "Title C",
        "scrape_year": "2018",
        "scrape_media_type": "movie",
        "scrape_dimensions": json.dumps({
            "quality": "2160p",
            "source": "UHD.BluRay",
            "video_codec": "HEVC",
            "audio_codec": "TrueHD.Atmos",
        }, ensure_ascii=False),
        "scrape_confidence": 0.92,
        "file_location": "temp",
        "confirm_status": "PENDING",
        "video_path": "/tmp/nas_media_test/temp/Title.C.2018.mkv",
    })

    # 4. PENDING + AWAIT_REVIEW (低置信度) → 主: 去确认; 副: 修改(需编辑字段)
    tasks.append({
        "task_id": SEED_PREFIX + "04-review-low-confidence",
        "source_path": "/tmp/nas_media_test/source/SEED_review/Ambiguous.D.2015.mkv",
        "source_filename": "Ambiguous.D.2015.mkv",
        "file_size_mb": 2200.0,
        "status": "PENDING",
        "stage": "AWAIT_REVIEW",
        "retry_count": 0,
        "created_at": ts(90),
        "started_at": ts(80),
        "last_seen_at": ts(70),
        "current_step": 7,
        "total_steps": 10,
        "step_name": "await_review",
        "percentage": 70,
        "scrape_result": json.dumps({
            "title_cn": "",
            "title_en": "Ambiguous D",
            "year": "2015",
            "type": "tv",
            "season": 0,
            "episode": 0,
        }, ensure_ascii=False),
        "scrape_title_cn": "",
        "scrape_title_en": "Ambiguous D",
        "scrape_year": "2015",
        "scrape_media_type": "tv",
        "scrape_season": 0,
        "scrape_episode": 0,
        "scrape_dimensions": json.dumps({
            "quality": "1080p",
            "source": "WEB-DL",
        }, ensure_ascii=False),
        "scrape_confidence": 0.45,
        "file_location": "temp",
        "confirm_status": "PENDING",
        "video_path": "/tmp/nas_media_test/temp/Ambiguous.D.2015.mkv",
    })

    # 5. FAILED → 主: 去重试; 副: 移入回收
    tasks.append({
        "task_id": SEED_PREFIX + "05-failed-with-error",
        "source_path": "/tmp/nas_media_test/source/SEED_failed/Broken.E.2017.mkv",
        "source_filename": "Broken.E.2017.mkv",
        "file_size_mb": 600.0,
        "status": "FAILED",
        "stage": "DONE",
        "retry_count": 2,
        "created_at": ts(120),
        "started_at": ts(110),
        "completed_at": ts(100),
        "last_seen_at": ts(100),
        "current_step": 3,
        "total_steps": 10,
        "step_name": "scrape_metadata",
        "percentage": 30,
        "scrape_result": json.dumps({}, ensure_ascii=False),
        "scrape_title_cn": "",
        "scrape_title_en": "",
        "scrape_confidence": 0,
        "file_location": "source",
        "confirm_status": "NONE",
        "error_code": 500,
        "error_message": "TMDB API 请求失败: timeout after 30s",
    })

    # 6. SKIPPED → 主: 去重试; 无副按钮
    tasks.append({
        "task_id": SEED_PREFIX + "06-skipped-duplicate",
        "source_path": "/tmp/nas_media_test/source/SEED_skipped/Duplicate.F.2019.mkv",
        "source_filename": "Duplicate.F.2019.mkv",
        "file_size_mb": 3000.0,
        "status": "SKIPPED",
        "stage": "DONE",
        "retry_count": 0,
        "created_at": ts(150),
        "started_at": ts(145),
        "completed_at": ts(140),
        "last_seen_at": ts(140),
        "current_step": 5,
        "total_steps": 10,
        "step_name": "dedup",
        "percentage": 50,
        "scrape_result": json.dumps({
            "title_cn": "重复资源 F",
            "title_en": "Duplicate F",
            "year": "2019",
        }, ensure_ascii=False),
        "scrape_title_cn": "重复资源 F",
        "scrape_title_en": "Duplicate F",
        "scrape_year": "2019",
        "scrape_media_type": "movie",
        "scrape_confidence": 0.95,
        "file_location": "source",
        "confirm_status": "NONE",
        "skip_reason": "库内已存在相同指纹: a1b2c3d4e5f6g7h8",
    })

    # 7. SUCCESS → 主: 查看结果; 无副按钮
    tasks.append({
        "task_id": SEED_PREFIX + "07-success-imported",
        "source_path": "/tmp/nas_media_test/source/SEED_success/Imported.G.2020.mkv",
        "source_filename": "Imported.G.2020.mkv",
        "file_size_mb": 5500.0,
        "status": "SUCCESS",
        "stage": "DONE",
        "retry_count": 0,
        "created_at": ts(200),
        "started_at": ts(190),
        "completed_at": ts(180),
        "last_seen_at": ts(180),
        "current_step": 10,
        "total_steps": 10,
        "step_name": "imported",
        "percentage": 100,
        "scrape_result": json.dumps({
            "title_cn": "已入库 G",
            "title_en": "Imported G",
            "year": "2020",
            "type": "movie",
        }, ensure_ascii=False),
        "scrape_title_cn": "已入库 G",
        "scrape_title_en": "Imported G",
        "scrape_year": "2020",
        "scrape_media_type": "movie",
        "scrape_dimensions": json.dumps({
            "quality": "1080p",
            "source": "BluRay",
        }, ensure_ascii=False),
        "scrape_confidence": 0.98,
        "file_location": "import",
        "import_success": 1,
        "import_path": "/Movies/Imported.G.2020",
        "final_filename": "Imported.G.2020.1080p.BluRay.x264.mkv",
        "import_video_path": "/Movies/Imported.G.2020/Imported.G.2020.1080p.BluRay.x264.mkv",
        "confirm_status": "CONFIRMED",
        "confirmed_at": ts(180),
    })

    # 8. CANCELLED → 主: 查看; 无副按钮
    tasks.append({
        "task_id": SEED_PREFIX + "08-cancelled-by-user",
        "source_path": "/tmp/nas_media_test/source/SEED_cancelled/Cancelled.H.2022.mkv",
        "source_filename": "Cancelled.H.2022.mkv",
        "file_size_mb": 1100.0,
        "status": "CANCELLED",
        "stage": "DONE",
        "retry_count": 0,
        "created_at": ts(250),
        "started_at": ts(245),
        "completed_at": ts(240),
        "last_seen_at": ts(240),
        "current_step": 2,
        "total_steps": 10,
        "step_name": "cancelled",
        "percentage": 20,
        "scrape_result": json.dumps({}, ensure_ascii=False),
        "file_location": "source",
        "confirm_status": "NONE",
        "error_message": "用户主动取消",
    })

    return tasks


COLUMNS = [
    "task_id", "source_path", "source_filename", "file_size_mb",
    "status", "stage", "retry_count",
    "created_at", "started_at", "completed_at", "last_seen_at",
    "current_step", "total_steps", "step_name", "percentage",
    "bytes_copied", "total_bytes",
    "scrape_result", "scrape_title_cn", "scrape_title_en",
    "scrape_year", "scrape_media_type", "scrape_season", "scrape_episode",
    "scrape_dimensions", "scrape_confidence",
    "classify_result", "import_path", "final_filename",
    "dedup_result", "dedup_existing_file", "import_video_path",
    "video_path", "file_location", "import_success", "confirm_status",
    "confirmed_at", "skip_reason", "error_code", "error_message",
    "scrape_trace", "provider_type", "provider_id",
    "source_fingerprint", "source_file_size", "source_mtime",
]


def seed(db_path: str) -> int:
    if not os.path.exists(db_path):
        print(f"ERROR: DB not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")

    tasks = build_seed_tasks()

    placeholders = ",".join("?" * len(COLUMNS))
    insert_sql = (
        f"INSERT OR REPLACE INTO tasks ({','.join(COLUMNS)}) "
        f"VALUES ({placeholders})"
    )

    inserted = 0
    for task in tasks:
        row = [task.get(col, "") for col in COLUMNS]
        try:
            conn.execute(insert_sql, row)
            inserted += 1
        except sqlite3.Error as e:
            print(f"  Failed to insert {task['task_id']}: {e}", file=sys.stderr)

    conn.commit()

    cur = conn.execute(
        f"SELECT task_id, status, stage FROM tasks "
        f"WHERE task_id LIKE ? ORDER BY task_id",
        (f"{SEED_PREFIX}%",),
    )
    rows = cur.fetchall()
    print(f"Seeded {inserted} tasks into {db_path}")
    print(f"Current seed tasks in DB ({len(rows)}):")
    for r in rows:
        print(f"  - {r[0]:<55s} status={r[1]:<10s} stage={r[2]}")

    conn.close()
    return inserted


def clear(db_path: str) -> int:
    if not os.path.exists(db_path):
        print(f"ERROR: DB not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    cur = conn.execute(
        f"DELETE FROM task_subtitles WHERE task_id LIKE ?",
        (f"{SEED_PREFIX}%",),
    )
    sub_count = cur.rowcount
    cur = conn.execute(
        f"DELETE FROM tasks WHERE task_id LIKE ?",
        (f"{SEED_PREFIX}%",),
    )
    task_count = cur.rowcount
    conn.commit()
    print(f"Cleared {task_count} seed tasks and {sub_count} subtitles from {db_path}")
    conn.close()
    return task_count


def main():
    parser = argparse.ArgumentParser(
        description="Seed status+stage test tasks into the media_importer DB"
    )
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite DB path")
    parser.add_argument(
        "--clear", action="store_true", help="Clear seed tasks only, no insert"
    )
    args = parser.parse_args()

    if args.clear:
        clear(args.db)
    else:
        seed(args.db)


if __name__ == "__main__":
    main()
