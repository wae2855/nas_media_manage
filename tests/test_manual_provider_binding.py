import sqlite3
from types import SimpleNamespace

from media_importer.core.db.connection import init_db
from media_importer.core.db.constants import CREATE_TASKS_TABLE
from media_importer.features.import_flow.services.naming import apply_filename_template
from media_importer.features.import_flow.steps.scrape import ScrapeStepsMixin


class BindingHarness(ScrapeStepsMixin):
    def __init__(self):
        self.config = {}
        self.task_manager = SimpleNamespace(conn=object())
        self.logs = []

    def _log(self, level, message, task=None, step=""):
        self.logs.append((level, message, step))

    def _update_progress(self, *_args, **_kwargs):
        return None


def test_existing_database_adds_manual_provider_binding_column(tmp_path):
    db_path = tmp_path / "tasks.db"
    legacy_schema = CREATE_TASKS_TABLE.replace(
        "    manual_provider_binding TEXT DEFAULT '{}',\n",
        "",
    )
    legacy = sqlite3.connect(db_path)
    legacy.execute(legacy_schema)
    legacy.close()

    conn = init_db(str(db_path))
    columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
    conn.close()

    assert "manual_provider_binding" in columns


def test_manual_binding_loads_exact_provider_and_preserves_episode(monkeypatch):
    calls = []

    def fake_load(*args, **kwargs):
        calls.append(kwargs)
        return {
            "language": "zh-CN",
            "dimensions": {"media_type": "tv", "genre": "剧情"},
            "dim_sources": {
                "media_type": "provider:tmdb",
                "genre": "provider:tmdb",
            },
            "scrape_result": {
                "title_cn": "北海鲸梦",
                "title_en": "The North Water",
                "year": 2021,
                "media_type": "tv",
                "provider_type": "tmdb",
                "provider_id": "86941",
                "poster_url": "",
                "scrape_trace": {"dimension_mapping_evidence": {}},
            },
        }

    monkeypatch.setattr(
        "media_importer.features.tasks.search_service.load_provider_candidate",
        fake_load,
    )
    task = {
        "task_id": "north-water-5",
        "source_filename": "北海鲸梦.S01E05.mkv",
        "manual_provider_binding": {
            "provider_type": "tmdb",
            "item_id": "86941",
            "media_type": "tv",
            "language": "zh-CN",
            "season": 1,
            "episode": 5,
        },
    }

    result = BindingHarness()._load_manual_provider_binding(task)

    assert len(calls) == 1
    assert calls[0]["item_id"] == "86941"
    assert result["match_level"] == "AUTO_PASS"
    assert result["provider_id"] == "86941"
    assert result["season"] == 1
    assert result["episode"] == 5
    assert result["dimensions"]["season"] == 1
    assert result["dimensions"]["episode"] == 5
    assert task["_manual_binding_consumed"] is True


def test_manual_movie_binding_keeps_movie_provider_type(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "media_importer.features.tasks.search_service.load_provider_candidate",
        lambda *args, **kwargs: calls.append(kwargs) or {
            "scrape_result": {"title_cn": "沙丘", "year": 2021},
            "dimensions": {"media_type": "movie"},
            "dim_sources": {},
        },
    )
    task = {
        "task_id": "dune",
        "source_filename": "Dune.2021.mkv",
        "manual_provider_binding": {
            "provider_type": "tmdb",
            "item_id": "438631",
            "media_type": "movie",
            "language": "zh-CN",
            "season": None,
            "episode": None,
        },
    }

    result = BindingHarness()._load_manual_provider_binding(task)

    assert calls[0]["media_type"] == "movie"
    assert result["media_type"] == "movie"
    assert "season" not in result
    assert "episode" not in result


def test_cached_series_dimensions_never_copy_another_episode(monkeypatch):
    harness = BindingHarness()
    monkeypatch.setattr(
        "media_importer.features.import_flow.steps.scrape.db_list_all_tasks",
        lambda *args, **kwargs: [{
            "task_id": "north-water-4",
            "status": "SUCCESS",
            "scrape_result": {
                "title_cn": "北海鲸梦",
                "dimensions": {
                    "media_type": "tv",
                    "genre": "剧情",
                    "season": 1,
                    "episode": 4,
                },
            },
        }],
    )

    dimensions = harness._find_cached_series_dims(
        {"task_id": "north-water-5"},
        {"title_cn": "北海鲸梦"},
    )

    assert dimensions == {"media_type": "tv", "genre": "剧情"}


def test_bound_episode_scrape_clears_intent_and_generates_standard_episode_name(
    monkeypatch,
):
    harness = BindingHarness()
    task = {
        "task_id": "north-water-5",
        "status": "PENDING",
        "stage": "RUNNING",
        "source_path": "/source/北海鲸梦.S01E05.release-group.mkv",
        "source_filename": "北海鲸梦.S01E05.release-group.mkv",
        "subtitle_files": [],
        "manual_provider_binding": {
            "provider_type": "tmdb",
            "item_id": "86941",
            "media_type": "tv",
            "language": "zh-CN",
            "season": 1,
            "episode": 5,
        },
    }
    writes = []

    monkeypatch.setattr(
        "media_importer.features.tasks.search_service.load_provider_candidate",
        lambda *args, **kwargs: {
            "language": "zh-CN",
            "dimensions": {"media_type": "tv", "resolution_tier": "1080P"},
            "dim_sources": {},
            "scrape_result": {
                "title_cn": "北海鲸梦",
                "title_en": "The North Water",
                "year": 2021,
                "media_type": "tv",
                "provider_type": "tmdb",
                "provider_id": "86941",
                "poster_url": "",
            },
        },
    )
    monkeypatch.setattr(
        "media_importer.features.scraping.get_dimensions_for_file",
        lambda conn: [],
    )
    monkeypatch.setattr(
        "media_importer.features.import_flow.steps.scrape.get_enabled_dimensions",
        lambda conn: [],
    )
    monkeypatch.setattr(
        "media_importer.features.scraping.dimension_resolution.resolve_dimension_sources",
        lambda **kwargs: SimpleNamespace(dim_sources={}),
    )
    monkeypatch.setattr(
        "media_importer.features.import_flow.steps.scrape.db_update_task",
        lambda conn, task_id, **fields: writes.append(fields),
    )

    harness._step_scrape(task)
    harness._step_validate(task)
    final_name = apply_filename_template(
        task["scrape_result"],
        "{title_cn}.{title_en}.{year}.S{season:02d}E{episode:02d}.{resolution}.{ext}",
        ".mkv",
    )

    assert writes[-1]["manual_provider_binding"] == {}
    assert task["scrape_result"]["provider_id"] == "86941"
    assert task["scrape_result"]["episode"] == 5
    assert task.get("_needs_confirm") is not True
    assert final_name == "北海鲸梦.The North Water.2021.S01E05.1080P.mkv"
