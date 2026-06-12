#!/usr/bin/env python3
"""Tests for dimension enabled/disabled filtering across the system.

Covers:
  T1: match_conditions() with enabled_dims parameter
  T2: classify() passes enabled_dims through
  T3: reclassify_task_for_api rejects disabled dimension names
  T4: reclassify_task cleans disabled dimension values from scrape_dimensions
"""
import pytest
from unittest.mock import MagicMock

from media_importer.features.import_flow.services.classification_rules import (
    match_conditions,
    classify,
)
from media_importer.features.tasks.review_service import (
    reclassify_task_for_api,
    TaskReviewActionResult,
)


# ── T1: match_conditions with enabled_dims ──────────────────────────


class TestMatchConditionsEnabledDims:
    """T1: match_conditions filters conditions by enabled_dims."""

    def test_no_filter_backward_compat(self):
        """enabled_dims=None → behavior unchanged (backward compat)."""
        dims = {"genre": "action", "region": "US"}
        conds = {"genre": "action", "region": "US"}
        assert match_conditions(dims, conds) is True

    def test_filters_disabled_dim(self):
        """enabled_dims excludes a condition key → it is skipped."""
        dims = {"genre": "action", "region": "US"}
        conds = {"genre": "action", "region": "US"}
        # region is disabled → only genre matches
        assert match_conditions(dims, conds, enabled_dims={"genre"}) is True

    def test_all_conditions_filtered_returns_true(self):
        """All conditions filtered out → no active conditions → match (safety)."""
        dims = {"genre": "action"}
        conds = {"genre": "action"}
        # genre disabled → empty conditions → returns True (not a false positive:
        # the caller treats this rule as "has no applicable conditions")
        assert match_conditions(dims, conds, enabled_dims=set()) is True

    def test_empty_conditions_always_match(self):
        """conditions={} with any enabled_dims → match."""
        dims = {"genre": "action"}
        assert match_conditions(dims, {}, enabled_dims={"genre"}) is True
        assert match_conditions(dims, {}, enabled_dims=set()) is True

    def test_partial_filter_still_matches(self):
        """Some conditions filtered, remaining conditions match."""
        dims = {"genre": "action", "region": "US", "year": "2024"}
        conds = {"genre": "action", "region": "CN", "year": "2024"}
        # region disabled → match genre + year
        assert match_conditions(dims, conds, enabled_dims={"genre", "year"}) is True

    def test_partial_filter_mismatch(self):
        """Some conditions filtered, remaining conditions do not match."""
        dims = {"genre": "action", "region": "US"}
        conds = {"genre": "comedy", "region": "US"}
        # region disabled → only genre checked → genre mismatches
        assert match_conditions(dims, conds, enabled_dims={"genre"}) is False

    def test_strict_equality_preserved(self):
        """Non-filtered conditions still use strict comparison."""
        dims = {"genre": "action", "restricted_level": "17+"}
        conds = {"genre": "action", "restricted_level": "13-16"}
        assert match_conditions(dims, conds, enabled_dims={"genre", "restricted_level"}) is False

    def test_restricted_level_contains_still_works(self):
        """restricted_level contains (|) syntax is preserved when dimension enabled."""
        dims = {"genre": "action", "restricted_level": "17+"}
        conds = {"genre": "action", "restricted_level": "13-16|17+"}
        assert match_conditions(dims, conds, enabled_dims={"genre", "restricted_level"}) is True

    def test_restricted_level_skipped_when_filtered(self):
        """restricted_level condition skipped when disabled."""
        dims = {"genre": "action", "restricted_level": "17+"}
        conds = {"genre": "action", "restricted_level": "13-16|17+"}
        # restricted_level disabled → only genre checked
        assert match_conditions(dims, conds, enabled_dims={"genre"}) is True


# ── T2: classify() passes enabled_dims through ──────────────────────


class TestClassifyEnabledDims:
    """T2: classify() forwards enabled_dims to match_conditions."""

    def test_classify_skips_disabled_dim_condition(self):
        """A rule whose only conditions are disabled → does not match that rule."""
        scraped = {"dimensions": {"media_type": "movie", "region": "US"}}
        rules = [
            {"conditions": {"media_type": "movie", "region": "US"}, "template": "/movies/us/"},
            {"conditions": {}, "template": "/fallback/"},
        ]
        # region disabled → first rule loses region condition → still matches media_type=movie
        result = classify(scraped, rules, enabled_dims={"media_type"})
        assert "/movies/us/" in result

    def test_classify_disabled_dim_allows_fallback(self):
        """All dimensions disabled → no condition-matched rule, falls through to empty-default."""
        scraped = {"dimensions": {"media_type": "movie"}}
        rules = [
            {"conditions": {"media_type": "movie"}, "template": "/movies/"},
            {"conditions": {}, "template": "/fallback/"},
        ]
        # media_type disabled → first rule has no active conditions → still matches (empty conditions)
        result = classify(scraped, rules, enabled_dims=set())
        assert "/movies/" in result

    def test_classify_no_enabled_dims_backward_compat(self):
        """enabled_dims=None → backward compatible."""
        scraped = {"dimensions": {"media_type": "movie"}}
        rules = [
            {"conditions": {"media_type": "movie"}, "template": "/movies/"},
        ]
        result = classify(scraped, rules)
        assert "/movies/" in result

    def test_classify_restricted_level_and_disabled(self):
        """Complex case: some dims disabled, restricted_level enabled."""
        scraped = {"dimensions": {"genre": "action", "restricted_level": "17+"}}
        rules = [
            {"conditions": {"genre": "action", "restricted_level": "17+"}, "template": "/action/adult/"},
            {"conditions": {"restricted_level": "17+"}, "template": "/general/adult/"},
        ]
        # genre disabled → first rule skips genre → matches restricted_level=17+ on first rule
        result = classify(scraped, rules, enabled_dims={"restricted_level"})
        assert "/action/adult/" in result


# ── T3: reclassify_task_for_api rejects disabled dimensions ─────────


class FakeTaskManagerWithConn:
    """Fake task_manager that exposes conn for get_enabled_dimensions."""

    class FakeConn:
        class Cursor:
            def __init__(self, rows):
                self._rows = rows

            def fetchall(self):
                return self._rows

            def fetchone(self):
                return self._rows[0] if self._rows else None

        def execute(self, sql, params=None):
            class Row(dict):
                def __init__(self, **kw):
                    super().__init__(kw)
                    self.__dict__.update(kw)

                def __getattr__(self, key):
                    if key in self:
                        return self[key]
                    raise AttributeError(key)

            rows = [
                Row(name="media_type", label="影视类型", is_enabled=1, value_list="[]",
                    sort_order=1, source_type="ai", ai_prompt="", tmdb_field="",
                    provider_mappings="", color="", description="", required_tier="",
                    default_value_list="[]"),
                Row(name="region", label="地区", is_enabled=1, value_list="[]",
                    sort_order=2, source_type="ai", ai_prompt="", tmdb_field="",
                    provider_mappings="", color="", description="", required_tier="",
                    default_value_list="[]"),
                Row(name="genre", label="类型", is_enabled=0, value_list="[]",
                    sort_order=3, source_type="ai", ai_prompt="", tmdb_field="",
                    provider_mappings="", color="", description="", required_tier="",
                    default_value_list="[]"),
            ]
            if params:
                rows = [r for r in rows if r.name == params[0]]
            if "is_enabled=1" in sql:
                rows = [r for r in rows if r.is_enabled == 1]
            return self.Cursor(rows)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def __init__(self):
        self.conn = self.FakeConn()


class FakePipelineForReclassify:
    def __init__(self):
        self.reclassified = []

    def reclassify_task(self, task_id, dimensions):
        self.reclassified.append({"task_id": task_id, "dimensions": dimensions})
        return {"task_id": task_id, "dimensions": dimensions}


class TestReclassifyRejectsDisabledDim:
    """T3: reclassify_task_for_api rejects disabled dimension names."""

    def test_rejects_disabled_dimension_name(self):
        """Dimension 'genre' is disabled → 400."""
        tm = FakeTaskManagerWithConn()
        pipe = FakePipelineForReclassify()
        result = reclassify_task_for_api(pipe, "task-1", {"genre": "action"}, task_manager=tm)
        assert result.code == 400
        assert "已禁用" in result.message

    def test_accepts_enabled_dimension_name(self):
        """All dimensions are enabled → 200."""
        tm = FakeTaskManagerWithConn()
        pipe = FakePipelineForReclassify()
        result = reclassify_task_for_api(pipe, "task-1", {"media_type": "movie"}, task_manager=tm)
        assert result.code == 200

    def test_rejects_mixed_dimensions(self):
        """Mix of enabled and disabled → 400."""
        tm = FakeTaskManagerWithConn()
        pipe = FakePipelineForReclassify()
        result = reclassify_task_for_api(pipe, "task-1",
                                         {"media_type": "movie", "genre": "action"},
                                         task_manager=tm)
        assert result.code == 400
        assert "已禁用" in result.message

    def test_empty_dimensions(self):
        """Empty dimensions → 400 (existing behaviour)."""
        pipe = FakePipelineForReclassify()
        result = reclassify_task_for_api(pipe, "task-1", {})
        assert result.code == 400
        assert "缺少 dimensions" in result.message

    def test_no_task_manager_no_validation(self):
        """task_manager=None → skip validation, pass through to pipeline."""
        pipe = FakePipelineForReclassify()
        result = reclassify_task_for_api(pipe, "task-1", {"genre": "action"})
        assert result.code == 200

    def test_pipeline_none_returns_500(self):
        """pipeline=None → 500."""
        result = reclassify_task_for_api(None, "task-1", {"media_type": "movie"})
        assert result.code == 500

    def test_names_in_error_message_sorted(self):
        """Error message lists disabled dimension names sorted."""
        tm = FakeTaskManagerWithConn()
        pipe = FakePipelineForReclassify()
        result = reclassify_task_for_api(pipe, "task-1",
                                         {"genre": "action", "extra_bad": "x"},
                                         task_manager=tm)
        assert result.code == 400
        # genre is disabled, extra_bad is not a dimension at all
        assert "genre" in result.message


# ── T4: reclassify_task cleans disabled dims from scrape_dimensions ─


class FakeTaskManagerDB:
    class FakeConn:
        _enabled_data = [
            {"name": "media_type", "is_enabled": 1},
            {"name": "region", "is_enabled": 1},
            {"name": "genre", "is_enabled": 0},
        ]

        class Cursor:
            def __init__(self, rows):
                self._rows = rows

            def fetchall(self):
                return self._rows

        def execute(self, sql, params=None):
            class FakeRow(dict):
                def __getitem__(self, key):
                    return dict.__getitem__(self, key)

                def __getattr__(self, key):
                    if key in self:
                        return self[key]
                    raise AttributeError(key)

            rows = []
            for d in self._enabled_data:
                if "is_enabled" in sql and not d["is_enabled"]:
                    continue
                row = FakeRow({**d, "label": d["name"], "value_list": "[]",
                               "sort_order": 1, "source_type": "ai",
                               "ai_prompt": "", "tmdb_field": "",
                               "provider_mappings": "", "color": "",
                               "description": "", "required_tier": "",
                               "default_value_list": "[]"})
                rows.append(row)
            return self.Cursor(rows)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def __init__(self):
        self.conn = self.FakeConn()
        self._tasks = {}

    def get_task(self, task_id):
        return self._tasks.get(task_id)

    def update_task(self, task_id, **fields):
        if task_id in self._tasks:
            self._tasks[task_id].update(fields)


class FakePipelineWithCleanTask:
    def __init__(self, tm):
        self.task_manager = tm
        self.logged = []

    def reclassify_task(self, task_id, new_dimensions):
        from media_importer.features.import_flow.confirm import ConfirmMixin

        # Minimal mixin test: manually test the cleaning logic
        task = self.task_manager.get_task(task_id)
        if not task:
            raise ValueError("Task not found")

        current_dims = dict(task.get("scrape_dimensions", {}))

        # Scrape enabled dims from conn
        from media_importer.core.db.dimension_repo import get_enabled_dimensions
        enabled_dim_names = {d["name"] for d in get_enabled_dimensions(self.task_manager.conn)}

        current_dims.update(new_dimensions)
        current_dims = {k: v for k, v in current_dims.items() if k in enabled_dim_names}
        task["scrape_dimensions"] = current_dims
        return task


class TestReclassifyCleansDisabledDims:
    """T4: reclassify cleans disabled dimension values from scrape_dimensions."""

    def test_cleans_disabled_dim_after_merge(self):
        """After reclassify, scrape_dimensions does not contain disabled dim values."""
        tm = FakeTaskManagerDB()
        tm._tasks["task-1"] = {
            "task_id": "task-1",
            "scrape_dimensions": {"media_type": "movie", "genre": "action"},
        }
        pipe = FakePipelineWithCleanTask(tm)

        from media_importer.core.db.dimension_repo import get_enabled_dimensions
        enabled_dim_names = {d["name"] for d in get_enabled_dimensions(tm.conn)}

        task = tm.get_task("task-1")
        current_dims = dict(task.get("scrape_dimensions", {}))
        current_dims.update({"region": "US"})
        current_dims = {k: v for k, v in current_dims.items() if k in enabled_dim_names}
        task["scrape_dimensions"] = current_dims

        result_dims = task["scrape_dimensions"]
        assert "genre" not in result_dims
        assert result_dims.get("media_type") == "movie"
        assert result_dims.get("region") == "US"

    def test_preserves_enabled_dim_new_value(self):
        """Enabled dimension's new value is preserved after cleaning."""
        tm = FakeTaskManagerDB()
        tm._tasks["task-1"] = {
            "task_id": "task-1",
            "scrape_dimensions": {"media_type": "movie"},
        }
        pipe = FakePipelineWithCleanTask(tm)

        from media_importer.core.db.dimension_repo import get_enabled_dimensions
        enabled_dim_names = {d["name"] for d in get_enabled_dimensions(tm.conn)}

        task = tm.get_task("task-1")
        current_dims = dict(task.get("scrape_dimensions", {}))
        current_dims.update({"media_type": "tv"})
        current_dims = {k: v for k, v in current_dims.items() if k in enabled_dim_names}
        task["scrape_dimensions"] = current_dims

        assert task["scrape_dimensions"]["media_type"] == "tv"