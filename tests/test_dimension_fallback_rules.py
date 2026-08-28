"""ADR-0010 维度兜底回归：限制级 9 国分级映射 + 默认值机制。

- _map_restricted_level：US/GB 之外的 7 国分级数据也应被消费（DE/FR/JP/KR...）
- _apply_dimension_defaults：映射为 None 的维度应用 DB default_value；无默认值保持 None
"""
import unittest
from unittest.mock import MagicMock

from media_importer.features.scraping.dimension_manager import _map_restricted_level
from media_importer.features.scraping.metadata_scrape_flow import (
    _apply_dimension_defaults,
    _check_dimension_completeness,
)


class TestRestrictedLevelNineCountry(unittest.TestCase):
    """限制级 9 国规则增强（原实现只消费 US/GB）。"""

    def _map(self, release_dates):
        return _map_restricted_level("restricted_level", [], release_dates)

    def test_us_certification_takes_priority(self):
        dates = [
            {"iso_3166_1": "DE", "rating": "16", "release_dates": []},
            {"iso_3166_1": "US", "rating": "PG-13", "release_dates": []},
        ]
        result = self._map(dates)
        self.assertEqual(result["value"], "13-16")
        self.assertEqual(result["source_reliability"], 1.0)

    def test_germany_fsk16_mapped_when_no_us_gb(self):
        dates = [
            {"iso_3166_1": "DE", "rating": "16", "release_dates": []},
        ]
        result = self._map(dates)
        self.assertEqual(result["value"], "13-16")
        self.assertEqual(result["source_reliability"], 0.95)

    def test_france_minus_18_mapped(self):
        dates = [{"iso_3166_1": "FR", "rating": "-18", "release_dates": []}]
        result = self._map(dates)
        self.assertEqual(result["value"], "17+")

    def test_japan_r15plus_mapped(self):
        dates = [{"iso_3166_1": "JP", "rating": "R-15+", "release_dates": []}]
        result = self._map(dates)
        self.assertEqual(result["value"], "13-16")

    def test_korea_15_mapped_to_teenager(self):
        dates = [{"iso_3166_1": "KR", "rating": "15", "release_dates": []}]
        result = self._map(dates)
        self.assertEqual(result["value"], "13-16")

    def test_korea_19_mapped(self):
        dates = [{"iso_3166_1": "KR", "rating": "19", "release_dates": []}]
        result = self._map(dates)
        self.assertEqual(result["value"], "17+")

    def test_germany_fsk12_mapped(self):
        dates = [{"iso_3166_1": "DE", "rating": "12", "release_dates": []}]
        result = self._map(dates)
        self.assertEqual(result["value"], "13-16")

    def test_movie_certification_in_release_dates(self):
        dates = [
            {
                "iso_3166_1": "DE",
                "rating": "",
                "release_dates": [{"certification": "FSK 16"}],
            }
        ]
        result = self._map(dates)
        self.assertEqual(result["value"], "13-16")

    def test_priority_order_us_before_de(self):
        """US 与 DE 同时有数据时取 US。"""
        dates = [
            {"iso_3166_1": "DE", "rating": "16", "release_dates": []},
            {"iso_3166_1": "US", "rating": "R", "release_dates": []},
        ]
        result = self._map(dates)
        self.assertEqual(result["value"], "17+")
        self.assertEqual(result["source_reliability"], 1.0)

    def test_no_known_certification_returns_none(self):
        dates = [{"iso_3166_1": "BR", "rating": "14", "release_dates": []}]
        result = self._map(dates)
        self.assertIsNone(result["value"])
        self.assertEqual(result["source_reliability"], 0)


class TestDimensionDefaults(unittest.TestCase):
    """B 方案：default_value 应用逻辑。"""

    def _conn_with_defaults(self, defaults: dict) -> MagicMock:
        """返回 mock conn；get_all_dimensions 走 infrastructure.db 属性 patch。"""
        conn = MagicMock()
        rows = [
            {"name": name, "default_value": value} for name, value in defaults.items()
        ]
        from media_importer.infrastructure import db as db_mod
        patcher = unittest.mock.patch.object(
            db_mod, "get_all_dimensions", lambda _conn: rows
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return conn

    def test_none_value_replaced_by_default(self):
        conn = self._conn_with_defaults({"restricted_level": "13-16"})
        dims = {
            "media_type": {"value": "movie", "source": "tmdb"},
            "restricted_level": {"value": None, "source": "tmdb", "source_reliability": 0},
        }
        _apply_dimension_defaults(dims, conn)
        self.assertEqual(dims["restricted_level"]["value"], "13-16")
        self.assertEqual(dims["restricted_level"]["source"], "default")
        self.assertEqual(dims["restricted_level"]["source_reliability"], 0.5)
        # 已有值不覆盖
        self.assertEqual(dims["media_type"]["value"], "movie")

    def test_no_default_keeps_none_for_manual_confirm(self):
        """A 方案：无默认值 → 保持 None → completeness 不完整。"""
        conn = self._conn_with_defaults({"documentary": "false"})
        dims = {
            "documentary": {"value": None, "source": "tmdb"},
            "restricted_level": {"value": None, "source": "tmdb"},
        }
        _apply_dimension_defaults(dims, conn)
        self.assertEqual(dims["documentary"]["value"], "false")
        self.assertIsNone(dims["restricted_level"]["value"])

        completeness = _check_dimension_completeness(
            dims, {"documentary", "restricted_level"}
        )
        self.assertFalse(completeness["complete"])
        self.assertIn("restricted_level", completeness["missing_dims"])

    def test_blank_default_is_ignored(self):
        conn = self._conn_with_defaults({"restricted_level": "  "})
        dims = {"restricted_level": {"value": None, "source": "tmdb"}}
        _apply_dimension_defaults(dims, conn)
        self.assertIsNone(dims["restricted_level"]["value"])

    def test_no_conn_is_noop(self):
        dims = {"restricted_level": {"value": None, "source": "tmdb"}}
        _apply_dimension_defaults(dims, None)
        self.assertIsNone(dims["restricted_level"]["value"])


if __name__ == "__main__":
    unittest.main()
