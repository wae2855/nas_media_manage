#!/usr/bin/env python3
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.api.routes import API_ROUTES, match_route
from media_importer.api.handler import APIHandler


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
            "POST", "/api/tasks/abc123/retry", "_retry_task",
            {"task_id": "abc123"},
        )
        self.assert_route(
            "POST", "/api/tasks/abc123/reclassify", "_task_reclassify",
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
        route = self.assert_route(
            "POST", "/api/providers/tmdb/search", "_provider_search",
            {"provider_type": "tmdb"},
        )

        self.assertTrue(route.pass_body)
        self.assertTrue(route.body_before_params)

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

    def test_dispatch_orders_task_params_before_body(self):
        handler = APIHandler.__new__(APIHandler)
        calls = []
        handler._check_auth = lambda: True
        handler._task_reclassify = lambda task_id, body: calls.append((task_id, body))

        handled = handler._dispatch_api_route(
            "POST",
            "/api/tasks/t1/reclassify",
            body={"dimensions": {"media_type": "movie"}},
        )

        self.assertTrue(handled)
        self.assertEqual(calls, [("t1", {"dimensions": {"media_type": "movie"}})])

    def test_dispatch_orders_provider_body_before_params(self):
        handler = APIHandler.__new__(APIHandler)
        calls = []
        handler._check_auth = lambda: True
        handler._provider_search = lambda body, provider_type: calls.append((body, provider_type))

        handled = handler._dispatch_api_route(
            "POST",
            "/api/providers/tmdb/search",
            body={"query": "Inception"},
        )

        self.assertTrue(handled)
        self.assertEqual(calls, [({"query": "Inception"}, "tmdb")])

    def test_dispatch_extracts_delete_files_from_body(self):
        handler = APIHandler.__new__(APIHandler)
        calls = []
        handler._check_auth = lambda: True
        handler._delete_task = lambda task_id, delete_files=False: calls.append((task_id, delete_files))

        handled = handler._dispatch_api_route(
            "POST",
            "/api/tasks/t1/delete",
            body={"delete_files": True},
        )

        self.assertTrue(handled)
        self.assertEqual(calls, [("t1", True)])


if __name__ == "__main__":
    unittest.main()
