import unittest
import math
from media_importer.features.scraping import (
    ConfidenceEngine, FilenameCleaner, TitleMatcher,
    CleanResult, MatchResult, ConfidenceResult,
    _calc_R, _aggregate, DEFAULT_CONFIDENCE_CONFIG,
)


class TestCalcR(unittest.TestCase):
    def test_inverse(self):
        self.assertAlmostEqual(_calc_R(1, "inverse", 10, 0.1), 1.0)
        self.assertAlmostEqual(_calc_R(5, "inverse", 10, 0.1), 0.2)
        self.assertAlmostEqual(_calc_R(10, "inverse", 10, 0.1), 0.1)

    def test_log(self):
        self.assertAlmostEqual(_calc_R(1, "log", 10, 0.1), 1.0)
        self.assertAlmostEqual(_calc_R(5, "log", 10, 0.1), 1.0 / math.log2(6))
        self.assertAlmostEqual(_calc_R(10, "log", 10, 0.1), 1.0 / math.log2(11))

    def test_sqrt(self):
        self.assertAlmostEqual(_calc_R(1, "sqrt", 10, 0.1), 1.0)
        self.assertAlmostEqual(_calc_R(4, "sqrt", 10, 0.1), 0.5)
        self.assertAlmostEqual(_calc_R(9, "sqrt", 10, 0.1), 1.0 / 3.0)

    def test_flat(self):
        self.assertEqual(_calc_R(1, "flat", 10, 0.1), 1.0)
        self.assertEqual(_calc_R(100, "flat", 10, 0.1), 1.0)

    def test_cap(self):
        self.assertAlmostEqual(_calc_R(20, "inverse", 10, 0.0), 0.1)
        self.assertAlmostEqual(_calc_R(20, "log", 10, 0.0), 1.0 / math.log2(11))

    def test_min_value(self):
        self.assertEqual(_calc_R(100, "inverse", 100, 0.2), 0.2)

    def test_zero_results(self):
        self.assertEqual(_calc_R(0, "inverse", 10, 0.1), 1.0)
        self.assertEqual(_calc_R(0, "log", 10, 0.1), 1.0)


class TestAggregate(unittest.TestCase):
    def test_geometric_mean(self):
        result = _aggregate([1.0, 1.0, 1.0], [1.0, 1.0, 1.0], "geometric_mean")
        self.assertAlmostEqual(result, 1.0)

    def test_geometric_mean_mixed(self):
        result = _aggregate([1.0, 0.9, 1.0], [1.0, 1.0, 1.0], "geometric_mean")
        expected = (1.0 * 0.9 * 1.0) ** (1.0 / 3.0)
        self.assertAlmostEqual(result, expected, places=4)

    def test_weighted_geometric_mean(self):
        result = _aggregate([1.0, 0.5], [1.0, 2.0], "geometric_mean")
        expected = (1.0 ** 1.0 * 0.5 ** 2.0) ** (1.0 / 3.0)
        self.assertAlmostEqual(result, expected, places=4)

    def test_product(self):
        result = _aggregate([1.0, 0.9, 0.8], [1.0, 1.0, 1.0], "product")
        self.assertAlmostEqual(result, 0.72)

    def test_min(self):
        result = _aggregate([1.0, 0.5, 0.8], [1.0, 1.0, 1.0], "min")
        self.assertAlmostEqual(result, 0.5)

    def test_empty(self):
        self.assertEqual(_aggregate([], [], "geometric_mean"), 1.0)


class TestConfidenceEngineCalculate(unittest.TestCase):
    def setUp(self):
        self.engine = ConfidenceEngine()

    def _make_scrape_result(self, dims):
        return {"dimensions": dims, "title": "Test Movie"}

    def _make_match_result(self, T=1.0):
        return MatchResult(level="L1", T=T, similarity=1.0, year_match=True, reason="L1")

    def test_exact_match_all_tmdb(self):
        dims = {
            "media_type": {"value": "movie", "source": "tmdb", "confidence": 1.0},
            "broad_genre": {"value": "drama", "source": "tmdb", "confidence": 1.0},
        }
        result = self.engine.calculate(
            scrape_result=self._make_scrape_result(dims),
            provider_search_info={"total_results": 1},
            clean_result=CleanResult(clean_title="Joker", year=2019),
            match_result=self._make_match_result(1.0),
        )
        self.assertAlmostEqual(result.search_conf, 1.0)
        self.assertAlmostEqual(result.data_conf, 1.0)
        self.assertAlmostEqual(result.final_confidence, 1.0)
        self.assertIsNone(result.veto)

    def test_fuzzy_match_with_log_R(self):
        dims = {
            "media_type": {"value": "tv", "source": "tmdb", "confidence": 1.0},
        }
        result = self.engine.calculate(
            scrape_result=self._make_scrape_result(dims),
            provider_search_info={"total_results": 8},
            clean_result=CleanResult(clean_title="Gintama"),
            match_result=self._make_match_result(0.72),
        )
        expected_R = 1.0 / math.log2(9)
        expected_search = 0.72 * expected_R
        self.assertAlmostEqual(result.search_conf, expected_search, places=4)
        self.assertAlmostEqual(result.data_conf, 1.0)

    def test_disabled_dims_excluded(self):
        dims = {
            "media_type": {"value": "movie", "source": "tmdb", "confidence": 1.0},
            "broad_genre": {"value": "drama", "source": "tmdb", "confidence": 1.0},
            "origin_lang": {"value": "en", "source": "tmdb", "confidence": 1.0},
        }
        result = self.engine.calculate(
            scrape_result=self._make_scrape_result(dims),
            provider_search_info={"total_results": 1},
            clean_result=CleanResult(clean_title="Test"),
            match_result=self._make_match_result(1.0),
            enabled_dims={"media_type", "broad_genre"},
        )
        self.assertIn("media_type", result.dimensions)
        self.assertIn("broad_genre", result.dimensions)
        self.assertTrue(result.dimensions["origin_lang"].get("skipped"))

    def test_veto_triggered(self):
        config = {
            "dimensions": {
                "restricted_level": {
                    "veto_threshold": 0.9,
                    "source_confidence": {"ai": 0.5},
                }
            }
        }
        engine = ConfidenceEngine(config)
        dims = {
            "restricted_level": {"value": "7-12", "source": "ai", "confidence": 0.7},
            "media_type": {"value": "movie", "source": "tmdb", "confidence": 1.0},
        }
        result = engine.calculate(
            scrape_result=self._make_scrape_result(dims),
            provider_search_info={"total_results": 1},
            clean_result=CleanResult(clean_title="Test"),
            match_result=self._make_match_result(1.0),
        )
        self.assertIsNotNone(result.veto)
        self.assertEqual(result.veto["dim_name"], "restricted_level")
        self.assertEqual(engine.get_confidence_level(result.final_confidence, result.veto), "NEEDS_REVIEW")

    def test_weighted_aggregation(self):
        config = {
            "dimensions": {
                "restricted_level": {"weight": 2.0},
                "broad_genre": {"weight": 0.5},
            }
        }
        engine = ConfidenceEngine(config)
        dims = {
            "restricted_level": {"value": "17+", "source": "tmdb", "confidence": 1.0},
            "broad_genre": {"value": "action", "source": "tmdb", "confidence": 1.0},
            "media_type": {"value": "movie", "source": "tmdb", "confidence": 1.0},
        }
        result = engine.calculate(
            scrape_result=self._make_scrape_result(dims),
            provider_search_info={"total_results": 1},
            clean_result=CleanResult(clean_title="Test"),
            match_result=self._make_match_result(1.0),
        )
        self.assertAlmostEqual(result.data_conf, 1.0)
        self.assertAlmostEqual(result.final_confidence, 1.0)

    def test_source_confidence_override(self):
        config = {
            "dimensions": {
                "restricted_level": {
                    "source_confidence": {"ai": 0.5, "missing": 0.2},
                }
            }
        }
        engine = ConfidenceEngine(config)
        dims = {
            "restricted_level": {"value": "7-12", "source": "ai", "confidence": 0.8},
        }
        result = engine.calculate(
            scrape_result=self._make_scrape_result(dims),
            provider_search_info={"total_results": 1},
            clean_result=CleanResult(clean_title="Test"),
            match_result=self._make_match_result(1.0),
        )
        self.assertAlmostEqual(result.dimensions["restricted_level"]["dim_confidence"], 0.5)

    def test_missing_dim_confidence(self):
        dims = {
            "restricted_level": None,
        }
        result = self.engine.calculate(
            scrape_result=self._make_scrape_result(dims),
            provider_search_info={"total_results": 1},
            clean_result=CleanResult(clean_title="Test"),
            match_result=self._make_match_result(1.0),
        )
        self.assertAlmostEqual(result.dimensions["restricted_level"]["dim_confidence"], 0.5)

    def test_confidence_levels(self):
        engine = ConfidenceEngine()
        self.assertEqual(engine.get_confidence_level(0.9, None), "PASS")
        self.assertEqual(engine.get_confidence_level(0.6, None), "CONFIRMING")
        self.assertEqual(engine.get_confidence_level(0.35, None), "NEEDS_REVIEW")
        self.assertEqual(engine.get_confidence_level(0.1, None), "FAILED")

    def test_veto_overrides_level(self):
        engine = ConfidenceEngine()
        veto = {"dim_name": "restricted_level", "dim_confidence": 0.5, "veto_threshold": 0.9}
        self.assertEqual(engine.get_confidence_level(0.9, veto), "NEEDS_REVIEW")

    def test_R_formula_inverse(self):
        config = {"R_formula": "inverse"}
        engine = ConfidenceEngine(config)
        dims = {"media_type": {"value": "movie", "source": "tmdb", "confidence": 1.0}}
        result = engine.calculate(
            scrape_result=self._make_scrape_result(dims),
            provider_search_info={"total_results": 5},
            clean_result=CleanResult(clean_title="Test"),
            match_result=self._make_match_result(1.0),
        )
        self.assertAlmostEqual(result.search_conf, 0.2)

    def test_aggregation_product(self):
        config = {"aggregation_method": "product"}
        engine = ConfidenceEngine(config)
        dims = {
            "media_type": {"value": "movie", "source": "tmdb", "confidence": 1.0},
            "broad_genre": {"value": "drama", "source": "tmdb", "confidence": 1.0},
            "restricted_level": {"value": "17+", "source": "ai", "confidence": 0.7},
        }
        result = engine.calculate(
            scrape_result=self._make_scrape_result(dims),
            provider_search_info={"total_results": 1},
            clean_result=CleanResult(clean_title="Test"),
            match_result=self._make_match_result(1.0),
        )
        self.assertAlmostEqual(result.data_conf, 1.0 * 1.0 * 0.7)

    def test_aggregation_min(self):
        config = {"aggregation_method": "min"}
        engine = ConfidenceEngine(config)
        dims = {
            "media_type": {"value": "movie", "source": "tmdb", "confidence": 1.0},
            "restricted_level": {"value": "17+", "source": "ai", "confidence": 0.7},
        }
        result = engine.calculate(
            scrape_result=self._make_scrape_result(dims),
            provider_search_info={"total_results": 1},
            clean_result=CleanResult(clean_title="Test"),
            match_result=self._make_match_result(1.0),
        )
        self.assertAlmostEqual(result.data_conf, 0.7)


class TestConfidenceEngineAiOnly(unittest.TestCase):
    def test_ai_only_basic(self):
        engine = ConfidenceEngine()
        dims = {
            "media_type": {"value": "movie", "source": "ai", "confidence": 0.8},
        }
        result = engine.calculate_ai_only(
            scrape_result={"dimensions": dims, "title": "Test Movie"},
            clean_result=CleanResult(clean_title="Test Movie"),
        )
        self.assertGreater(result.final_confidence, 0)
        self.assertIn("objective_cap", result.scrape_trace["confidence_calc"])

    def test_ai_only_disabled_dims(self):
        engine = ConfidenceEngine()
        dims = {
            "media_type": {"value": "movie", "source": "ai", "confidence": 0.8},
            "broad_genre": {"value": "drama", "source": "ai", "confidence": 0.9},
        }
        result = engine.calculate_ai_only(
            scrape_result={"dimensions": dims, "title": "Test"},
            clean_result=CleanResult(clean_title="Test"),
            enabled_dims={"media_type"},
        )
        self.assertIn("media_type", result.dimensions)
        self.assertTrue(result.dimensions["broad_genre"].get("skipped"))


class TestFilenameCleaner(unittest.TestCase):
    def setUp(self):
        self.cleaner = FilenameCleaner()

    def test_basic_clean(self):
        result = self.cleaner.clean("Joker.2019.1080p.BluRay.x264.mkv")
        self.assertEqual(result.clean_title, "Joker")
        self.assertEqual(result.year, 2019)

    def test_tv_show(self):
        result = self.cleaner.clean("[YYeTs].Gintama.S01E01.720p.mkv")
        self.assertEqual(result.season, 1)
        self.assertEqual(result.episode, 1)


class TestTitleMatcher(unittest.TestCase):
    def setUp(self):
        self.matcher = TitleMatcher()

    def test_exact_with_year(self):
        result = self.matcher.match(
            "Joker",
            {"title": "Joker", "release_date": "2019-10-04"},
            year=2019,
        )
        self.assertEqual(result.level, "L1")
        self.assertAlmostEqual(result.T, 1.0)

    def test_year_mismatch(self):
        result = self.matcher.match(
            "Joker",
            {"title": "Joker", "release_date": "2016-01-01"},
            year=2019,
        )
        self.assertEqual(result.level, "L4")


if __name__ == "__main__":
    unittest.main()
