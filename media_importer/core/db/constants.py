import json
from pathlib import Path

_MAPPING_PRESET_PATH = (
    Path(__file__).parents[2]
    / "features/scraping/data/provider_dimension_mappings.v2.json"
)
_MAPPING_PRESETS = json.loads(_MAPPING_PRESET_PATH.read_text(encoding="utf-8"))


def _mapping_json(dimension_name: str) -> str:
    mappings = (
        _MAPPING_PRESETS.get("dimensions", {})
        .get(dimension_name, {})
        .get("providers", {})
    )
    return json.dumps(mappings, ensure_ascii=False, sort_keys=True) if mappings else ""

CREATE_TASKS_TABLE = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT UNIQUE NOT NULL,
    source_path TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    file_size_mb REAL DEFAULT 0,
    status TEXT DEFAULT 'PENDING',
    stage TEXT DEFAULT 'QUEUED',
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
    progress_item_name TEXT DEFAULT '',
    progress_item_kind TEXT DEFAULT '',
    progress_item_index INTEGER DEFAULT 0,
    progress_item_total INTEGER DEFAULT 0,
    scrape_result TEXT DEFAULT '{}',
    scrape_title_cn TEXT,
    scrape_title_en TEXT,
    scrape_year TEXT,
    scrape_media_type TEXT,
    scrape_season INTEGER,
    scrape_episode INTEGER,
    scrape_dimensions TEXT DEFAULT '{}',
    match_level TEXT DEFAULT NULL,
    match_concerns TEXT DEFAULT NULL,
    match_trace TEXT DEFAULT NULL,
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
    error_message TEXT DEFAULT '',
    scrape_trace TEXT DEFAULT '',
    dim_sources TEXT DEFAULT NULL,
    provider_type TEXT DEFAULT '',
    provider_id TEXT DEFAULT '',
    source_fingerprint TEXT DEFAULT '',
    source_file_size INTEGER DEFAULT 0,
    source_mtime TEXT DEFAULT '',
    thumbnail_path TEXT DEFAULT '',
    confirmed_override INTEGER DEFAULT 0,
    confirmed_title TEXT DEFAULT '',
    override_source TEXT DEFAULT ''
    ,source_unit_id TEXT DEFAULT ''
    ,source_cleanup_status TEXT DEFAULT ''
    ,bundle_state TEXT DEFAULT ''
    ,bundle_manifest TEXT DEFAULT '[]'
    ,bundle_committed INTEGER DEFAULT 0
    ,task_kind TEXT DEFAULT 'IMPORT'
    ,parent_task_id TEXT DEFAULT ''
    ,used_fallback INTEGER DEFAULT 0
    ,organization_status TEXT DEFAULT ''
    ,reorganized_by_task_id TEXT DEFAULT ''
    ,cancel_requested INTEGER DEFAULT 0
    ,stop_requested_at TEXT DEFAULT ''
    ,requested_source_disposition TEXT DEFAULT ''
    ,outcome_code TEXT DEFAULT ''
    ,source_disposition TEXT DEFAULT ''
    ,source_disposition_message TEXT DEFAULT ''
)
"""

CREATE_SOURCE_UNITS_TABLE = """
CREATE TABLE IF NOT EXISTS source_units (
    unit_id TEXT PRIMARY KEY,
    source_root TEXT NOT NULL,
    unit_path TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('folder', 'loose_root')),
    snapshot_json TEXT NOT NULL DEFAULT '[]',
    state TEXT NOT NULL DEFAULT 'DISCOVERED',
    cleanup_status TEXT NOT NULL DEFAULT 'WAITING',
    last_error TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

CREATE_SOURCE_UNITS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_source_units_state ON source_units(state)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_source_unit_id ON tasks(source_unit_id)",
]

CREATE_SUBTITLES_TABLE = """
CREATE TABLE IF NOT EXISTS task_subtitles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    member_id TEXT DEFAULT '',
    source_size INTEGER DEFAULT 0,
    source_mtime_ns INTEGER DEFAULT 0,
    source_fingerprint TEXT DEFAULT '',
    planned_filename TEXT DEFAULT '',
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
    "CREATE INDEX IF NOT EXISTS idx_tasks_fingerprint ON tasks(source_fingerprint)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_parent_task_id ON tasks(parent_task_id)",
]

CREATE_SUBTITLES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_subtitles_task_id ON task_subtitles(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_subtitles_source_path ON task_subtitles(source_path)",
]

CREATE_RECYCLE_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS recycle_items (
    item_id TEXT PRIMARY KEY,
    recycle_path TEXT UNIQUE NOT NULL,
    original_path TEXT NOT NULL,
    metadata_path TEXT NOT NULL,
    source_zone TEXT DEFAULT 'other',
    reason TEXT DEFAULT '',
    task_id TEXT DEFAULT '',
    moved_at TEXT NOT NULL,
    is_dir INTEGER NOT NULL DEFAULT 0,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK(status IN ('ACTIVE', 'RESTORED', 'DELETED')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_RECYCLE_ITEMS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_recycle_items_status_moved "
    "ON recycle_items(status, moved_at DESC)",
]

CREATE_DIMENSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS dimensions (
    name TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'provider',
    sort_order INTEGER DEFAULT 0,
    ai_prompt TEXT,
    tmdb_field TEXT,
    provider_mappings TEXT DEFAULT '',
    default_provider_mappings TEXT DEFAULT '',
    value_list TEXT NOT NULL,
    default_value_list TEXT DEFAULT '',
    color TEXT DEFAULT '#6c757d',
    is_system INTEGER DEFAULT 1,
    is_enabled INTEGER DEFAULT 0,
    trust_ai_assist INTEGER NOT NULL DEFAULT 1,
    trust_ai_search INTEGER NOT NULL DEFAULT 0,
    required_tier TEXT DEFAULT 'free',
    description TEXT DEFAULT ''
)
"""

DEFAULT_DIMENSIONS = [
    {
        "name": "media_type",
        "label": "影视类型",
        "source_type": "provider",
        "sort_order": 1,
        "ai_prompt": "请判断这是电影（movie）还是电视剧（tv）。判断依据：如果文件名中包含季集编号（如S01E01、S2E03等格式），则为电视剧（tv）；如果是完整独立的影视故事，则为电影（movie）。电视电影/网络电影仍归为movie。",
        "tmdb_field": "",
        "provider_mappings": "",
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
        "trust_ai_assist": 1,
        "trust_ai_search": 1,
        "required_tier": "free",
        "description": "区分电影和电视剧，决定目录结构形态"
    },
    {
        "name": "documentary",
        "label": "是否纪录片",
        "source_type": "provider",
        "sort_order": 2,
        "ai_prompt": "请判断是否为纪录片（true/false）。纪录片是以真实事件、人物、历史、社会等为主题的非虚构影视作品，包括自然纪录片（如《地球脉动》）、历史纪录片、社会纪录片、科学纪录片等。TMDB genres 包含 Documentary (id=99) 则为 true；如 TMDB 未标注，请根据标题和简介判断。真人出演+虚构剧情的作品（如《辛德勒的名单》）应选 false。",
        "tmdb_field": "genres",
        "provider_mappings": _mapping_json("documentary"),
        "default_provider_mappings": _mapping_json("documentary"),
        "value_list": json.dumps([
            {"value": "true", "label": "是", "tmdb_genre_ids": [99]},
            {"value": "false", "label": "否"}
        ], ensure_ascii=False),
        "default_value_list": json.dumps([
            {"value": "true", "label": "是", "tmdb_genre_ids": [99]},
            {"value": "false", "label": "否"}
        ], ensure_ascii=False),
        "color": "#f59e0b",
        "is_system": 1,
        "is_enabled": 1,
        "trust_ai_assist": 1,
        "trust_ai_search": 0,
        "required_tier": "free",
        "description": "将纪录片从虚构作品中分离"
    },
    {
        "name": "restricted_level",
        "label": "观看分级",
        "source_type": "provider",
        "sort_order": 3,
        "ai_prompt": "请判断该影视内容的官方观看年龄分级。17+ 只表示限制观看，不等同于成人或露骨内容；成人电影标记由独立维度表达。优先使用 Provider 提供的国家/地区官方分级，缺失时进入人工确认。",
        "tmdb_field": "release_dates",
        "provider_mappings": _mapping_json("restricted_level"),
        "default_provider_mappings": _mapping_json("restricted_level"),
        "value_list": json.dumps([
            {"value": "0-6", "label": "幼儿/儿童"},
            {"value": "7-12", "label": "家庭向"},
            {"value": "13-16", "label": "青少年向"},
            {"value": "17+", "label": "限制观看"}
        ], ensure_ascii=False),
        "default_value_list": json.dumps([
            {"value": "0-6", "label": "幼儿/儿童"},
            {"value": "7-12", "label": "家庭向"},
            {"value": "13-16", "label": "青少年向"},
            {"value": "17+", "label": "限制观看"}
        ], ensure_ascii=False),
        "color": "#ec4899",
        "is_system": 1,
        "is_enabled": 1,
        "trust_ai_assist": 1,
        "trust_ai_search": 0,
        "required_tier": "free",
        "description": "按国家/地区的官方年龄分级分类，不代表成人电影标记"
    },
    {
        "name": "content_sensitivity",
        "label": "成人电影标记",
        "source_type": "provider",
        "sort_order": 4,
        "ai_prompt": "仅根据 Provider 的明确成人标记判断是否为成人电影。没有明确证据时不要猜测，保留为待确认。",
        "tmdb_field": "adult",
        "provider_mappings": _mapping_json("content_sensitivity"),
        "default_provider_mappings": _mapping_json("content_sensitivity"),
        "value_list": json.dumps([
            {"value": "normal", "label": "否"},
            {"value": "adult", "label": "是"}
        ], ensure_ascii=False),
        "default_value_list": json.dumps([
            {"value": "normal", "label": "否"},
            {"value": "adult", "label": "是"}
        ], ensure_ascii=False),
        "color": "#ef4444",
        "is_system": 1,
        "is_enabled": 0,
        "trust_ai_assist": 0,
        "trust_ai_search": 0,
        "required_tier": "free",
        "description": "仅在 Provider 有明确证据时标记成人电影"
    },
    {
        "name": "animation",
        "label": "是否动漫",
        "source_type": "provider",
        "sort_order": 4,
        "ai_prompt": "请判断是否为动漫/动画作品（true/false）。判断标准：以动画/手绘/CG形式制作的作品均为 true，包括日本动画（日漫）、中国动画（国漫）、欧美动画电影、动画短片等。TMDB genres 包含 Animation (id=16) 则为 true。真人拍摄+少量CG特效的作品（如漫威电影）不算动画，应选 false。",
        "tmdb_field": "genres",
        "provider_mappings": _mapping_json("animation"),
        "default_provider_mappings": _mapping_json("animation"),
        "value_list": json.dumps([
            {"value": "true", "label": "是", "tmdb_genre_ids": [16]},
            {"value": "false", "label": "否"}
        ], ensure_ascii=False),
        "default_value_list": json.dumps([
            {"value": "true", "label": "是", "tmdb_genre_ids": [16]},
            {"value": "false", "label": "否"}
        ], ensure_ascii=False),
        "color": "#8b5cf6",
        "is_system": 1,
        "is_enabled": 0,
        "trust_ai_assist": 1,
        "trust_ai_search": 0,
        "required_tier": "free",
        "description": "将动漫/动画从真人作品中分离"
    },
    {
        "name": "region",
        "label": "地区",
        "source_type": "provider",
        "sort_order": 5,
        "ai_prompt": "请判断该影视作品的主要制片国家或地区，从以下选项中选择：us（美国）、cn（中国大陆）、hk（中国香港）、tw（中国台湾）、jp（日本）、kr（韩国）、gb（英国）、fr（法国）、de（德国）、it（意大利）、es（西班牙）、in（印度）、other（其他）。判断依据：优先看制作公司/出品方所在国家，其次看主要创作团队国籍和语言。合拍片选择投资占比最大或主创团队所属的国家。如不确定，请联网搜索该作品的制片信息。",
        "tmdb_field": "origin_country",
        "provider_mappings": _mapping_json("region"),
        "default_provider_mappings": _mapping_json("region"),
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
        "trust_ai_assist": 1,
        "trust_ai_search": 0,
        "required_tier": "pro",
        "description": "按制片国家/地区分拣"
    },
    {
        "name": "origin_lang",
        "label": "原始语言",
        "source_type": "provider",
        "sort_order": 6,
        "ai_prompt": "请判断该影视作品的原始语言，从以下选项中选择：zh（中文）、en（英语）、ja（日语）、ko（韩语）、other（其他语言）。判断依据：原始语言是作品最初制作时使用的语言，不是配音或翻译后的语言。例如日本动漫的原始语言是ja，即使有中文配音版也选ja。",
        "tmdb_field": "original_language",
        "provider_mappings": _mapping_json("origin_lang"),
        "default_provider_mappings": _mapping_json("origin_lang"),
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
        "trust_ai_assist": 1,
        "trust_ai_search": 0,
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
        "provider_mappings": "",
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
        "trust_ai_assist": 1,
        "trust_ai_search": 0,
        "required_tier": "pro",
        "description": "按视频分辨率分拣（4K/1080P/720P）"
    },
    {
        "name": "broad_genre",
        "label": "题材类型",
        "source_type": "provider",
        "sort_order": 8,
        "ai_prompt": "请判断该影视作品的主要类型，从以下选项中选择风格最鲜明突出的一个：horror_mystery（恐怖/悬疑：以恐惧、惊悚、推理为核心，如恐怖片、悬疑片、惊悚片）、scifi_fantasy（科幻/奇幻：以未来科技或奇幻世界观为背景，如太空歌剧、超级英雄、魔幻）、war（战争/军事：以战争或军事行动为核心题材）、action_adventure（动作/冒险：以动作场面或冒险旅程为核心，如功夫片、探险片）、comedy（喜剧：以幽默搞笑为核心，如爆笑喜剧、黑色幽默）、drama_romance（剧情/情感：以人物情感或社会现实为核心，如文艺片、爱情片、犯罪剧情片）、documentary（纪录/纪实：非虚构纪实作品）、music（音乐/演出：以音乐或演出为核心，如演唱会电影、音乐传记）、kids（儿童/家庭：面向低龄观众的儿童节目）、tv_show（电视节目：综艺、脱口秀、真人秀等非虚构电视节目）、other（其他：不属于以上任何类型）。如果同时属于多个类型，选择风格最突出、最能代表该作品核心特征的那个。",
        "tmdb_field": "genres",
        "provider_mappings": _mapping_json("broad_genre"),
        "default_provider_mappings": _mapping_json("broad_genre"),
        "value_list": json.dumps([
            {"value": "horror_mystery", "label": "恐怖/悬疑", "tmdb_genre_ids": [27, 9648, 53, 10758], "priority": 1},
            {"value": "scifi_fantasy", "label": "科幻/奇幻", "tmdb_genre_ids": [878, 14, 10765], "priority": 2},
            {"value": "war", "label": "战争/军事", "tmdb_genre_ids": [10752, 10768], "priority": 3},
            {"value": "action_adventure", "label": "动作/冒险", "tmdb_genre_ids": [28, 12, 10759, 37], "priority": 4},
            {"value": "comedy", "label": "喜剧", "tmdb_genre_ids": [35], "priority": 5},
            {"value": "drama_romance", "label": "剧情/情感", "tmdb_genre_ids": [18, 10749, 80, 36, 10751, 10766, 10770], "priority": 6},
            {"value": "documentary", "label": "纪录/纪实", "tmdb_genre_ids": [99], "priority": 7},
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
            {"value": "documentary", "label": "纪录/纪实", "tmdb_genre_ids": [99], "priority": 7},
            {"value": "music", "label": "音乐/演出", "tmdb_genre_ids": [10402], "priority": 8},
            {"value": "kids", "label": "儿童/家庭", "tmdb_genre_ids": [10762], "priority": 9},
            {"value": "tv_show", "label": "电视节目", "tmdb_genre_ids": [10763, 10764, 10767], "priority": 10},
            {"value": "other", "label": "其他", "tmdb_genre_ids": [], "priority": 11}
        ], ensure_ascii=False),
        "color": "#ef4444",
        "is_system": 1,
        "is_enabled": 0,
        "trust_ai_assist": 1,
        "trust_ai_search": 0,
        "required_tier": "premium",
        "description": "按影视类型分拣（恐怖/科幻/战争/喜剧/动作/剧情等）"
    },
]

VALID_STATUSES = [
    "PENDING", "SUCCESS", "FAILED", "SKIPPED", "CANCELLED",
]
