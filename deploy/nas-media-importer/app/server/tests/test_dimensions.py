#!/usr/bin/env python3
"""
维度系统测试 - 覆盖 db.py / dimension_manager.py / file_analyzer.py / API 端点
测试场景:
  1. DB 维度 CRUD: seed / get_all / get_enabled / get / update / enable / disable
  2. dimension_manager: 按来源筛选 / TMDB 映射 (region / origin_lang / broad_genre)
  3. file_analyzer: classify_resolution_tier / analyze_file
  4. API 端点: GET /api/dimensions / GET /api/dimensions/enabled / POST enable/disable
"""
import os
import sys
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'media_importer'))

import db as db_module
import types

media_importer_pkg = types.ModuleType('media_importer')
media_importer_pkg.__path__ = [os.path.join(os.path.dirname(__file__), '..', 'media_importer')]
sys.modules['media_importer'] = media_importer_pkg
sys.modules['media_importer.db'] = db_module

from dimension_manager import (
    get_dimensions_for_scrape,
    get_dimensions_for_tmdb,
    get_dimensions_for_file,
    map_tmdb_to_dimension,
)
from file_analyzer import classify_resolution_tier, analyze_file


# ============================================================
# 1. db.py 维度 CRUD 测试
# ============================================================
class TestDBDimensions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="test_dims_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        self.db_path = os.path.join(self.tmpdir, f"test_{self._testMethodName}.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.conn = db_module.init_db(self.db_path)

    def tearDown(self):
        self.conn.close()

    def test_seed_creates_8_dimensions(self):
        dims = db_module.get_all_dimensions(self.conn)
        self.assertEqual(len(dims), 8)

    def test_seed_3_enabled(self):
        dims = db_module.get_enabled_dimensions(self.conn)
        enabled_names = [d["name"] for d in dims]
        self.assertEqual(len(dims), 3)
        self.assertIn("media_type", enabled_names)
        self.assertIn("documentary", enabled_names)
        self.assertIn("restricted_level", enabled_names)

    def test_get_all_dimensions_returns_8(self):
        dims = db_module.get_all_dimensions(self.conn)
        self.assertEqual(len(dims), 8)

    def test_get_enabled_dimensions_returns_only_enabled(self):
        dims = db_module.get_enabled_dimensions(self.conn)
        for d in dims:
            self.assertEqual(d["is_enabled"], 1)

    def test_get_dimension_by_name(self):
        dim = db_module.get_dimension(self.conn, "media_type")
        self.assertIsNotNone(dim)
        self.assertEqual(dim["name"], "media_type")
        self.assertEqual(dim["label"], "影视类型")
        self.assertEqual(dim["source_type"], "tmdb_ai")

    def test_get_dimension_not_found(self):
        dim = db_module.get_dimension(self.conn, "nonexistent")
        self.assertIsNone(dim)

    def test_update_dimension_ai_prompt(self):
        updated = db_module.update_dimension(
            self.conn, "media_type", ai_prompt="新的AI提示词"
        )
        self.assertEqual(updated["ai_prompt"], "新的AI提示词")

    def test_update_dimension_color(self):
        updated = db_module.update_dimension(
            self.conn, "media_type", color="#ff0000"
        )
        self.assertEqual(updated["color"], "#ff0000")

    def test_update_dimension_value_list(self):
        new_values = [
            {"value": "movie", "label": "电影"},
            {"value": "tv", "label": "剧集"},
            {"value": "short", "label": "短片"},
        ]
        updated = db_module.update_dimension(
            self.conn, "media_type", value_list=new_values
        )
        self.assertIsInstance(updated["value_list"], list)
        self.assertEqual(len(updated["value_list"]), 3)
        self.assertEqual(updated["value_list"][2]["value"], "short")

    def test_update_dimension_ignores_invalid_column(self):
        updated = db_module.update_dimension(
            self.conn, "media_type", invalid_column="should_be_ignored"
        )
        self.assertIsNotNone(updated)
        self.assertNotIn("invalid_column", updated)

    def test_enable_dimension(self):
        db_module.disable_dimension(self.conn, "animation")
        dim = db_module.get_dimension(self.conn, "animation")
        self.assertEqual(dim["is_enabled"], 0)

        updated = db_module.enable_dimension(self.conn, "animation")
        self.assertEqual(updated["is_enabled"], 1)

    def test_disable_dimension(self):
        dim_before = db_module.get_dimension(self.conn, "media_type")
        self.assertEqual(dim_before["is_enabled"], 1)

        updated = db_module.disable_dimension(self.conn, "media_type")
        self.assertEqual(updated["is_enabled"], 0)

        db_module.enable_dimension(self.conn, "media_type")

    def test_seed_does_not_overwrite_existing_data(self):
        dim = db_module.get_dimension(self.conn, "media_type")
        original_prompt = dim["ai_prompt"]
        db_module.update_dimension(self.conn, "media_type", ai_prompt="修改后的提示词")

        db_module._seed_dimensions(self.conn)

        dim_after = db_module.get_dimension(self.conn, "media_type")
        self.assertEqual(dim_after["ai_prompt"], "修改后的提示词")

    def test_dimension_value_list_is_parsed_json(self):
        dim = db_module.get_dimension(self.conn, "media_type")
        self.assertIsInstance(dim["value_list"], list)
        self.assertIsInstance(dim["value_list"][0], dict)
        self.assertIn("value", dim["value_list"][0])

    def test_all_8_dimension_names(self):
        dims = db_module.get_all_dimensions(self.conn)
        names = [d["name"] for d in dims]
        expected = [
            "media_type", "documentary", "restricted_level", "animation",
            "region", "origin_lang", "resolution_tier", "broad_genre",
        ]
        self.assertEqual(names, expected)


# ============================================================
# 2. dimension_manager.py 测试
# ============================================================
class TestDimensionManagerScrapeFilter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="test_dm_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        self.db_path = os.path.join(self.tmpdir, f"test_{self._testMethodName}.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.conn = db_module.init_db(self.db_path)

    def tearDown(self):
        self.conn.close()

    def test_get_dimensions_for_scrape_returns_ai_and_tmdb_ai(self):
        dims = get_dimensions_for_scrape(self.conn)
        for d in dims:
            self.assertIn(d["source_type"], ("ai", "tmdb_ai"))

    def test_get_dimensions_for_scrape_only_enabled(self):
        dims = get_dimensions_for_scrape(self.conn)
        all_dims = db_module.get_all_dimensions(self.conn)
        ai_names = [d["name"] for d in all_dims
                     if d["source_type"] in ("ai", "tmdb_ai") and d["is_enabled"] == 1]
        result_names = [d["name"] for d in dims]
        self.assertEqual(result_names, ai_names)

    def test_get_dimensions_for_tmdb_returns_tmdb_and_tmdb_ai(self):
        dims = get_dimensions_for_tmdb(self.conn)
        for d in dims:
            self.assertIn(d["source_type"], ("tmdb", "tmdb_ai"))

    def test_get_dimensions_for_tmdb_only_enabled(self):
        dims = get_dimensions_for_tmdb(self.conn)
        all_dims = db_module.get_all_dimensions(self.conn)
        tmdb_names = [d["name"] for d in all_dims
                       if d["source_type"] in ("tmdb", "tmdb_ai") and d["is_enabled"] == 1]
        result_names = [d["name"] for d in dims]
        self.assertEqual(result_names, tmdb_names)

    def test_get_dimensions_for_file_returns_file_only(self):
        db_module.enable_dimension(self.conn, "resolution_tier")
        dims = get_dimensions_for_file(self.conn)
        for d in dims:
            self.assertEqual(d["name"], "resolution_tier")
        db_module.disable_dimension(self.conn, "resolution_tier")

    def test_get_dimensions_for_file_only_enabled(self):
        dims = get_dimensions_for_file(self.conn)
        self.assertEqual(len(dims), 0)

        db_module.enable_dimension(self.conn, "resolution_tier")
        dims = get_dimensions_for_file(self.conn)
        self.assertEqual(len(dims), 1)
        self.assertEqual(dims[0]["name"], "resolution_tier")
        db_module.disable_dimension(self.conn, "resolution_tier")


class TestDimensionManagerTmdbMapping(unittest.TestCase):
    def _get_region_config(self):
        return {
            "name": "region",
            "source_type": "tmdb",
            "tmdb_field": "origin_country",
            "value_list": [
                {"value": "asia", "tmdb_codes": ["CN", "HK", "TW", "JP", "KR"]},
                {"value": "western", "tmdb_codes": ["US", "CA", "AU", "NZ", "GB", "IE"]},
                {"value": "european", "tmdb_codes": ["FR", "DE", "IT", "ES", "RU"]},
                {"value": "other"},
            ],
        }

    def _get_origin_lang_config(self):
        return {
            "name": "origin_lang",
            "source_type": "tmdb",
            "tmdb_field": "original_language",
            "value_list": [
                {"value": "zh"},
                {"value": "en"},
                {"value": "ja"},
                {"value": "ko"},
                {"value": "other"},
            ],
        }

    def _get_broad_genre_config(self):
        return {
            "name": "broad_genre",
            "source_type": "tmdb_ai",
            "tmdb_field": "genres",
            "value_list": [
                {"value": "horror", "tmdb_genre_ids": [27, 9648, 53], "priority": 1},
                {"value": "scifi", "tmdb_genre_ids": [878, 14, 10765], "priority": 2},
                {"value": "action", "tmdb_genre_ids": [28, 12, 10752, 37], "priority": 3},
                {"value": "comedy", "tmdb_genre_ids": [35], "priority": 4},
                {"value": "drama", "tmdb_genre_ids": [18, 10749, 80, 36], "priority": 5},
                {"value": "other", "tmdb_genre_ids": [10402, 10763], "priority": 6},
            ],
        }

    def test_map_region_cn(self):
        config = self._get_region_config()
        result = map_tmdb_to_dimension(config, {"origin_country": ["CN"]})
        self.assertEqual(result["name"], "region")
        self.assertEqual(result["value"], "asia")
        self.assertEqual(result["confidence"], 1.0)

    def test_map_region_us(self):
        config = self._get_region_config()
        result = map_tmdb_to_dimension(config, {"origin_country": ["US"]})
        self.assertEqual(result["value"], "western")

    def test_map_region_fr(self):
        config = self._get_region_config()
        result = map_tmdb_to_dimension(config, {"origin_country": ["FR"]})
        self.assertEqual(result["value"], "european")

    def test_map_region_unknown_falls_to_other(self):
        config = self._get_region_config()
        result = map_tmdb_to_dimension(config, {"origin_country": ["IN"]})
        self.assertEqual(result["value"], "other")

    def test_map_region_empty_country(self):
        config = self._get_region_config()
        result = map_tmdb_to_dimension(config, {"origin_country": []})
        self.assertIsNone(result["value"])
        self.assertEqual(result["confidence"], 0)

    def test_map_origin_lang_zh(self):
        config = self._get_origin_lang_config()
        result = map_tmdb_to_dimension(config, {"original_language": "zh"})
        self.assertEqual(result["name"], "origin_lang")
        self.assertEqual(result["value"], "zh")
        self.assertEqual(result["confidence"], 1.0)

    def test_map_origin_lang_en(self):
        config = self._get_origin_lang_config()
        result = map_tmdb_to_dimension(config, {"original_language": "en"})
        self.assertEqual(result["value"], "en")

    def test_map_origin_lang_unknown_falls_to_other(self):
        config = self._get_origin_lang_config()
        result = map_tmdb_to_dimension(config, {"original_language": "ar"})
        self.assertEqual(result["value"], "other")

    def test_map_origin_lang_empty(self):
        config = self._get_origin_lang_config()
        result = map_tmdb_to_dimension(config, {"original_language": ""})
        self.assertIsNone(result["value"])
        self.assertEqual(result["confidence"], 0)

    def test_map_broad_genre_horror(self):
        config = self._get_broad_genre_config()
        result = map_tmdb_to_dimension(config, {"genres": [{"id": 27, "name": "Horror"}]})
        self.assertEqual(result["name"], "broad_genre")
        self.assertEqual(result["value"], "horror")
        self.assertEqual(result["confidence"], 0.9)

    def test_map_broad_genre_comedy(self):
        config = self._get_broad_genre_config()
        result = map_tmdb_to_dimension(config, {"genres": [{"id": 35, "name": "Comedy"}]})
        self.assertEqual(result["value"], "comedy")

    def test_map_broad_genre_horror_plus_comedy_picks_horror(self):
        config = self._get_broad_genre_config()
        result = map_tmdb_to_dimension(config, {
            "genres": [
                {"id": 27, "name": "Horror"},
                {"id": 35, "name": "Comedy"},
            ]
        })
        self.assertEqual(result["value"], "horror")

    def test_map_broad_genre_empty_genres(self):
        config = self._get_broad_genre_config()
        result = map_tmdb_to_dimension(config, {"genres": []})
        self.assertIsNone(result["value"])
        self.assertEqual(result["confidence"], 0)

    def test_map_broad_genre_no_matching_genre_falls_to_other(self):
        config = self._get_broad_genre_config()
        result = map_tmdb_to_dimension(config, {"genres": [{"id": 99, "name": "Unknown"}]})
        self.assertEqual(result["value"], "other")

    def test_map_unknown_source_type_returns_none(self):
        config = {"name": "test_dim", "source_type": "unknown", "tmdb_field": ""}
        result = map_tmdb_to_dimension(config, {})
        self.assertEqual(result["value"], None)
        self.assertEqual(result["confidence"], 0)

    def test_map_broad_genre_with_int_ids(self):
        config = self._get_broad_genre_config()
        result = map_tmdb_to_dimension(config, {"genres": [878]})
        self.assertEqual(result["value"], "scifi")


# ============================================================
# 3. file_analyzer.py 测试
# ============================================================
class TestFileAnalyzer(unittest.TestCase):
    def test_classify_resolution_tier_4k(self):
        value_list = [
            {"value": "4k", "min_width": 3840},
            {"value": "1080p", "min_width": 1920},
            {"value": "720p", "min_width": 1280},
            {"value": "sd", "min_width": 0},
        ]
        result = classify_resolution_tier(3840, value_list)
        self.assertEqual(result, "4k")

    def test_classify_resolution_tier_1080p(self):
        value_list = [
            {"value": "4k", "min_width": 3840},
            {"value": "1080p", "min_width": 1920},
            {"value": "720p", "min_width": 1280},
            {"value": "sd", "min_width": 0},
        ]
        result = classify_resolution_tier(1920, value_list)
        self.assertEqual(result, "1080p")

    def test_classify_resolution_tier_720p(self):
        value_list = [
            {"value": "4k", "min_width": 3840},
            {"value": "1080p", "min_width": 1920},
            {"value": "720p", "min_width": 1280},
            {"value": "sd", "min_width": 0},
        ]
        result = classify_resolution_tier(1280, value_list)
        self.assertEqual(result, "720p")

    def test_classify_resolution_tier_sd(self):
        value_list = [
            {"value": "4k", "min_width": 3840},
            {"value": "1080p", "min_width": 1920},
            {"value": "720p", "min_width": 1280},
            {"value": "sd", "min_width": 0},
        ]
        result = classify_resolution_tier(720, value_list)
        self.assertEqual(result, "sd")

    def test_classify_resolution_tier_between_tiers(self):
        value_list = [
            {"value": "4k", "min_width": 3840},
            {"value": "1080p", "min_width": 1920},
            {"value": "720p", "min_width": 1280},
            {"value": "sd", "min_width": 0},
        ]
        result = classify_resolution_tier(2500, value_list)
        self.assertEqual(result, "1080p")

    def test_classify_resolution_tier_no_sd_fallback(self):
        value_list = [
            {"value": "4k", "min_width": 3840},
            {"value": "1080p", "min_width": 1920},
        ]
        result = classify_resolution_tier(100, value_list)
        self.assertEqual(result, "sd")

    def test_analyze_file_empty_dimensions_returns_empty(self):
        result = analyze_file("/fake/path.mkv", [])
        self.assertEqual(result, {})

    @patch("file_analyzer.detect_resolution")
    def test_analyze_file_with_resolution_dimension(self, mock_detect):
        mock_detect.return_value = {"width": 1920, "height": 1080}
        dims = [
            {
                "name": "resolution_tier",
                "value_list": [
                    {"value": "4k", "min_width": 3840},
                    {"value": "1080p", "min_width": 1920},
                    {"value": "720p", "min_width": 1280},
                    {"value": "sd", "min_width": 0},
                ],
            }
        ]
        result = analyze_file("/fake/path.mkv", dims)
        self.assertIn("resolution_tier", result)
        self.assertEqual(result["resolution_tier"]["value"], "1080p")
        self.assertEqual(result["resolution_tier"]["confidence"], 1.0)
        self.assertEqual(result["resolution_tier"]["source"], "file")

    @patch("file_analyzer.detect_resolution")
    def test_analyze_file_zero_width_returns_none_value(self, mock_detect):
        mock_detect.return_value = {"width": 0, "height": 0}
        dims = [
            {
                "name": "resolution_tier",
                "value_list": [
                    {"value": "4k", "min_width": 3840},
                    {"value": "sd", "min_width": 0},
                ],
            }
        ]
        result = analyze_file("/fake/path.mkv", dims)
        self.assertIn("resolution_tier", result)
        self.assertIsNone(result["resolution_tier"]["value"])
        self.assertEqual(result["resolution_tier"]["confidence"], 0)


# ============================================================
# 4. API 端点测试
# ============================================================
class TestAPIDimensions(unittest.TestCase):
    BASE_URL = "http://127.0.0.1:9801"

    @classmethod
    def setUpClass(cls):
        try:
            import urllib.request
            req = urllib.request.Request(f"{cls.BASE_URL}/api/health")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status != 200:
                    raise ConnectionError()
            cls.server_available = True
        except Exception:
            cls.server_available = False

    def setUp(self):
        if not self.server_available:
            self.skipTest("API server not running")

    def _request(self, method, path, data=None):
        import urllib.request
        url = f"{self.BASE_URL}{path}"
        headers = {"Content-Type": "application/json"}
        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8")), resp.status

    def test_get_dimensions_returns_8(self):
        result, status = self._request("GET", "/api/dimensions")
        self.assertEqual(status, 200)
        self.assertEqual(result["total"], 8)
        self.assertEqual(len(result["dimensions"]), 8)

    def test_get_dimensions_enabled_returns_3(self):
        result, status = self._request("GET", "/api/dimensions/enabled")
        self.assertEqual(status, 200)
        self.assertEqual(result["total"], 3)
        for d in result["dimensions"]:
            self.assertEqual(d["is_enabled"], 1)

    def test_enable_animation(self):
        self._request("POST", "/api/dimensions/animation/enable")
        result, status = self._request("GET", "/api/dimensions/enabled")
        enabled_names = [d["name"] for d in result["dimensions"]]
        self.assertIn("animation", enabled_names)
        self._request("POST", "/api/dimensions/animation/disable")

    def test_disable_animation(self):
        self._request("POST", "/api/dimensions/animation/enable")
        self._request("POST", "/api/dimensions/animation/disable")
        result, status = self._request("GET", "/api/dimensions/enabled")
        enabled_names = [d["name"] for d in result["dimensions"]]
        self.assertNotIn("animation", enabled_names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
