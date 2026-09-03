"""P1 预览/搜索服务单元测试。

覆盖：
- preview_task: 元数据/维度/文件名更新 + 分类重算 + 不入库
- search_provider_candidates: 候选搜索 + 边界场景
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch

# ============================================================================
# preview_task 测试（真实 SQLite + TaskManager + Mock ClassificationService）
# ============================================================================


class TestPreviewTask(unittest.TestCase):
    """preview_task 的单元测试。"""

    @classmethod
    def setUpClass(cls):
        cls.data_dir = tempfile.mkdtemp(prefix="nas_test_")

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

        from media_importer.core.task_manager import TaskManager

        self.task_manager = TaskManager(self.data_dir, config={})
        self.task_manager.conn = self.conn

        self._seed_dimensions()
        self._seed_task()

        self.pipeline = _PreviewPipeline(self.task_manager, {})

    def tearDown(self):
        self.conn.close()

    def _create_tables(self):
        from media_importer.core.db.constants import (
            CREATE_DIMENSIONS_TABLE,
            CREATE_TASKS_TABLE,
        )

        self.conn.execute(CREATE_TASKS_TABLE)
        self.conn.execute("CREATE TABLE IF NOT EXISTS task_subtitles ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, "
            "source_path TEXT NOT NULL, source_filename TEXT NOT NULL, "
            "target_path TEXT DEFAULT '', lang TEXT DEFAULT '', "
            "status TEXT DEFAULT 'PENDING', import_path TEXT DEFAULT '', "
            "confirm_status TEXT DEFAULT 'NONE', error_message TEXT DEFAULT '', "
            "created_at TEXT, completed_at TEXT)")
        self.conn.execute(CREATE_DIMENSIONS_TABLE)
        self.conn.commit()

    def _seed_dimensions(self):
        self.conn.execute(
            "INSERT INTO dimensions (name, label, source_type, value_list, "
            "is_enabled, trust_ai_assist, trust_ai_search) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "media_type", "影视类型", "ai+provider",
                json.dumps([{"value": "movie", "label": "电影"}, {"value": "tv", "label": "电视剧"}]),
                1, 1, 1,
            ),
        )
        self.conn.commit()

    def _seed_task(self):
        scrape_result = json.dumps({
            "title_cn": "阿凡达",
            "title_en": "Avatar",
            "year": 2009,
            "media_type": "movie",
            "match_level": "NEEDS_CONFIRM",
            "clean_result": {"clean_title": "阿凡达", "year": 2009},
        })
        dims = json.dumps({"media_type": "movie"})
        self.conn.execute(
            "INSERT INTO tasks (task_id, source_path, source_filename, "
            "status, stage, scrape_result, scrape_dimensions, "
            "scrape_title_cn, scrape_title_en, scrape_year, video_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("task-test-1", "/src/Avatar.2009.mkv", "Avatar.2009.mkv",
             "PENDING", "AWAIT_REVIEW", scrape_result, dims,
             "阿凡达", "Avatar", "2009", "/tmp/Avatar.2009.mkv"),
        )
        self.conn.commit()

    # --- 正向测试 ---

    def test_preview_updates_title_cn(self):
        task = self.pipeline.preview_task("task-test-1", {"title_cn": "阿凡达2"})

        self.assertEqual(task["scrape_title_cn"], "阿凡达2")
        sr = task["scrape_result"]
        if isinstance(sr, str):
            sr = json.loads(sr)
        self.assertEqual(sr["title_cn"], "阿凡达2")

    def test_preview_updates_title_en(self):
        task = self.pipeline.preview_task("task-test-1", {"title_en": "Avatar 2"})

        self.assertEqual(task["scrape_title_en"], "Avatar 2")

    def test_preview_updates_year(self):
        task = self.pipeline.preview_task("task-test-1", {"year": 2022})

        self.assertEqual(task["scrape_year"], "2022")

    def test_preview_updates_dimensions(self):
        task = self.pipeline.preview_task(
            "task-test-1", {"dimensions": {"media_type": "tv"}}
        )

        dims = task["scrape_dimensions"]
        if isinstance(dims, str):
            dims = json.loads(dims)
        self.assertEqual(dims["media_type"], "tv")

    def test_preview_updates_filename(self):
        task = self.pipeline.preview_task(
            "task-test-1", {"filename": "custom-name.mkv"}
        )

        self.assertEqual(task["final_filename"], "custom-name.mkv")

    def test_preview_stage_unchanged(self):
        task = self.pipeline.preview_task("task-test-1", {"title_cn": "新标题"})

        self.assertEqual(task["stage"], "AWAIT_REVIEW")
        self.assertEqual(task["status"], "PENDING")

    def test_preview_generates_filename_when_empty(self):
        self.conn.execute(
            "UPDATE tasks SET final_filename='' WHERE task_id='task-test-1'"
        )
        self.conn.commit()

        task = self.pipeline.preview_task("task-test-1", {})

        self.assertTrue(task.get("final_filename"))
        self.assertIn("mkv", task["final_filename"])
        self.assertIn("2009", task["final_filename"])

    def test_preview_task_not_found(self):
        from media_importer.features.import_flow.utils import PipelineError

        with self.assertRaises(PipelineError):
            self.pipeline.preview_task("nonexistent", {})

    def test_preview_filters_disabled_dimensions(self):
        self.conn.execute(
            "UPDATE dimensions SET is_enabled=0 WHERE name='media_type'"
        )
        self.conn.commit()

        task = self.pipeline.preview_task(
            "task-test-1", {"dimensions": {"media_type": "tv", "unknown_dim": "x"}}
        )

        dims = task["scrape_dimensions"]
        if isinstance(dims, str):
            dims = json.loads(dims)
        self.assertNotIn("media_type", dims)
        self.assertNotIn("unknown_dim", dims)

    def test_preview_handles_string_scrape_result(self):
        self.conn.execute(
            "UPDATE tasks SET scrape_result='{}' WHERE task_id='task-test-1'"
        )
        self.conn.commit()

        task = self.pipeline.preview_task("task-test-1", {"title_cn": "测试"})

        self.assertEqual(task["scrape_title_cn"], "测试")

    def test_preview_handles_string_scrape_dimensions(self):
        self.conn.execute(
            "UPDATE tasks SET scrape_dimensions='{}' WHERE task_id='task-test-1'"
        )
        self.conn.commit()

        task = self.pipeline.preview_task(
            "task-test-1", {"dimensions": {"media_type": "movie"}}
        )

        dims = task["scrape_dimensions"]
        if isinstance(dims, str):
            dims = json.loads(dims)
        self.assertEqual(dims["media_type"], "movie")

    def test_preview_multiple_updates_at_once(self):
        task = self.pipeline.preview_task(
            "task-test-1",
            {"title_cn": "新标题", "title_en": "New Title", "year": 2023, "filename": "新标题.2023.mkv"},
        )

        self.assertEqual(task["scrape_title_cn"], "新标题")
        self.assertEqual(task["scrape_title_en"], "New Title")
        self.assertEqual(task["scrape_year"], "2023")
        self.assertEqual(task["final_filename"], "新标题.2023.mkv")

    def test_preview_empty_updates_still_reclassifies(self):
        task = self.pipeline.preview_task("task-test-1", {})

        self.assertIsNotNone(task)
        self.assertEqual(task["task_id"], "task-test-1")

    def test_manual_candidate_refreshes_details_without_starting_import(self):
        library = os.path.join(self.data_dir, "manual-candidate-library")
        os.makedirs(library, exist_ok=True)
        self.pipeline.config = {
            "fallback_dir": library,
            "filename_templates": {
                "movie": "{title_cn}.{year}.{ext}",
            },
        }
        candidate = {
            "provider_type": "tmdb",
            "provider_id": "290098",
            "language": "zh-CN",
            "dimensions": {"media_type": "movie"},
            "dim_sources": {"media_type": "provider:tmdb"},
            "scrape_result": {
                "title_cn": "小姐",
                "title_en": "The Handmaiden",
                "year": 2016,
                "media_type": "movie",
                "overview": "完整简介",
                "provider_type": "tmdb",
                "provider_id": "290098",
                "dimensions": {"media_type": "movie"},
                "match_level": "NEEDS_CONFIRM",
                "match_concerns": [],
                "manual_selected": True,
            },
        }
        with patch(
            "media_importer.features.tasks.search_service.load_provider_candidate",
            return_value=candidate,
        ):
            task = self.pipeline.apply_scrape_candidate(
                "task-test-1",
                provider_type="tmdb",
                item_id="290098",
                media_type="movie",
                language="zh-CN",
            )

        self.assertEqual(task["status"], "PENDING")
        self.assertEqual(task["stage"], "AWAIT_REVIEW")
        self.assertEqual(task["provider_id"], "290098")
        self.assertEqual(task["scrape_title_cn"], "小姐")
        self.assertEqual(task["scrape_result"]["overview"], "完整简介")
        self.assertEqual(os.path.normpath(task["import_path"]), library)
        self.assertEqual(task["final_filename"], "小姐.2016.mkv")
        self.assertEqual(task["import_success"], 0)
        self.assertFalse(os.path.exists(os.path.join(library, task["final_filename"])))


# ============================================================================
# search_provider_candidates 测试
# ============================================================================


class FakeSearchItem:
    def __init__(self, item_id, title, year, media_type="movie",
                 original_title="", overview="", poster_url="",
                 vote_average=0.0):
        self.item_id = item_id
        self.title = title
        self.original_title = original_title or title
        self.year = year
        self.media_type = media_type
        self.overview = overview
        self.poster_url = poster_url
        self.vote_average = vote_average


class FakeSearchResult:
    def __init__(self, items):
        self.items = items if items is not None else []


class FakeProvider:
    def __init__(self, provider_type, items=None, should_fail=False):
        self.provider_type = provider_type
        self._items = items or []
        self.should_fail = should_fail

    def search(self, query, year=None, media_type=None):
        if self.should_fail:
            raise RuntimeError("provider error")
        return FakeSearchResult(self._items)


class TestSearchProviderCandidates(unittest.TestCase):
    """search_provider_candidates 边界和正常场景测试。"""

    def setUp(self):
        from media_importer.features.tasks.search_service import (
            search_provider_candidates,
        )

        self.search_fn = search_provider_candidates

    def test_search_returns_candidates(self):
        providers = [FakeProvider("tmdb", [FakeSearchItem("1", "阿凡达", 2009, overview="科幻电影")])]
        with patch("media_importer.features.providers.create_providers", lambda _: providers):
            result = self.search_fn({}, "阿凡达", year="2009")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "阿凡达")
        self.assertEqual(result[0]["provider_type"], "tmdb")

    def test_search_empty_config_returns_empty(self):
        with patch("media_importer.features.providers.create_providers", lambda _: []):
            result = self.search_fn({}, "test")

        self.assertEqual(result, [])

    def test_search_all_providers_fail_returns_empty(self):
        providers = [FakeProvider("tmdb", should_fail=True), FakeProvider("douban", should_fail=True)]
        with patch("media_importer.features.providers.create_providers", lambda _: providers):
            result = self.search_fn({}, "test")

        self.assertEqual(result, [])

    def test_search_dedup_by_id_and_provider(self):
        providers = [
            FakeProvider("tmdb", [FakeSearchItem("1", "Avatar", 2009)]),
            FakeProvider("douban", [FakeSearchItem("1", "Avatar", 2009)]),
        ]
        with patch("media_importer.features.providers.create_providers", lambda _: providers):
            result = self.search_fn({}, "Avatar")

        self.assertEqual(len(result), 2)
        provider_types = {r["provider_type"] for r in result}
        self.assertEqual(provider_types, {"tmdb", "douban"})

    def test_search_same_id_same_provider_dedup(self):
        providers = [
            FakeProvider("tmdb", [
                FakeSearchItem("1", "Avatar", 2009),
                FakeSearchItem("1", "Avatar 3D", 2010),
            ]),
        ]
        with patch("media_importer.features.providers.create_providers", lambda _: providers):
            result = self.search_fn({}, "Avatar")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Avatar")

    def test_search_overview_truncation(self):
        long_overview = "A" * 300
        providers = [FakeProvider("tmdb", [FakeSearchItem("1", "Test", 2000, overview=long_overview)])]
        with patch("media_importer.features.providers.create_providers", lambda _: providers):
            result = self.search_fn({}, "Test")

        self.assertEqual(len(result), 1)
        self.assertLessEqual(len(result[0]["overview"]), 203)

    def test_search_returns_up_to_twenty_candidates(self):
        items = [FakeSearchItem(str(i), f"Movie {i}", 2020) for i in range(30)]
        providers = [FakeProvider("tmdb", items)]
        with patch("media_importer.features.providers.create_providers", lambda _: providers):
            result = self.search_fn({}, "Movie")

        self.assertEqual(len(result), 20)

    def test_search_honors_smaller_limit(self):
        items = [FakeSearchItem(str(i), f"Movie {i}", 2020) for i in range(10)]
        providers = [FakeProvider("tmdb", items)]
        with patch("media_importer.features.providers.create_providers", lambda _: providers):
            result = self.search_fn({}, "Movie", limit=7)

        self.assertEqual(len(result), 7)

    def test_search_handles_provider_with_empty_result(self):
        providers = [
            FakeProvider("tmdb", []),
            FakeProvider("douban", [FakeSearchItem("2", "Match", 2020)]),
        ]
        with patch("media_importer.features.providers.create_providers", lambda _: providers):
            result = self.search_fn({}, "Match")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["provider_type"], "douban")

    def test_search_handles_provider_with_none_result(self):
        providers = [FakeProvider("tmdb", items=None)]
        with patch("media_importer.features.providers.create_providers", lambda _: providers):
            result = self.search_fn({}, "test")

        self.assertEqual(result, [])


class TestLoadProviderCandidate(unittest.TestCase):
    def test_loads_full_details_in_selected_language_and_maps_dimensions(self):
        from media_importer.features.providers import (
            DimensionMapping,
            Genre,
            MediaDetails,
        )
        from media_importer.features.tasks.search_service import (
            load_provider_candidate,
        )

        class FakeDetailsProvider:
            received_config = {}

            def __init__(self, config):
                type(self).received_config = config

            def get_details(self, item_id, media_type):
                self.item_id = item_id
                return MediaDetails(
                    provider_type="tmdb",
                    item_id=item_id,
                    media_type=media_type,
                    title="小姐",
                    original_title="The Handmaiden",
                    year=2016,
                    genres=[Genre(id="18", name="剧情")],
                    overview="完整简介",
                    vote_average=8.1,
                    origin_country=["KR"],
                    original_language="ko",
                    adult=False,
                    tagline="",
                    poster_url="https://image.example/poster.jpg",
                    raw_data={},
                )

            def map_dimensions(self, dim_configs, details):
                self.dim_configs = dim_configs
                self.details = details
                return [
                    DimensionMapping(
                        name="documentary",
                        value="否",
                        source_reliability=0.9,
                        source="tmdb",
                    ),
                ]

        config = {
            "metadata": {
                "providers": [
                    {
                        "type": "tmdb",
                        "enabled": True,
                        "api_key": "secret",
                        "language": "zh-CN",
                    },
                ],
            },
        }
        with (
            patch(
                "media_importer.features.providers.get_provider_class",
                return_value=FakeDetailsProvider,
            ),
            patch(
                "media_importer.features.scraping.dimension_manager.get_dimensions_for_provider",
                return_value=[{"name": "documentary"}],
            ),
            patch(
                "media_importer.infrastructure.db.get_enabled_dimensions",
                return_value=[{"name": "media_type"}, {"name": "documentary"}],
            ),
        ):
            result = load_provider_candidate(
                config,
                object(),
                provider_type="tmdb",
                item_id="290098",
                media_type="movie",
                language="ko-KR",
            )

        self.assertEqual(FakeDetailsProvider.received_config["language"], "ko-KR")
        self.assertEqual(result["provider_id"], "290098")
        self.assertEqual(result["scrape_result"]["title_cn"], "小姐")
        self.assertEqual(result["scrape_result"]["overview"], "完整简介")
        self.assertEqual(result["dimensions"]["documentary"], "否")
        self.assertEqual(result["dimensions"]["media_type"], "movie")


# ============================================================================
# 辅助：ConfirmMixin 的最小子类用于测试
# ============================================================================


class _PreviewPipeline:
    """最小 Pipeline stub，混入 ConfirmMixin 供 preview_task 测试用。"""

    def __init__(self, task_manager, config):
        from media_importer.features.import_flow.confirm import ConfirmMixin

        self.task_manager = task_manager
        self.config = config
        self._confirm_mixin = ConfirmMixin()

    def preview_task(self, task_id: str, updates: dict) -> dict:
        return self._confirm_mixin.preview_task.__get__(
            self, type(self)
        )(task_id, updates)

    def apply_scrape_candidate(self, task_id: str, **selection) -> dict:
        return self._confirm_mixin.apply_scrape_candidate.__get__(
            self, type(self)
        )(task_id, **selection)

    def _log(self, level, msg, task=None, step=""):
        pass


if __name__ == "__main__":
    unittest.main()
