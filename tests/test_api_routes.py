#!/usr/bin/env python3
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.api.handler import APIHandler
from media_importer.api.routes import API_ROUTES, match_route


class TestAPIRoutes(unittest.TestCase):
    def assert_route(self, method, path, handler_name, params=None):
        match = match_route(method, path)

        self.assertIsNotNone(match, f"{method} {path} should match")
        self.assertEqual(match.route.handler_name, handler_name)
        self.assertEqual(match.params, params or {})
        return match.route

    def test_static_health_does_not_require_auth(self):
        route = self.assert_route("GET", "/api/health", "_health")

        self.assertFalse(route.auth_required)

    def test_stable_get_routes(self):
        self.assert_route("GET", "/api/metrics", "_metrics")
        self.assert_route("GET", "/api/config", "_config")
        self.assert_route("GET", "/api/config/validate", "_config_validate")
        self.assert_route("GET", "/api/tasks", "_list_tasks")
        self.assert_route("GET", "/api/tasks/stats", "_task_stats")
        self.assert_route("GET", "/api/queue/status", "_queue_status")
        self.assert_route("GET", "/api/providers", "_providers_list")
        self.assert_route("GET", "/api/recycle/list", "recycle_list")

    def test_task_routes_prefer_exact_paths_before_task_id(self):
        self.assert_route("GET", "/api/tasks/stats", "_task_stats")
        self.assert_route("POST", "/api/tasks/confirm-all", "_task_confirm_all")

    def test_task_dynamic_routes(self):
        self.assert_route(
            "GET", "/api/tasks/abc123", "_get_task",
            {"task_id": "abc123"},
        )
        self.assert_route(
            "GET", "/api/tasks/abc123/subtitles", "_task_subtitles",
            {"task_id": "abc123"},
        )
        self.assert_route(
            "POST", "/api/tasks/abc123/cancel", "_task_cancel",
            {"task_id": "abc123"},
        )
        self.assert_route(
            "POST", "/api/tasks/abc123/retry", "_retry_task",
            {"task_id": "abc123"},
        )
        self.assert_route(
            "POST", "/api/tasks/abc123/reclassify", "_task_reclassify",
            {"task_id": "abc123"},
        )
        self.assert_route(
            "POST", "/api/tasks/abc123/preview", "_task_preview",
            {"task_id": "abc123"},
        )
        self.assert_route(
            "POST", "/api/tasks/abc123/scrape-search", "_task_scrape_search",
            {"task_id": "abc123"},
        )
        self.assert_route(
            "DELETE", "/api/tasks/abc123", "_delete_task",
            {"task_id": "abc123"},
        )

    def test_provider_routes(self):
        self.assert_route(
            "GET", "/api/providers/tmdb/genres", "_provider_genres_list",
            {"provider_type": "tmdb"},
        )
        self.assert_route(
            "POST", "/api/providers/tmdb/search", "_provider_search",
            {"provider_type": "tmdb"},
        )

    def test_dimension_routes(self):
        self.assert_route(
            "GET", "/api/dimensions/media_type", "_dimension_get",
            {"dim_name": "media_type"},
        )
        self.assert_route(
            "PUT", "/api/dimensions/media_type", "_dimension_update",
            {"dim_name": "media_type"},
        )
        self.assert_route(
            "POST", "/api/dimensions/media_type/enable", "_dimension_enable",
            {"dim_name": "media_type"},
        )

    def test_unknown_route_returns_none(self):
        self.assertIsNone(match_route("GET", "/api/not-found"))
        self.assertIsNone(match_route("POST", "/api/tasks/abc123/not-real"))

    def test_no_duplicate_method_pattern_pairs(self):
        pairs = [(route.method, route.pattern) for route in API_ROUTES]

        self.assertEqual(len(pairs), len(set(pairs)))

    def test_all_registered_route_handlers_exist_on_api_handler(self):
        for route in API_ROUTES:
            with self.subTest(method=route.method, pattern=route.pattern):
                self.assertTrue(
                    hasattr(APIHandler, route.handler_name),
                    f"{route.method} {route.pattern} -> {route.handler_name}",
                )

    def test_dispatch_unified_kwargs_signature(self):
        """新 dispatch 统一 handler 签名 (self, *, body, params, query)。"""
        handler = APIHandler.__new__(APIHandler)
        calls = []
        handler._check_auth = lambda: True
        handler._task_reclassify = lambda *, body, params, query: calls.append(("reclassify", body, params, query))
        handler._provider_search = lambda *, body, params, query: calls.append(("search", body, params, query))
        handler._delete_task = lambda *, body, params, query: calls.append(("delete", body, params, query))

        handler._dispatch_api_route(
            "POST", "/api/tasks/t1/reclassify",
            body={"dimensions": {"media_type": "movie"}},
        )
        handler._dispatch_api_route(
            "POST", "/api/providers/tmdb/search",
            body={"query": "Inception"},
        )
        handler._dispatch_api_route(
            "POST", "/api/tasks/t1/delete",
            body={"delete_files": True},
        )

        self.assertEqual(calls[0], ("reclassify", {"dimensions": {"media_type": "movie"}}, {"task_id": "t1"}, {}))
        self.assertEqual(calls[1], ("search", {"query": "Inception"}, {"provider_type": "tmdb"}, {}))
        self.assertEqual(calls[2], ("delete", {"delete_files": True}, {"task_id": "t1"}, {}))


if __name__ == "__main__":
    unittest.main()
