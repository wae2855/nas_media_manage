#!/usr/bin/env python3
"""dimension_manager.py 纯函数聚合逻辑单测。

覆盖维度匹配引擎的核心纯函数：
- CERTIFICATION_TO_LEVEL: 分级到年龄段映射
- _extract_genre_ids: 多格式 genres 输入归一化
- _map_region_v2: 国家码匹配（country_codes）
- _map_origin_lang_v2: 语言匹配（direct_match）
- _map_genre_by_rules: 按 priority 排序的 genre 匹配
- _map_bool_genre: 纪录片/动画类 bool genre
- map_provider_to_dimension: match_type 分发入口
"""

# ruff: noqa: E402
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from media_importer.features.scraping.dimension_manager import (
    CERTIFICATION_TO_LEVEL,
    _extract_genre_ids,
    _map_bool_genre,
    _map_genre_by_rules,
    _map_origin_lang_v2,
    _map_region_v2,
    map_provider_to_dimension,
)


class TestCertificationToLevel(unittest.TestCase):
    def test_mappings_cover_us_and_cn_systems(self):
        """US 系统：G/PG/PG-13/R/NC-17，CN 系统：/U/12A/12/15/18，TV：TV-Y/TV-MA。"""
        self.assertEqual(CERTIFICATION_TO_LEVEL["G"], "0-6")
        self.assertEqual(CERTIFICATION_TO_LEVEL["PG"], "7-12")
        self.assertEqual(CERTIFICATION_TO_LEVEL["PG-13"], "13-16")
        self.assertEqual(CERTIFICATION_TO_LEVEL["R"], "17+")
        self.assertEqual(CERTIFICATION_TO_LEVEL["NC-17"], "17+")
        self.assertEqual(CERTIFICATION_TO_LEVEL["U"], "0-6")
        self.assertEqual(CERTIFICATION_TO_LEVEL["12"], "13-16")
        self.assertEqual(CERTIFICATION_TO_LEVEL["18"], "17+")

    def test_tv_age_groups(self):
        self.assertEqual(CERTIFICATION_TO_LEVEL["TV-Y"], "0-6")
        self.assertEqual(CERTIFICATION_TO_LEVEL["TV-Y7"], "7-12")
        self.assertEqual(CERTIFICATION_TO_LEVEL["TV-14"], "13-16")
        self.assertEqual(CERTIFICATION_TO_LEVEL["TV-MA"], "17+")

    def test_unknown_certification_is_not_in_table(self):
        self.assertNotIn("XYZ", CERTIFICATION_TO_LEVEL)
        self.assertNotIn("", CERTIFICATION_TO_LEVEL)


class TestExtractGenreIds(unittest.TestCase):
    def test_dict_genres_with_id(self):
        genres = [{"id": 18}, {"id": 28}]
        self.assertEqual(_extract_genre_ids({"genres": genres}), {"18", "28"})

    def test_int_genres(self):
        self.assertEqual(_extract_genre_ids({"genres": [18, 28]}), {"18", "28"})

    def test_str_genres(self):
        self.assertEqual(_extract_genre_ids({"genres": ["18", "28"]}), {"18", "28"})

    def test_mixed_formats(self):
        genres = [{"id": 18}, 28, "35"]
        self.assertEqual(_extract_genre_ids({"genres": genres}), {"18", "28", "35"})

    def test_dict_genres_without_id_is_ignored(self):
        genres = [{"name": "Drama"}, {"id": 18}]
        self.assertEqual(_extract_genre_ids({"genres": genres}), {"18"})

    def test_missing_genres_returns_empty_set(self):
        self.assertEqual(_extract_genre_ids({}), set())

    def test_empty_genres_returns_empty_set(self):
        self.assertEqual(_extract_genre_ids({"genres": []}), set())


class TestMapRegionV2(unittest.TestCase):
    def test_first_country_matches_returns_value(self):
        mapping = {
            "field": "origin_country",
            "match_rules": {
                "美国": {"codes": ["US"]},
                "日本": {"codes": ["JP"]},
            },
        }
        result = _map_region_v2("region", mapping, {"origin_country": ["JP", "US"]})
        self.assertEqual(result["value"], "日本")
        self.assertEqual(result["source_reliability"], 1.0)
        self.assertEqual(result["name"], "region")

    def test_no_match_falls_to_other(self):
        mapping = {
            "field": "origin_country",
            "match_rules": {
                "美国": {"codes": ["US"]},
            },
        }
        result = _map_region_v2("region", mapping, {"origin_country": ["DE"]})
        self.assertEqual(result["value"], "other")
        self.assertEqual(result["source_reliability"], 1.0)

    def test_empty_origin_country_returns_none(self):
        mapping = {"match_rules": {"美国": {"codes": ["US"]}}}
        result = _map_region_v2("region", mapping, {"origin_country": []})
        self.assertIsNone(result["value"])
        self.assertEqual(result["source_reliability"], 0)

    def test_missing_origin_country_field_returns_none(self):
        mapping = {"field": "origin_country", "match_rules": {"美国": {"codes": ["US"]}}}
        result = _map_region_v2("region", mapping, {})
        self.assertIsNone(result["value"])

    def test_string_origin_country(self):
        mapping = {
            "field": "origin_country",
            "match_rules": {"美国": {"codes": ["US"]}},
        }
        result = _map_region_v2("region", mapping, {"origin_country": "US"})
        self.assertEqual(result["value"], "美国")


class TestMapOriginLangV2(unittest.TestCase):
    def test_matched_language_returns_value(self):
        mapping = {
            "field": "original_language",
            "match_rules": {
                "中文": {"languages": ["zh", "zh-CN", "zh-TW"]},
                "英文": {"languages": ["en"]},
            },
        }
        result = _map_origin_lang_v2("language", mapping, {"original_language": "zh"})
        self.assertEqual(result["value"], "中文")
        self.assertEqual(result["source_reliability"], 1.0)

    def test_unmatched_language_falls_to_other(self):
        mapping = {
            "match_rules": {"中文": {"languages": ["zh"]}},
        }
        result = _map_origin_lang_v2("language", mapping, {"original_language": "ja"})
        self.assertEqual(result["value"], "other")

    def test_missing_language_returns_none(self):
        mapping = {"match_rules": {"中文": {"languages": ["zh"]}}}
        result = _map_origin_lang_v2("language", mapping, {})
        self.assertIsNone(result["value"])
        self.assertEqual(result["source_reliability"], 0)

    def test_empty_language_returns_none(self):
        mapping = {"match_rules": {"中文": {"languages": ["zh"]}}}
        result = _map_origin_lang_v2("language", mapping, {"original_language": ""})
        self.assertIsNone(result["value"])


class TestMapGenreByRules(unittest.TestCase):
    def test_match_by_genre_id(self):
        mapping = {
            "match_rules": {
                "动作": {"ids": [28, 12]},
                "喜剧": {"ids": [35]},
            },
        }
        value_list = [
            {"value": "动作", "priority": 1},
            {"value": "喜剧", "priority": 2},
        ]
        result = _map_genre_by_rules("genre", mapping, value_list, {"genres": [{"id": 28}]})
        self.assertEqual(result["value"], "动作")
        self.assertEqual(result["source_reliability"], 0.9)

    def test_priority_ordering(self):
        """priority 数字小的优先匹配。"""
        mapping = {
            "match_rules": {
                "动作": {"ids": [28]},
                "冒险": {"ids": [28]},
            },
        }
        value_list = [
            {"value": "冒险", "priority": 1},
            {"value": "动作", "priority": 2},
        ]
        result = _map_genre_by_rules("genre", mapping, value_list, {"genres": [{"id": 28}]})
        self.assertEqual(result["value"], "冒险")

    def test_no_genres_returns_none(self):
        mapping = {"match_rules": {"动作": {"ids": [28]}}}
        value_list = [{"value": "动作", "priority": 1}]
        result = _map_genre_by_rules("genre", mapping, value_list, {"genres": []})
        self.assertIsNone(result["value"])
        self.assertEqual(result["source_reliability"], 0)

    def test_no_matching_genre_falls_to_other(self):
        """value_list 含字面量 "other" 时，genre 不命中会回退到 "other"。"""
        mapping = {
            "match_rules": {
                "动作": {"ids": [28]},
            },
        }
        value_list = [
            {"value": "动作", "priority": 1},
            {"value": "other", "priority": 99},
        ]
        result = _map_genre_by_rules("genre", mapping, value_list, {"genres": [{"id": 9999}]})
        self.assertEqual(result["value"], "other")
        self.assertEqual(result["source_reliability"], 0.9)

    def test_default_other_when_no_other_value_in_list(self):
        mapping = {"match_rules": {"动作": {"ids": [28]}}}
        value_list = [{"value": "动作", "priority": 1}]
        result = _map_genre_by_rules("genre", mapping, value_list, {"genres": [{"id": 9999}]})
        self.assertEqual(result["value"], "other")
        self.assertEqual(result["source_reliability"], 0.9)


class TestMapBoolGenre(unittest.TestCase):
    def test_true_when_genre_in_true_ids(self):
        mapping = {"match_rules": {"true": {"ids": [99]}}}
        result = _map_bool_genre("documentary", mapping, {"genres": [{"id": 99}]})
        self.assertEqual(result["value"], "true")
        self.assertEqual(result["source_reliability"], 1.0)

    def test_false_when_genre_present_but_not_in_true_ids(self):
        mapping = {"match_rules": {"true": {"ids": [99]}}}
        result = _map_bool_genre("documentary", mapping, {"genres": [{"id": 28}]})
        self.assertEqual(result["value"], "false")
        self.assertEqual(result["source_reliability"], 0.9)

    def test_none_when_no_genres(self):
        mapping = {"match_rules": {"true": {"ids": [99]}}}
        result = _map_bool_genre("documentary", mapping, {"genres": []})
        self.assertIsNone(result["value"])
        self.assertEqual(result["source_reliability"], 0)

    def test_name_is_preserved(self):
        mapping = {"match_rules": {"true": {"ids": [99]}}}
        result = _map_bool_genre("animation", mapping, {"genres": [{"id": 99}]})
        self.assertEqual(result["name"], "animation")


class TestMapProviderToDimensionDispatch(unittest.TestCase):
    def test_genre_ids_match_type_routes_to_bool_for_documentary(self):
        dim = {
            "name": "documentary",
            "value_list": [],
            "provider_mappings": {
                "tmdb": {
                    "match_type": "genre_ids",
                    "match_rules": {"true": {"ids": [99]}},
                }
            },
        }
        result = map_provider_to_dimension(dim, {"genres": [{"id": 99}]})
        self.assertEqual(result["value"], "true")

    def test_genre_ids_match_type_routes_to_genre_rules(self):
        dim = {
            "name": "type",
            "value_list": [{"value": "动作", "priority": 1}],
            "provider_mappings": {
                "tmdb": {
                    "match_type": "genre_ids",
                    "match_rules": {"动作": {"ids": [28]}},
                }
            },
        }
        result = map_provider_to_dimension(dim, {"genres": [{"id": 28}]})
        self.assertEqual(result["value"], "动作")

    def test_country_codes_match_type_routes_to_region(self):
        dim = {
            "name": "region",
            "value_list": [],
            "provider_mappings": {
                "tmdb": {
                    "match_type": "country_codes",
                    "field": "origin_country",
                    "match_rules": {"美国": {"codes": ["US"]}},
                }
            },
        }
        result = map_provider_to_dimension(dim, {"origin_country": ["US"]})
        self.assertEqual(result["value"], "美国")

    def test_direct_match_routes_to_origin_lang(self):
        dim = {
            "name": "language",
            "value_list": [],
            "provider_mappings": {
                "tmdb": {
                    "match_type": "direct_match",
                    "field": "original_language",
                    "match_rules": {"中文": {"languages": ["zh"]}},
                }
            },
        }
        result = map_provider_to_dimension(dim, {"original_language": "zh"})
        self.assertEqual(result["value"], "中文")

    def test_unknown_match_type_returns_none(self):
        dim = {
            "name": "x",
            "value_list": [],
            "provider_mappings": {
                "tmdb": {"match_type": "unknown_type", "match_rules": {}},
            },
        }
        result = map_provider_to_dimension(dim, {})
        self.assertIsNone(result["value"])
        self.assertEqual(result["source_reliability"], 0)

    def test_missing_provider_mappings_returns_none(self):
        dim = {"name": "x", "value_list": [], "provider_mappings": {}}
        result = map_provider_to_dimension(dim, {})
        self.assertIsNone(result["value"])

    def test_provider_mappings_not_a_dict_returns_none(self):
        dim = {"name": "x", "value_list": [], "provider_mappings": "invalid"}
        result = map_provider_to_dimension(dim, {})
        self.assertIsNone(result["value"])

    def test_provider_type_selection(self):
        """不同 provider_type 取不同的 mapping。"""
        dim = {
            "name": "language",
            "value_list": [],
            "provider_mappings": {
                "tmdb": {
                    "match_type": "direct_match",
                    "field": "original_language",
                    "match_rules": {"英文": {"languages": ["en"]}},
                },
                "douban": {
                    "match_type": "direct_match",
                    "field": "original_language",
                    "match_rules": {"中文": {"languages": ["zh"]}},
                },
            },
        }
        tmdb_result = map_provider_to_dimension(dim, {"original_language": "en"}, provider_type="tmdb")
        douban_result = map_provider_to_dimension(dim, {"original_language": "zh"}, provider_type="douban")
        self.assertEqual(tmdb_result["value"], "英文")
        self.assertEqual(douban_result["value"], "中文")
