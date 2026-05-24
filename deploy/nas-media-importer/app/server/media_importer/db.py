#!/usr/bin/env python3
import sqlite3
import os
import json
import logging
import threading
from datetime import datetime


logger = logging.getLogger(__name__)
_sqlite_conn_lock = threading.RLock()


CREATE_TASKS_TABLE = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT UNIQUE NOT NULL,
    source_path TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    file_size_mb REAL DEFAULT 0,
    status TEXT DEFAULT 'PENDING',
    retry_count INTEGER DEFAULT 0,
    created_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    last_seen_at TEXT,
    current_step INTEGER DEFAULT 0,
    total_steps INTEGER DEFAULT 10,
    step_name TEXT DEFAULT '',
    percentage INTEGER DEFAULT 0,
    bytes_copied INTEGER DEFAULT 0,
    total_bytes INTEGER DEFAULT 0,
    scrape_result TEXT DEFAULT '{}',
    scrape_title_cn TEXT,
    scrape_title_en TEXT,
    scrape_year TEXT,
    scrape_media_type TEXT,
    scrape_season INTEGER,
    scrape_episode INTEGER,
    scrape_dimensions TEXT DEFAULT '{}',
    scrape_confidence REAL DEFAULT 0,
    classify_result TEXT DEFAULT '',
    import_path TEXT DEFAULT '',
    final_filename TEXT DEFAULT '',
    dedup_result TEXT DEFAULT '{}',
    dedup_existing_file TEXT DEFAULT '',
    import_video_path TEXT DEFAULT '',
    video_path TEXT DEFAULT '',
    file_location TEXT DEFAULT 'source',
    import_success INTEGER DEFAULT 0,
    confirm_status TEXT DEFAULT 'NONE',
    confirmed_at TEXT,
    skip_reason TEXT DEFAULT '',
    error_code INTEGER DEFAULT 0,
    error_message TEXT DEFAULT ''
)
"""

CREATE_SUBTITLES_TABLE = """
CREATE TABLE IF NOT EXISTS task_subtitles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    target_path TEXT DEFAULT '',
    lang TEXT DEFAULT '',
    status TEXT DEFAULT 'PENDING',
    import_path TEXT DEFAULT '',
    confirm_status TEXT DEFAULT 'NONE',
    error_message TEXT DEFAULT '',
    created_at TEXT,
    completed_at TEXT
)
"""

CREATE_TASKS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_tasks_source_path ON tasks(source_path)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at DESC)",
]

CREATE_SUBTITLES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_subtitles_task_id ON task_subtitles(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_subtitles_source_path ON task_subtitles(source_path)",
]

CREATE_DIMENSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS dimensions (
    name TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'ai',
    sort_order INTEGER DEFAULT 0,
    ai_prompt TEXT,
    tmdb_field TEXT,
    value_list TEXT NOT NULL,
    default_value_list TEXT DEFAULT '',
    color TEXT DEFAULT '#6c757d',
    is_system INTEGER DEFAULT 1,
    is_enabled INTEGER DEFAULT 0,
    required_tier TEXT DEFAULT 'free',
    description TEXT DEFAULT ''
)
"""

DEFAULT_DIMENSIONS = [
    {
        "name": "media_type",
        "label": "影视类型",
        "source_type": "ai+tmdb",
        "sort_order": 1,
        "ai_prompt": "请判断这是电影（movie）还是电视剧（tv）。判断依据：如果文件名中包含季集编号（如S01E01、S2E03等格式），则为电视剧（tv）；如果是完整独立的影视故事，则为电影（movie）。电视电影/网络电影仍归为movie。",
        "tmdb_field": "",
        "value_list": json.dumps([
            {"value": "movie", "label": "电影"},
            {"value": "tv", "label": "剧集"}
        ], ensure_ascii=False),
        "default_value_list": json.dumps([
            {"value": "movie", "label": "电影"},
            {"value": "tv", "label": "剧集"}
        ], ensure_ascii=False),
        "color": "#3b82f6",
        "is_system": 1,
        "is_enabled": 1,
        "required_tier": "free",
        "description": "区分电影和电视剧，决定目录结构形态"
    },
    {
        "name": "documentary",
        "label": "是否纪录片",
        "source_type": "ai",
        "sort_order": 2,
        "ai_prompt": "请判断是否为纪录片（true/false）。纪录片是以真实事件、人物、自然、历史、社会等为主题的非虚构影视作品，包括自然纪录片（如《地球脉动》）、历史纪录片、社会纪录片、科学纪录片等。基于真实事件改编的剧情片（如《辛德勒的名单》）不算纪录片，应选false。",
        "tmdb_field": "",
        "value_list": json.dumps([
            {"value": "true", "label": "是"},
            {"value": "false", "label": "否"}
        ], ensure_ascii=False),
        "default_value_list": json.dumps([
            {"value": "true", "label": "是"},
            {"value": "false", "label": "否"}
        ], ensure_ascii=False),
        "color": "#f59e0b",
        "is_system": 1,
        "is_enabled": 1,
        "required_tier": "free",
        "description": "将纪录片从虚构作品中分离"
    },
    {
        "name": "restricted_level",
        "label": "限制级分类",
        "source_type": "ai",
        "sort_order": 3,
        "ai_prompt": "请判断该影视内容的年龄分级，从以下选项中选择最匹配的一个：\n- 0-6：幼儿/儿童内容，完全无任何不适画面，如幼儿启蒙动画、低龄卡通\n- 7-12：家庭向，适合全家观看，无暴力/恐怖/敏感内容，如合家欢动画、儿童剧集（对应美国PG及以下）\n- 13-16：青少年向，可能含轻微暴力、恐怖或敏感话题，但不涉及露骨画面（对应美国PG-13）\n- 17+：成人内容，含明显暴力血腥、裸露性爱、深度恐怖等（对应美国R级或同等）\n\n判断方法：如你对该作品不熟悉，请联网搜索该影视的官方分级（如MPAA分级、豆瓣家长指引等）后做出判断。切勿将17+内容误判为低年龄段。",
        "tmdb_field": "",
        "value_list": json.dumps([
            {"value": "0-6", "label": "幼儿/儿童"},
            {"value": "7-12", "label": "家庭向"},
            {"value": "13-16", "label": "青少年向"},
            {"value": "17+", "label": "成人内容"}
        ], ensure_ascii=False),
        "default_value_list": json.dumps([
            {"value": "0-6", "label": "幼儿/儿童"},
            {"value": "7-12", "label": "家庭向"},
            {"value": "13-16", "label": "青少年向"},
            {"value": "17+", "label": "成人内容"}
        ], ensure_ascii=False),
        "color": "#ec4899",
        "is_system": 1,
        "is_enabled": 1,
        "required_tier": "free",
        "description": "按年龄分级隔离成人内容"
    },
    {
        "name": "animation",
        "label": "是否动漫",
        "source_type": "ai",
        "sort_order": 4,
        "ai_prompt": "请判断是否为动漫/动画作品（true/false）。判断标准：以动画/手绘/CG形式制作的作品均为true，包括日本动画（日漫）、中国动画（国漫）、欧美动画电影、动画短片等。真人拍摄+少量CG特效的作品（如漫威电影）不算动画，应选false。",
        "tmdb_field": "",
        "value_list": json.dumps([
            {"value": "true", "label": "是"},
            {"value": "false", "label": "否"}
        ], ensure_ascii=False),
        "default_value_list": json.dumps([
            {"value": "true", "label": "是"},
            {"value": "false", "label": "否"}
        ], ensure_ascii=False),
        "color": "#8b5cf6",
        "is_system": 1,
        "is_enabled": 0,
        "required_tier": "free",
        "description": "将动漫/动画从真人作品中分离"
    },
    {
        "name": "region",
        "label": "地区",
        "source_type": "ai+tmdb",
        "sort_order": 5,
        "ai_prompt": "请判断该影视作品的主要制片国家或地区，从以下选项中选择：us（美国）、cn（中国大陆）、hk（中国香港）、tw（中国台湾）、jp（日本）、kr（韩国）、gb（英国）、fr（法国）、de（德国）、it（意大利）、es（西班牙）、in（印度）、other（其他）。判断依据：优先看制作公司/出品方所在国家，其次看主要创作团队国籍和语言。合拍片选择投资占比最大或主创团队所属的国家。如不确定，请联网搜索该作品的制片信息。",
        "tmdb_field": "origin_country",
        "value_list": json.dumps([
            {"value": "us", "label": "美国", "tmdb_codes": ["US"]},
            {"value": "cn", "label": "中国大陆", "tmdb_codes": ["CN"]},
            {"value": "hk", "label": "中国香港", "tmdb_codes": ["HK"]},
            {"value": "tw", "label": "中国台湾", "tmdb_codes": ["TW"]},
            {"value": "jp", "label": "日本", "tmdb_codes": ["JP"]},
            {"value": "kr", "label": "韩国", "tmdb_codes": ["KR"]},
            {"value": "gb", "label": "英国", "tmdb_codes": ["GB", "IE"]},
            {"value": "fr", "label": "法国", "tmdb_codes": ["FR"]},
            {"value": "de", "label": "德国", "tmdb_codes": ["DE"]},
            {"value": "it", "label": "意大利", "tmdb_codes": ["IT"]},
            {"value": "es", "label": "西班牙", "tmdb_codes": ["ES"]},
            {"value": "in", "label": "印度", "tmdb_codes": ["IN"]},
            {"value": "other", "label": "其他"}
        ], ensure_ascii=False),
        "default_value_list": json.dumps([
            {"value": "us", "label": "美国", "tmdb_codes": ["US"]},
            {"value": "cn", "label": "中国大陆", "tmdb_codes": ["CN"]},
            {"value": "hk", "label": "中国香港", "tmdb_codes": ["HK"]},
            {"value": "tw", "label": "中国台湾", "tmdb_codes": ["TW"]},
            {"value": "jp", "label": "日本", "tmdb_codes": ["JP"]},
            {"value": "kr", "label": "韩国", "tmdb_codes": ["KR"]},
            {"value": "gb", "label": "英国", "tmdb_codes": ["GB", "IE"]},
            {"value": "fr", "label": "法国", "tmdb_codes": ["FR"]},
            {"value": "de", "label": "德国", "tmdb_codes": ["DE"]},
            {"value": "it", "label": "意大利", "tmdb_codes": ["IT"]},
            {"value": "es", "label": "西班牙", "tmdb_codes": ["ES"]},
            {"value": "in", "label": "印度", "tmdb_codes": ["IN"]},
            {"value": "other", "label": "其他"}
        ], ensure_ascii=False),
        "color": "#10b981",
        "is_system": 1,
        "is_enabled": 0,
        "required_tier": "pro",
        "description": "按制片国家/地区分拣"
    },
    {
        "name": "origin_lang",
        "label": "原始语言",
        "source_type": "ai+tmdb",
        "sort_order": 6,
        "ai_prompt": "请判断该影视作品的原始语言，从以下选项中选择：zh（中文）、en（英语）、ja（日语）、ko（韩语）、other（其他语言）。判断依据：原始语言是作品最初制作时使用的语言，不是配音或翻译后的语言。例如日本动漫的原始语言是ja，即使有中文配音版也选ja。",
        "tmdb_field": "original_language",
        "value_list": json.dumps([
            {"value": "zh", "label": "中文"},
            {"value": "en", "label": "英语"},
            {"value": "ja", "label": "日语"},
            {"value": "ko", "label": "韩语"},
            {"value": "other", "label": "其他"}
        ], ensure_ascii=False),
        "default_value_list": json.dumps([
            {"value": "zh", "label": "中文"},
            {"value": "en", "label": "英语"},
            {"value": "ja", "label": "日语"},
            {"value": "ko", "label": "韩语"},
            {"value": "other", "label": "其他"}
        ], ensure_ascii=False),
        "color": "#06b6d4",
        "is_system": 1,
        "is_enabled": 0,
        "required_tier": "pro",
        "description": "按原始语言分拣（中/英/日/韩）"
    },
    {
        "name": "resolution_tier",
        "label": "分辨率等级",
        "source_type": "file",
        "sort_order": 7,
        "ai_prompt": "",
        "tmdb_field": "",
        "value_list": json.dumps([
            {"value": "4k", "label": "4K", "min_width": 3840},
            {"value": "1080p", "label": "1080P", "min_width": 1920},
            {"value": "720p", "label": "720P", "min_width": 1280},
            {"value": "sd", "label": "标清", "min_width": 0}
        ], ensure_ascii=False),
        "default_value_list": json.dumps([
            {"value": "4k", "label": "4K", "min_width": 3840},
            {"value": "1080p", "label": "1080P", "min_width": 1920},
            {"value": "720p", "label": "720P", "min_width": 1280},
            {"value": "sd", "label": "标清", "min_width": 0}
        ], ensure_ascii=False),
        "color": "#f97316",
        "is_system": 1,
        "is_enabled": 0,
        "required_tier": "pro",
        "description": "按视频分辨率分拣（4K/1080P/720P）"
    },
    {
        "name": "broad_genre",
        "label": "类型",
        "source_type": "ai+tmdb",
        "sort_order": 8,
        "ai_prompt": "请判断该影视作品的主要类型，从以下选项中选择风格最鲜明突出的一个：horror_mystery（恐怖/悬疑：以恐惧、惊悚、推理为核心，如恐怖片、悬疑片、惊悚片）、scifi_fantasy（科幻/奇幻：以未来科技或奇幻世界观为背景，如太空歌剧、超级英雄、魔幻）、war（战争/军事：以战争或军事行动为核心题材）、action_adventure（动作/冒险：以动作场面或冒险旅程为核心，如功夫片、探险片）、comedy（喜剧：以幽默搞笑为核心，如爆笑喜剧、黑色幽默）、drama_romance（剧情/情感：以人物情感或社会现实为核心，如文艺片、爱情片、犯罪剧情片）、documentary（纪录/纪实：非虚构纪实作品）、music（音乐/演出：以音乐或演出为核心，如演唱会电影、音乐传记）、kids（儿童/家庭：面向低龄观众的儿童节目）、tv_show（电视节目：综艺、脱口秀、真人秀等非虚构电视节目）、other（其他：不属于以上任何类型）。如果同时属于多个类型，选择风格最突出、最能代表该作品核心特征的那个。",
        "tmdb_field": "genres",
        "value_list": json.dumps([
            {"value": "horror_mystery", "label": "恐怖/悬疑", "tmdb_genre_ids": [27, 9648, 53, 10758], "priority": 1},
            {"value": "scifi_fantasy", "label": "科幻/奇幻", "tmdb_genre_ids": [878, 14, 10765], "priority": 2},
            {"value": "war", "label": "战争/军事", "tmdb_genre_ids": [10752, 10768], "priority": 3},
            {"value": "action_adventure", "label": "动作/冒险", "tmdb_genre_ids": [28, 12, 10759, 37], "priority": 4},
            {"value": "comedy", "label": "喜剧", "tmdb_genre_ids": [35], "priority": 5},
            {"value": "drama_romance", "label": "剧情/情感", "tmdb_genre_ids": [18, 10749, 80, 36, 10751, 10766, 10770], "priority": 6},
            {"value": "documentary", "label": "纪录/纪实", "tmdb_genre_ids": [99, 10761], "priority": 7},
            {"value": "music", "label": "音乐/演出", "tmdb_genre_ids": [10402], "priority": 8},
            {"value": "kids", "label": "儿童/家庭", "tmdb_genre_ids": [10762], "priority": 9},
            {"value": "tv_show", "label": "电视节目", "tmdb_genre_ids": [10763, 10764, 10767], "priority": 10},
            {"value": "other", "label": "其他", "tmdb_genre_ids": [], "priority": 11}
        ], ensure_ascii=False),
        "default_value_list": json.dumps([
            {"value": "horror_mystery", "label": "恐怖/悬疑", "tmdb_genre_ids": [27, 9648, 53, 10758], "priority": 1},
            {"value": "scifi_fantasy", "label": "科幻/奇幻", "tmdb_genre_ids": [878, 14, 10765], "priority": 2},
            {"value": "war", "label": "战争/军事", "tmdb_genre_ids": [10752, 10768], "priority": 3},
            {"value": "action_adventure", "label": "动作/冒险", "tmdb_genre_ids": [28, 12, 10759, 37], "priority": 4},
            {"value": "comedy", "label": "喜剧", "tmdb_genre_ids": [35], "priority": 5},
            {"value": "drama_romance", "label": "剧情/情感", "tmdb_genre_ids": [18, 10749, 80, 36, 10751, 10766, 10770], "priority": 6},
            {"value": "documentary", "label": "纪录/纪实", "tmdb_genre_ids": [99, 10761], "priority": 7},
            {"value": "music", "label": "音乐/演出", "tmdb_genre_ids": [10402], "priority": 8},
            {"value": "kids", "label": "儿童/家庭", "tmdb_genre_ids": [10762], "priority": 9},
            {"value": "tv_show", "label": "电视节目", "tmdb_genre_ids": [10763, 10764, 10767], "priority": 10},
            {"value": "other", "label": "其他", "tmdb_genre_ids": [], "priority": 11}
        ], ensure_ascii=False),
        "color": "#ef4444",
        "is_system": 1,
        "is_enabled": 0,
        "required_tier": "premium",
        "description": "按影视类型分拣（恐怖/科幻/战争/喜剧/动作/剧情等）"
    },
]

VALID_STATUSES = [
    "PENDING", "PROCESSING", "SUCCESS", "FAILED", "SKIPPED", "CONFIRMING",
]


def init_db(db_path: str) -> sqlite3.Connection:
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(CREATE_TASKS_TABLE)
    conn.execute(CREATE_SUBTITLES_TABLE)
    conn.execute(CREATE_DIMENSIONS_TABLE)
    for idx_sql in CREATE_TASKS_INDEXES:
        conn.execute(idx_sql)
    for idx_sql in CREATE_SUBTITLES_INDEXES:
        conn.execute(idx_sql)
    _migrate_schema(conn)
    _seed_dimensions(conn)
    conn.commit()
    return conn


def _migrate_schema(conn: sqlite3.Connection):
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "tasks" in tables:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        if "video_path" not in existing:
            conn.execute("ALTER TABLE tasks ADD COLUMN video_path TEXT DEFAULT ''")
        if "file_location" not in existing:
            conn.execute("ALTER TABLE tasks ADD COLUMN file_location TEXT DEFAULT 'source'")
            conn.execute("UPDATE tasks SET file_location='import' WHERE status='SUCCESS' AND import_success=1")
            conn.execute("UPDATE tasks SET file_location='deleted' WHERE status='SKIPPED'")
            conn.execute("UPDATE tasks SET file_location='quarantine' WHERE status='NEEDS_REVIEW'")
            conn.execute("UPDATE tasks SET file_location='temp' WHERE status='CONFIRMING'")
        else:
            source_count = conn.execute("SELECT COUNT(*) FROM tasks WHERE file_location='source' AND status='SUCCESS' AND import_success=1").fetchone()[0]
            if source_count > 0:
                conn.execute("UPDATE tasks SET file_location='import' WHERE file_location='source' AND status='SUCCESS' AND import_success=1")
                conn.execute("UPDATE tasks SET file_location='deleted' WHERE file_location='source' AND status='SKIPPED'")
                conn.execute("UPDATE tasks SET file_location='quarantine' WHERE file_location='source' AND status='NEEDS_REVIEW'")
                conn.execute("UPDATE tasks SET file_location='temp' WHERE file_location='source' AND status='CONFIRMING'")
        if "import_video_path" not in existing:
            conn.execute("ALTER TABLE tasks ADD COLUMN import_video_path TEXT DEFAULT ''")
        conn.execute("UPDATE tasks SET status='FAILED' WHERE status IN ('NEEDS_REVIEW', 'ROLLBACK')")
        conn.execute("UPDATE tasks SET status='SKIPPED' WHERE status='DUPLICATE_REVIEW'")
        conn.execute("UPDATE tasks SET file_location='quarantine' WHERE file_location='source' AND status='FAILED' AND import_success=0")
        conn.execute("UPDATE tasks SET file_location='quarantine' WHERE file_location='source' AND status='SKIPPED'")
    if "dimensions" in tables:
        dim_existing = {row[1] for row in conn.execute("PRAGMA table_info(dimensions)").fetchall()}
        if "default_value_list" not in dim_existing:
            conn.execute("ALTER TABLE dimensions ADD COLUMN default_value_list TEXT DEFAULT ''")
            for d in DEFAULT_DIMENSIONS:
                name = d['name']
                existing_row = conn.execute(
                    "SELECT default_value_list FROM dimensions WHERE name=?", (name,)
                ).fetchone()
                if existing_row and (not existing_row[0] or existing_row[0] == ''):
                    conn.execute(
                        "UPDATE dimensions SET default_value_list=? WHERE name=?",
                        (d['default_value_list'], name)
                    )
    if "task_subtitles" in tables:
        sub_existing = {row[1] for row in conn.execute("PRAGMA table_info(task_subtitles)").fetchall()}
        if "target_path" not in sub_existing:
            conn.execute("ALTER TABLE task_subtitles ADD COLUMN target_path TEXT DEFAULT ''")


def _row_to_dict(row) -> dict:
    if row is None:
        return None
    return dict(row)


def _rows_to_dicts(rows) -> list:
    return [dict(r) for r in rows]


def _seed_dimensions(conn: sqlite3.Connection):
    cur = conn.execute("SELECT COUNT(*) FROM dimensions")
    if cur.fetchone()[0] > 0:
        _migrate_dimensions(conn)
        return
    for dim in DEFAULT_DIMENSIONS:
        conn.execute(
            """INSERT INTO dimensions
               (name, label, source_type, sort_order, ai_prompt, tmdb_field,
                value_list, default_value_list, color, is_system, is_enabled,
                required_tier, description)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (dim["name"], dim["label"], dim["source_type"], dim["sort_order"],
             dim["ai_prompt"], dim["tmdb_field"], dim["value_list"],
             dim["default_value_list"], dim["color"], dim["is_system"],
             dim["is_enabled"], dim["required_tier"], dim["description"])
        )


def _migrate_dimensions(conn: sqlite3.Connection):
    _migrate_region(conn)
    _migrate_broad_genre(conn)
    _migrate_restricted_level(conn)
    _migrate_source_type(conn)


def _migrate_region(conn):
    row = conn.execute(
        "SELECT value_list FROM dimensions WHERE name='region'"
    ).fetchone()
    if not row:
        return

    try:
        vl = json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return

    if not vl or not isinstance(vl, list):
        return

    first_value = vl[0].get('value', '') if vl else ''
    if first_value in ('asia', 'western', 'european'):
        new_data = None
        for d in DEFAULT_DIMENSIONS:
            if d['name'] == 'region':
                new_data = d
                break
        if new_data:
            conn.execute(
                "UPDATE dimensions SET value_list=?, ai_prompt=?, description=? WHERE name='region'",
                (new_data['value_list'], new_data['ai_prompt'], new_data['description'])
            )
            conn.commit()
            logger.info("已迁移 region 维度数据：大类分组 → 具体国家")


def _migrate_broad_genre(conn):
    row = conn.execute(
        "SELECT value_list FROM dimensions WHERE name='broad_genre'"
    ).fetchone()
    if not row:
        return

    try:
        vl = json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return

    if not vl or not isinstance(vl, list):
        return

    old_keys = {'horror', 'scifi', 'action', 'drama'}
    needs_migrate = any(v.get('value') in old_keys for v in vl)
    if not needs_migrate:
        return

    new_data = None
    for d in DEFAULT_DIMENSIONS:
        if d['name'] == 'broad_genre':
            new_data = d
            break
    if new_data:
        conn.execute(
            "UPDATE dimensions SET value_list=?, ai_prompt=?, description=?, default_value_list=? WHERE name='broad_genre'",
            (new_data['value_list'], new_data['ai_prompt'], new_data['description'], new_data['default_value_list'])
        )
        conn.commit()
        logger.info("已迁移 broad_genre 维度数据：更新分类映射")


def _migrate_restricted_level(conn):
    row = conn.execute(
        "SELECT value_list, default_value_list FROM dimensions WHERE name='restricted_level'"
    ).fetchone()
    if not row:
        return

    needs_update = False
    new_value_list = row[0]
    new_default_value_list = row[1]

    for idx, raw in enumerate([new_value_list, new_default_value_list]):
        try:
            vl = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not vl or not isinstance(vl, list):
            continue
        has_old = any(v.get('value') == '13-15' for v in vl)
        if has_old:
            for v in vl:
                if v.get('value') == '13-15':
                    v['value'] = '13-16'
            needs_update = True
            if idx == 0:
                new_value_list = json.dumps(vl, ensure_ascii=False)
            else:
                new_default_value_list = json.dumps(vl, ensure_ascii=False)

    if not needs_update:
        return

    new_data = None
    for d in DEFAULT_DIMENSIONS:
        if d['name'] == 'restricted_level':
            new_data = d
            break

    if new_data:
        conn.execute(
            "UPDATE dimensions SET value_list=?, default_value_list=?, ai_prompt=? WHERE name='restricted_level'",
            (new_value_list, new_default_value_list, new_data['ai_prompt'])
        )
        conn.commit()
        logger.info("已迁移 restricted_level 维度数据：13-15 → 13-16")


def _migrate_source_type(conn):
    rows = conn.execute(
        "SELECT name, source_type FROM dimensions WHERE source_type IN ('tmdb', 'tmdb_ai')"
    ).fetchall()
    if not rows:
        return

    for row in rows:
        conn.execute(
            "UPDATE dimensions SET source_type='ai+tmdb' WHERE name=?",
            (row[0],)
        )
    conn.commit()
    logger.info(f"已迁移 {len(rows)} 个维度 source_type: tmdb/tmdb_ai → ai+tmdb")


def get_all_dimensions(conn: sqlite3.Connection) -> list:
    rows = conn.execute(
        "SELECT * FROM dimensions ORDER BY sort_order ASC"
    ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        if d.get('value_list'):
            try:
                d['value_list'] = json.loads(d['value_list'])
            except (json.JSONDecodeError, TypeError):
                d['value_list'] = []
        result.append(d)
    return result


def get_enabled_dimensions(conn: sqlite3.Connection) -> list:
    rows = conn.execute(
        "SELECT * FROM dimensions WHERE is_enabled=1 ORDER BY sort_order ASC"
    ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        if d.get('value_list'):
            try:
                d['value_list'] = json.loads(d['value_list'])
            except (json.JSONDecodeError, TypeError):
                d['value_list'] = []
        result.append(d)
    return result


def get_dimension(conn: sqlite3.Connection, name: str) -> dict:
    cur = conn.execute("SELECT * FROM dimensions WHERE name=?", (name,))
    row = cur.fetchone()
    if row is None:
        return None
    d = dict(row)
    if d.get('value_list'):
        try:
            d['value_list'] = json.loads(d['value_list'])
        except (json.JSONDecodeError, TypeError):
            d['value_list'] = []
    return d


def update_dimension(conn: sqlite3.Connection, name: str, **fields) -> dict:
    valid_columns = {
        "label", "ai_prompt", "tmdb_field", "value_list",
        "color", "description",
    }
    update_fields = {}
    for k, v in fields.items():
        if k in valid_columns:
            if k == "value_list" and isinstance(v, (dict, list)):
                update_fields[k] = json.dumps(v, ensure_ascii=False)
            else:
                update_fields[k] = v
    if not update_fields:
        return get_dimension(conn, name)
    set_clause = ", ".join(f"{k}=?" for k in update_fields)
    params = list(update_fields.values()) + [name]
    with _sqlite_conn_lock:
        conn.execute(f"UPDATE dimensions SET {set_clause} WHERE name=?", params)
        conn.commit()
    return get_dimension(conn, name)


def enable_dimension(conn: sqlite3.Connection, name: str) -> dict:
    with _sqlite_conn_lock:
        conn.execute("UPDATE dimensions SET is_enabled=1 WHERE name=?", (name,))
        conn.commit()
    return get_dimension(conn, name)


def disable_dimension(conn: sqlite3.Connection, name: str) -> dict:
    with _sqlite_conn_lock:
        conn.execute("UPDATE dimensions SET is_enabled=0 WHERE name=?", (name,))
        conn.commit()
    return get_dimension(conn, name)


def reset_dimension(conn: sqlite3.Connection, name: str) -> dict:
    row = conn.execute(
        "SELECT default_value_list, ai_prompt, description FROM dimensions WHERE name=?",
        (name,)
    ).fetchone()
    if row is None:
        return None
    default_vl = row['default_value_list']
    if not default_vl or default_vl.strip() == '':
        for d in DEFAULT_DIMENSIONS:
            if d['name'] == name:
                default_vl = d.get('value_list', '[]')
                break
    if not default_vl or default_vl.strip() == '':
        return None
    with _sqlite_conn_lock:
        conn.execute(
            "UPDATE dimensions SET value_list=?, ai_prompt=?, description=? WHERE name=?",
            (default_vl, row['ai_prompt'] or '', row['description'] or '', name)
        )
        conn.commit()
    return get_dimension(conn, name)


def create_task(conn: sqlite3.Connection, source_path: str, source_filename: str,
                file_size_mb: float = 0, task_id: str = None) -> dict:
    import uuid
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
    if row:
        subs = get_subtitles_by_task(conn, task_id)
        row['subtitle_files'] = [s.get('target_path', '') or s.get('source_path', '')
                                  for s in subs]
        row['subtitle_source_files'] = [s.get('source_path', '') for s in subs]
        row['subtitle_total'] = len(subs)
        row['subtitle_success'] = sum(1 for s in subs if s.get('status') == 'SUCCESS')
    return row


def find_by_source_path(conn: sqlite3.Connection, source_path: str) -> dict:
    cur = conn.execute(
        "SELECT * FROM tasks WHERE source_path=? ORDER BY created_at DESC LIMIT 1",
        (source_path,)
    )
    return _row_to_dict(cur.fetchone())


def find_by_source_filename(conn: sqlite3.Connection, source_filename: str
                            ) -> list:
    cur = conn.execute(
        "SELECT * FROM tasks WHERE source_filename=? ORDER BY created_at DESC",
        (source_filename,)
    )
    return _rows_to_dicts(cur.fetchall())


def list_tasks(conn: sqlite3.Connection, page: int = 1, page_size: int = 20,
               status: str = None) -> tuple:
    offset = (page - 1) * page_size
    conditions = []
    params = []
    if status:
        status = status.strip().upper()
    if status and status != "ALL" and status in VALID_STATUSES:
        conditions.append("status=?")
        params.append(status)
    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    count_sql = "SELECT COUNT(*) FROM tasks" + where_clause
    total = conn.execute(count_sql, params).fetchone()[0]
    data_sql = ("SELECT t.task_id, t.source_path, t.source_filename, t.status, "
                "t.percentage, t.file_size_mb, t.retry_count, "
                "t.scrape_title_cn, t.scrape_title_en, t.scrape_year, "
                "t.scrape_media_type, t.scrape_season, t.scrape_episode, "
                "t.scrape_confidence, t.import_path, t.final_filename, "
                "t.skip_reason, t.error_message, t.import_success, "
                "t.confirm_status, t.video_path, t.file_location, "
                "t.import_video_path, "
                "t.created_at, t.started_at, t.completed_at, "
                "(SELECT COUNT(*) FROM task_subtitles ts WHERE ts.task_id=t.task_id) AS subtitle_total, "
                "(SELECT COUNT(*) FROM task_subtitles ts WHERE ts.task_id=t.task_id AND ts.status='SUCCESS') AS subtitle_success "
                "FROM tasks t" + where_clause +
                " ORDER BY t.created_at DESC LIMIT ? OFFSET ?")
    rows = _rows_to_dicts(
        conn.execute(data_sql, params + [page_size, offset]).fetchall()
    )
    total_pages = max(1, (total + page_size - 1) // page_size)
    return rows, total, total_pages


def update_task(conn: sqlite3.Connection, task_id: str, **fields) -> dict:
    valid_columns = {
        "source_path", "source_filename", "file_size_mb", "status",
        "retry_count", "created_at", "started_at", "completed_at",
        "last_seen_at", "current_step", "total_steps", "step_name",
        "percentage", "bytes_copied", "total_bytes",
        "scrape_result", "scrape_title_cn", "scrape_title_en",
        "scrape_year", "scrape_media_type", "scrape_season",
        "scrape_episode", "scrape_dimensions", "scrape_confidence",
        "classify_result", "import_path", "final_filename",
        "dedup_result", "dedup_existing_file", "import_video_path",
        "video_path", "file_location", "import_success", "confirm_status", "confirmed_at",
        "skip_reason", "error_code", "error_message",
    }
    update_fields = {}
    for k, v in fields.items():
        if k in valid_columns:
            if k in ("scrape_result", "scrape_dimensions", "dedup_result"):
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
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status"
    ).fetchall()
    for row in rows:
        s = row["status"]
        if s in counts:
            counts[s] = row["cnt"]
    return counts


def delete_task(conn: sqlite3.Connection, task_id: str) -> bool:
    with _sqlite_conn_lock:
        conn.execute("DELETE FROM task_subtitles WHERE task_id=?", (task_id,))
        conn.execute("DELETE FROM tasks WHERE task_id=?", (task_id,))
        conn.commit()
    return True


def clear_tasks(conn: sqlite3.Connection, status: str = None) -> int:
    with _sqlite_conn_lock:
        if status and status in VALID_STATUSES:
            cur = conn.execute(
                "SELECT task_id FROM tasks WHERE status=?", (status,)
            )
            tids = [row["task_id"] for row in cur.fetchall()]
            conn.execute("DELETE FROM task_subtitles WHERE task_id IN ({})".format(
                ",".join("?" * len(tids))), tids)
            conn.execute("DELETE FROM tasks WHERE status=?", (status,))
        else:
            conn.execute("DELETE FROM task_subtitles")
            conn.execute("DELETE FROM tasks")
        conn.commit()
        return conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]


def has_running_tasks(conn: sqlite3.Connection) -> bool:
    cur = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE status IN ('PROCESSING')"
    )
    return cur.fetchone()[0] > 0


def count_by_specific_status(conn: sqlite3.Connection, status: str) -> int:
    cur = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE status=?", (status,)
    )
    return cur.fetchone()[0]


def find_failed_too_many(conn: sqlite3.Connection, max_retries: int) -> list:
    rows = conn.execute(
        "SELECT * FROM tasks WHERE status='FAILED' AND retry_count>=?",
        (max_retries,)
    ).fetchall()
    return _rows_to_dicts(rows)


def get_next_pending(conn: sqlite3.Connection) -> dict:
    cur = conn.execute(
        "SELECT task_id FROM tasks WHERE status='PENDING' ORDER BY created_at ASC LIMIT 1"
    )
    row = cur.fetchone()
    if row is None:
        return None
    return get_task(conn, row["task_id"])


def list_all_tasks(conn: sqlite3.Connection, limit: int = 500) -> list:
    rows = conn.execute(
        "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return _rows_to_dicts(rows)


def count_all_tasks(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]


def create_subtitles(conn: sqlite3.Connection, task_id: str,
                     subtitle_paths: list, target_paths: list = None) -> list:
    now = datetime.now().isoformat()
    inserted = []
    tpaths = target_paths or []
    for i, sp in enumerate(subtitle_paths):
        filename = os.path.basename(sp)
        tp = tpaths[i] if i < len(tpaths) else ""
        with _sqlite_conn_lock:
            cur = conn.execute(
                """INSERT INTO task_subtitles
                   (task_id, source_path, source_filename, target_path, status, created_at)
                   VALUES (?, ?, ?, ?, 'PENDING', ?)""",
                (task_id, sp, filename, tp, now)
            )
            inserted.append({
                "id": cur.lastrowid,
                "task_id": task_id,
                "source_path": sp,
                "source_filename": filename,
                "target_path": tp,
                "status": "PENDING",
            })
        conn.commit()
    return inserted


def get_subtitles_by_task(conn: sqlite3.Connection, task_id: str) -> list:
    rows = conn.execute(
        "SELECT * FROM task_subtitles WHERE task_id=? ORDER BY id ASC",
        (task_id,)
    ).fetchall()
    return _rows_to_dicts(rows)


def update_subtitle(conn: sqlite3.Connection, subtitle_id: int, **fields) -> dict:
    valid_columns = {
        "lang", "status", "import_path", "confirm_status",
        "error_message", "completed_at", "target_path", "source_path",
    }
    update_fields = {k: v for k, v in fields.items() if k in valid_columns}
    if not update_fields:
        cur = conn.execute(
            "SELECT * FROM task_subtitles WHERE id=?", (subtitle_id,)
        )
        return _row_to_dict(cur.fetchone())
    set_clause = ", ".join(f"{k}=?" for k in update_fields)
    params = list(update_fields.values()) + [subtitle_id]
    with _sqlite_conn_lock:
        conn.execute(
            f"UPDATE task_subtitles SET {set_clause} WHERE id=?",
            params
        )
        conn.commit()
    cur = conn.execute(
        "SELECT * FROM task_subtitles WHERE id=?", (subtitle_id,)
    )
    return _row_to_dict(cur.fetchone())


def update_subtitles_by_task(conn: sqlite3.Connection, task_id: str,
                              **fields) -> int:
    valid_columns = {
        "status", "import_path", "confirm_status", "completed_at",
        "target_path",
    }
    update_fields = {k: v for k, v in fields.items() if k in valid_columns}
    if not update_fields:
        return 0
    set_clause = ", ".join(f"{k}=?" for k in update_fields)
    params = list(update_fields.values()) + [task_id]
    with _sqlite_conn_lock:
        conn.execute(
            f"UPDATE task_subtitles SET {set_clause} WHERE task_id=?",
            params
        )
        conn.commit()
    return conn.total_changes


def count_subtitles_by_task(conn: sqlite3.Connection, task_id: str) -> tuple:
    total = conn.execute(
        "SELECT COUNT(*) FROM task_subtitles WHERE task_id=?", (task_id,)
    ).fetchone()[0]
    success = conn.execute(
        "SELECT COUNT(*) FROM task_subtitles WHERE task_id=? AND status='SUCCESS'",
        (task_id,)
    ).fetchone()[0]
    return total, success