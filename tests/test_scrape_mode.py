"""Tests for scrape_mode: provider_first / ai_only / hybrid."""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from media_importer.scraper.metadata_scrape_flow import (
    _check_dimension_completeness,
    _inject_trace_fields,
    scrape_metadata,
    scrape_series_metadata,
    _scrape_ai_only,
    _scrape_provider_first,
    _scrape_hybrid,
    VALID_SCRAPE_MODES,
)
from media_importer.scraper.llm_scraper import LLMScrapeError


# ===========================================================================
# T4.1: Dimension completeness check
# ===========================================================================

class TestCheckDimensionCompleteness:
    def test_all_dims_have_values(self):
        provider_dims = {
            "media_type": {"value": "movie", "confidence": 1.0},
            "documentary": {"value": "false", "confidence": 0.9},
            "restricted_level": {"value": "15", "confidence": 0.8},
        }
        result = _check_dimension_completeness(provider_dims, {"media_type", "documentary", "restricted_level"})
        assert result["complete"] is True
        assert result["missing_dims"] == set()
        assert result["provider_covered"] == {"media_type", "documentary", "restricted_level"}

    def test_some_dims_value_none(self):
        provider_dims = {
            "media_type": {"value": "movie", "confidence": 1.0},
            "documentary": {"value": None, "confidence": 0},
            "restricted_level": {"value": "15", "confidence": 0.8},
        }
        result = _check_dimension_completeness(provider_dims, {"media_type", "documentary", "restricted_level"})
        assert result["complete"] is False
        assert result["missing_dims"] == {"documentary"}
        assert result["provider_covered"] == {"media_type", "restricted_level"}

    def test_dim_not_in_provider_dimensions(self):
        provider_dims = {
            "media_type": {"value": "movie", "confidence": 1.0},
        }
        result = _check_dimension_completeness(provider_dims, {"media_type", "animation"})
        assert result["complete"] is False
        assert result["missing_dims"] == {"animation"}

    def test_empty_enabled_dims(self):
        result = _check_dimension_completeness({}, set())
        assert result["complete"] is True
        assert result["missing_dims"] == set()

    def test_all_dims_none(self):
        provider_dims = {
            "media_type": {"value": None, "confidence": 0},
            "documentary": {"value": None, "confidence": 0},
        }
        result = _check_dimension_completeness(provider_dims, {"media_type", "documentary"})
        assert result["complete"] is False
        assert result["missing_dims"] == {"media_type", "documentary"}


# ===========================================================================
# T4.2: Trace injection
# ===========================================================================

class TestInjectTraceFields:
    def test_inject_into_existing_trace(self):
        result = {"scrape_trace": {"existing": "data"}}
        _inject_trace_fields(result, "provider_first", True, "维度不完整")
        assert result["scrape_trace"]["scrape_mode"] == "provider_first"
        assert result["scrape_trace"]["ai_invoked"] is True
        assert result["scrape_trace"]["ai_invoke_reason"] == "维度不完整"
        assert result["scrape_trace"]["existing"] == "data"

    def test_inject_into_empty_trace(self):
        result = {}
        _inject_trace_fields(result, "ai_only", True, "纯AI刮削")
        assert result["scrape_trace"]["scrape_mode"] == "ai_only"
        assert result["scrape_trace"]["ai_invoked"] is True

    def test_inject_with_none_reason(self):
        result = {"scrape_trace": {}}
        _inject_trace_fields(result, "provider_first", False, None)
        assert result["scrape_trace"]["ai_invoked"] is False
        assert result["scrape_trace"]["ai_invoke_reason"] is None


# ===========================================================================
# T4.3: scrape_metadata dispatch
# ===========================================================================

class TestScrapeMetadataDispatch:
    def _make_scraper(self, scrape_mode="hybrid"):
        scraper = MagicMock()
        scraper.view = MagicMock()
        scraper.view.metadata = MagicMock()
        scraper.view.metadata.scrape_mode = scrape_mode
        scraper.llm_scraper = MagicMock()
        scraper.llm_scraper.enabled = True
        scraper._cleaner = MagicMock()
        scraper._cleaner.clean.return_value = MagicMock(
            clean_title="Test Movie", year=2024, season=None,
            episode=None, year_suspect=False, cjk_title=None,
        )
        scraper.providers = []
        scraper._search_all_providers.return_value = (None, [])
        scraper.confidence_engine = MagicMock()
        scraper.confidence_engine._config = {}
        scraper.confidence_engine.calculate_ai_only.return_value = MagicMock(
            final_confidence=0.5, scrape_trace={}, gate_blocked=False,
            search_conf=0, data_gate=0,
        )
        scraper.confidence_engine.calculate.return_value = MagicMock(
            final_confidence=0.8, scrape_trace={}, gate_blocked=False,
            search_conf=0.5, data_gate=0.8,
        )
        scraper.llm_scraper.scrape.return_value = {
            "title": "Test Movie", "year": 2024, "media_type": "movie",
            "confidence": 0.7,
        }
        return scraper

    def test_dispatch_hybrid(self):
        scraper = self._make_scraper("hybrid")
        result = scrape_metadata(scraper, "Test.Movie.2024.mkv")
        assert result is not None

    def test_dispatch_ai_only(self):
        scraper = self._make_scraper("ai_only")
        result = scrape_metadata(scraper, "Test.Movie.2024.mkv")
        assert result is not None
        # ai_only should NOT call provider search
        scraper._search_all_providers.assert_not_called()

    def test_dispatch_provider_first(self):
        scraper = self._make_scraper("provider_first")
        result = scrape_metadata(scraper, "Test.Movie.2024.mkv")
        assert result is not None

    def test_dispatch_invalid_mode_defaults_to_hybrid(self):
        scraper = self._make_scraper("invalid_mode")
        result = scrape_metadata(scraper, "Test.Movie.2024.mkv")
        assert result is not None

    def test_valid_scrape_modes(self):
        assert "provider_first" in VALID_SCRAPE_MODES
        assert "ai_only" in VALID_SCRAPE_MODES
        assert "hybrid" in VALID_SCRAPE_MODES


# ===========================================================================
# T4.3: provider_first mode - dimension completeness behavior
# ===========================================================================

class TestProviderFirstDimensionCompleteness:
    def _make_scraper_with_provider(self, provider_dims_complete=True):
        scraper = MagicMock()
        scraper.view = MagicMock()
        scraper.view.metadata = MagicMock()
        scraper.view.metadata.scrape_mode = "provider_first"
        scraper.llm_scraper = MagicMock()
        scraper.llm_scraper.enabled = True
        scraper._cleaner = MagicMock()
        scraper._cleaner.clean.return_value = MagicMock(
            clean_title="Test Movie", year=2024, season=None,
            episode=None, year_suspect=False, cjk_title=None,
        )

        # Provider mock
        provider = MagicMock()
        provider.provider_type = "tmdb"
        provider.display_name = "TMDb"
        search_item = MagicMock()
        search_item.item_id = "12345"
        search_item.title = "Test Movie"
        search_item.original_title = "Test Movie"
        match_result = MagicMock()
        match_result.T = 0.95
        search_info = {"original_filename": "Test.Movie.2024.mkv"}
        scraper._search_all_providers.return_value = (
            (provider, search_item, "movie", match_result, search_info), []
        )

        # Provider details
        details = MagicMock()
        details.title = "Test Movie"
        details.original_title = "Test Movie"
        details.year = 2024
        details.overview = "A test movie"
        details.genres = []
        details.vote_average = 7.5
        details.poster_url = ""
        provider.get_details.return_value = details

        # Provider dimensions
        if provider_dims_complete:
            scraper._map_provider_dimensions.return_value = {
                "documentary": {"value": "false", "confidence": 0.9, "source": "tmdb"},
                "restricted_level": {"value": "15", "confidence": 0.8, "source": "tmdb"},
                "animation": {"value": "false", "confidence": 0.9, "source": "tmdb"},
            }
        else:
            scraper._map_provider_dimensions.return_value = {
                "documentary": {"value": "false", "confidence": 0.9, "source": "tmdb"},
                "restricted_level": {"value": None, "confidence": 0, "source": "tmdb"},
                "animation": {"value": None, "confidence": 0, "source": "tmdb"},
            }

        scraper._extract_context.return_value = {"title": "Test Movie", "year": 2024}
        scraper.confidence_engine = MagicMock()
        scraper.confidence_engine._config = {"provider_match_threshold": 0.85}
        scraper.confidence_engine.calculate.return_value = MagicMock(
            final_confidence=0.9, scrape_trace={}, gate_blocked=False,
            search_conf=0.8, data_gate=0.9,
        )
        scraper.confidence_engine.calculate_ai_only.return_value = MagicMock(
            final_confidence=0.5, scrape_trace={}, gate_blocked=False,
            search_conf=0, data_gate=0,
        )
        scraper.llm_scraper.scrape_with_context.return_value = {
            "title": "Test Movie", "year": 2024, "media_type": "movie",
            "confidence": 0.7,
        }
        scraper.providers = [provider]

        return scraper

    def test_provider_dims_complete_no_ai_call(self):
        """When Provider dimensions are complete, AI should NOT be called."""
        scraper = self._make_scraper_with_provider(provider_dims_complete=True)
        mock_conn = MagicMock()
        with patch("media_importer.scraper.metadata_scrape_flow._get_enabled_dims",
                    return_value={"media_type", "documentary", "restricted_level", "animation"}):
            result = _scrape_provider_first(scraper, "Test.Movie.2024.mkv", [], mock_conn)

        # AI scrape should NOT be called
        scraper.llm_scraper.scrape_with_context.assert_not_called()
        scraper.llm_scraper.scrape.assert_not_called()
        # Result should have trace showing no AI invoked
        assert result["scrape_trace"]["ai_invoked"] is False
        assert result["scrape_trace"]["scrape_mode"] == "provider_first"

    def test_provider_dims_incomplete_ai_supplements(self):
        """When Provider dimensions are incomplete, AI should supplement missing dims."""
        scraper = self._make_scraper_with_provider(provider_dims_complete=False)
        mock_conn = MagicMock()
        with patch("media_importer.scraper.metadata_scrape_flow._get_enabled_dims",
                    return_value={"media_type", "documentary", "restricted_level", "animation"}):
            result = _scrape_provider_first(scraper, "Test.Movie.2024.mkv", [], mock_conn)

        # AI scrape_with_context should be called
        scraper.llm_scraper.scrape_with_context.assert_called_once()
        # Result should have trace showing AI invoked
        assert result["scrape_trace"]["ai_invoked"] is True
        assert result["scrape_trace"]["ai_invoke_reason"] == "维度不完整"


# ===========================================================================
# T4.3: ai_only mode
# ===========================================================================

class TestAiOnlyMode:
    def _make_scraper(self):
        scraper = MagicMock()
        scraper.view = MagicMock()
        scraper.view.metadata = MagicMock()
        scraper.view.metadata.scrape_mode = "ai_only"
        scraper.llm_scraper = MagicMock()
        scraper.llm_scraper.enabled = True
        scraper._cleaner = MagicMock()
        scraper._cleaner.clean.return_value = MagicMock(
            clean_title="Test Movie", year=2024, season=None,
            episode=None, year_suspect=False, cjk_title=None,
        )
        scraper.llm_scraper.scrape.return_value = {
            "title": "Test Movie", "year": 2024, "media_type": "movie",
            "confidence": 0.7,
        }
        scraper.confidence_engine = MagicMock()
        scraper.confidence_engine._config = {}
        scraper.confidence_engine.calculate_ai_only.return_value = MagicMock(
            final_confidence=0.7, scrape_trace={}, gate_blocked=False,
            search_conf=0, data_gate=0,
        )
        return scraper

    def test_ai_only_no_provider_search(self):
        """ai_only mode should not call any provider search."""
        scraper = self._make_scraper()
        result = _scrape_ai_only(scraper, "Test.Movie.2024.mkv", [], None)
        scraper._search_all_providers.assert_not_called()
        scraper.llm_scraper.scrape.assert_called_once()
        assert result["scrape_trace"]["scrape_mode"] == "ai_only"
        assert result["scrape_trace"]["ai_invoked"] is True

    def test_ai_only_with_year_suspect(self):
        """ai_only mode should use AI clean when year_suspect=True."""
        scraper = self._make_scraper()
        scraper._cleaner.clean.return_value.year_suspect = True
        scraper._cleaner.ai_clean.return_value = MagicMock(
            clean_title="Test Movie", year=2024,
        )
        result = _scrape_ai_only(scraper, "Test.Movie.2024(2023).mkv", [], None)
        scraper._cleaner.ai_clean.assert_called_once()

    def test_ai_only_llm_error(self):
        """ai_only mode should handle LLM errors gracefully."""
        scraper = self._make_scraper()
        scraper.llm_scraper.scrape.side_effect = LLMScrapeError("API error")
        scraper.confidence_engine.calculate_ai_only.return_value = MagicMock(
            final_confidence=0, scrape_trace={}, gate_blocked=False,
            search_conf=0, data_gate=0,
        )
        result = _scrape_ai_only(scraper, "Test.Movie.2024.mkv", [], None)
        assert result["confidence"] == 0


# ===========================================================================
# T4.4: ConfigView scrape_mode field
# ===========================================================================

class TestConfigViewScrapeMode:
    def test_default_is_hybrid(self):
        from media_importer.core.config_view import ConfigView
        view = ConfigView.from_dict({})
        assert view.metadata.scrape_mode == "hybrid"

    def test_read_provider_first(self):
        from media_importer.core.config_view import ConfigView
        view = ConfigView.from_dict({"metadata": {"scrape_mode": "provider_first"}})
        assert view.metadata.scrape_mode == "provider_first"

    def test_read_ai_only(self):
        from media_importer.core.config_view import ConfigView
        view = ConfigView.from_dict({"metadata": {"scrape_mode": "ai_only"}})
        assert view.metadata.scrape_mode == "ai_only"


# ===========================================================================
# T4.6: Config validator scrape_mode validation
# ===========================================================================

class TestConfigValidatorScrapeMode:
    def test_invalid_scrape_mode(self):
        from media_importer.core.config_validator import validate_config
        config = {"metadata": {"scrape_mode": "invalid"}, "llm": {}}
        results = validate_config(config, test_llm=False, test_hermes=False)
        details = results.get("details", [])
        mode_items = [i for i in details if "scrape_mode" in i.get("item", "")]
        assert any(i.get("status") == "error" for i in mode_items)

    def test_valid_scrape_mode(self):
        from media_importer.core.config_validator import validate_config
        config = {"metadata": {"scrape_mode": "provider_first"}, "llm": {"enabled": True, "api_key": "sk-test"}}
        results = validate_config(config, test_llm=False, test_hermes=False)
        details = results.get("details", [])
        mode_items = [i for i in details if "scrape_mode" in i.get("item", "")]
        assert any(i.get("status") == "ok" for i in mode_items)


# ===========================================================================
# T3.2: Scrape metadata dispatcher degradation
# ===========================================================================

class TestScrapeMetadataDegradation:
    """When ai_only or hybrid is selected but AI is not configured, the
    dispatcher should fall back to provider_first behavior."""

    def _make_scraper(self, scrape_mode="hybrid", ai_enabled=True):
        scraper = MagicMock()
        scraper.view = MagicMock()
        scraper.view.metadata = MagicMock()
        scraper.view.metadata.scrape_mode = scrape_mode
        scraper.llm_scraper = MagicMock()
        scraper.llm_scraper.enabled = ai_enabled
        scraper._cleaner = MagicMock()
        scraper._cleaner.clean.return_value = MagicMock(
            clean_title="Test Movie", year=2024, season=None,
            episode=None, year_suspect=False, cjk_title=None,
        )
        scraper._search_all_providers.return_value = (None, [])
        scraper.confidence_engine = MagicMock()
        scraper.confidence_engine._config = {}
        scraper.confidence_engine.calculate_ai_only.return_value = MagicMock(
            final_confidence=0.5, scrape_trace={}, gate_blocked=False,
            search_conf=0, data_gate=0,
        )
        scraper.confidence_engine.calculate.return_value = MagicMock(
            final_confidence=0.5, scrape_trace={}, gate_blocked=False,
            search_conf=0.5, data_gate=0.5,
        )
        scraper.llm_scraper.scrape.return_value = {
            "title": "Test Movie", "year": 2024, "media_type": "movie",
            "confidence": 0.7,
        }
        return scraper

    def test_ai_only_without_ai_falls_back_to_provider_first(self):
        """ai_only + AI unavailable -> dispatcher falls back to provider_first."""
        scraper = self._make_scraper(scrape_mode="ai_only", ai_enabled=False)
        with patch("media_importer.scraper.metadata_scrape_flow._get_enabled_dims",
                    return_value=None):
            result = scrape_metadata(scraper, "Test.Movie.2024.mkv")

        # Provider search was attempted (provider_first behavior)
        scraper._search_all_providers.assert_called()
        # Original scrape_mode preserved in trace
        assert result["scrape_trace"]["scrape_mode"] == "ai_only"
        # Degradation marker injected
        assert "降级" in result["scrape_trace"]["ai_invoke_reason"]
        # AI was not invoked
        assert result["scrape_trace"]["ai_invoked"] is False

    def test_hybrid_without_ai_falls_back_to_provider_first(self):
        """hybrid + AI unavailable -> dispatcher falls back to provider_first."""
        scraper = self._make_scraper(scrape_mode="hybrid", ai_enabled=False)
        with patch("media_importer.scraper.metadata_scrape_flow._get_enabled_dims",
                    return_value=None):
            result = scrape_metadata(scraper, "Test.Movie.2024.mkv")

        scraper._search_all_providers.assert_called()
        assert result["scrape_trace"]["scrape_mode"] == "hybrid"
        assert "降级" in result["scrape_trace"]["ai_invoke_reason"]
        assert result["scrape_trace"]["ai_invoked"] is False

    def test_provider_first_without_ai_no_degradation(self):
        """provider_first + AI unavailable -> normal flow, no degradation marker."""
        scraper = self._make_scraper(scrape_mode="provider_first", ai_enabled=False)
        with patch("media_importer.scraper.metadata_scrape_flow._get_enabled_dims",
                    return_value=None):
            result = scrape_metadata(scraper, "Test.Movie.2024.mkv")

        scraper._search_all_providers.assert_called()
        assert result["scrape_trace"]["scrape_mode"] == "provider_first"
        # No degradation marker
        reason = result["scrape_trace"].get("ai_invoke_reason") or ""
        assert "降级" not in reason

    def test_ai_only_with_ai_no_degradation(self):
        """ai_only + AI available -> normal ai_only flow (no Provider search)."""
        scraper = self._make_scraper(scrape_mode="ai_only", ai_enabled=True)
        with patch("media_importer.scraper.metadata_scrape_flow._get_enabled_dims",
                    return_value=None):
            result = scrape_metadata(scraper, "Test.Movie.2024.mkv")

        # ai_only never calls provider search
        scraper._search_all_providers.assert_not_called()
        assert result["scrape_trace"]["scrape_mode"] == "ai_only"
        assert "降级" not in (result["scrape_trace"].get("ai_invoke_reason") or "")

    def test_hybrid_with_ai_no_degradation(self):
        """hybrid + AI available -> normal hybrid flow (Provider + AI)."""
        scraper = self._make_scraper(scrape_mode="hybrid", ai_enabled=True)
        with patch("media_importer.scraper.metadata_scrape_flow._get_enabled_dims",
                    return_value=None):
            result = scrape_metadata(scraper, "Test.Movie.2024.mkv")

        scraper._search_all_providers.assert_called()
        assert result["scrape_trace"]["scrape_mode"] == "hybrid"
        assert "降级" not in (result["scrape_trace"].get("ai_invoke_reason") or "")


# ===========================================================================
# T3.3: Simplified mode functions (hybrid post-simplification)
# ===========================================================================

class TestHybridModeSimplified:
    """After T1.3, _scrape_hybrid no longer has ai_available branches because
    the dispatcher guarantees AI is configured."""

    def _make_scraper(self):
        scraper = MagicMock()
        scraper.view = MagicMock()
        scraper.view.metadata = MagicMock()
        scraper.view.metadata.scrape_mode = "hybrid"
        scraper.llm_scraper = MagicMock()
        scraper.llm_scraper.enabled = True
        scraper._cleaner = MagicMock()
        scraper._cleaner.clean.return_value = MagicMock(
            clean_title="Test Movie", year=2024, season=None,
            episode=None, year_suspect=False, cjk_title=None,
        )

        provider = MagicMock()
        provider.provider_type = "tmdb"
        provider.display_name = "TMDb"
        search_item = MagicMock()
        search_item.item_id = "12345"
        search_item.title = "Test Movie"
        search_item.original_title = "Test Movie"
        match_result = MagicMock()
        match_result.T = 0.95
        search_info = {"original_filename": "Test.Movie.2024.mkv"}
        scraper._search_all_providers.return_value = (
            (provider, search_item, "movie", match_result, search_info), []
        )
        details = MagicMock()
        details.title = "Test Movie"
        details.original_title = "Test Movie"
        details.year = 2024
        details.overview = "A test movie"
        details.genres = []
        details.vote_average = 7.5
        details.poster_url = ""
        provider.get_details.return_value = details
        scraper._map_provider_dimensions.return_value = {}
        scraper._extract_context.return_value = {"title": "Test Movie"}
        scraper.confidence_engine = MagicMock()
        scraper.confidence_engine._config = {"provider_match_threshold": 0.85}
        scraper.confidence_engine.calculate.return_value = MagicMock(
            final_confidence=0.9, scrape_trace={}, gate_blocked=False,
            search_conf=0.8, data_gate=0.9,
        )
        scraper.llm_scraper.scrape_with_context.return_value = {
            "title": "Test Movie", "year": 2024, "media_type": "movie",
        }
        scraper.llm_scraper.scrape.return_value = {
            "title": "Test Movie", "year": 2024, "media_type": "movie",
        }
        scraper.providers = [provider]
        return scraper

    def test_hybrid_with_provider_result_calls_ai(self):
        """hybrid + Provider result -> llm_scraper.scrape_with_context invoked."""
        scraper = self._make_scraper()
        with patch("media_importer.scraper.metadata_scrape_flow._get_enabled_dims",
                    return_value=None):
            _scrape_hybrid(scraper, "Test.Movie.2024.mkv", [], None)

        scraper.llm_scraper.scrape_with_context.assert_called_once()

    def test_hybrid_without_provider_result_calls_ai(self):
        """hybrid + no Provider result -> llm_scraper.scrape invoked (pure AI)."""
        scraper = self._make_scraper()
        scraper._search_all_providers.return_value = (None, [])
        with patch("media_importer.scraper.metadata_scrape_flow._get_enabled_dims",
                    return_value=None):
            _scrape_hybrid(scraper, "Test.Movie.2024.mkv", [], None)

        scraper.llm_scraper.scrape.assert_called_once()


# ===========================================================================
# T3.4: scrape_series_metadata() degradation
# ===========================================================================

class TestScrapeSeriesMetadataDegradation:
    """Series scraping should also degrade ai_only/hybrid -> provider_first
    when AI is not configured."""

    def _make_scraper(self, scrape_mode="hybrid", ai_enabled=True):
        scraper = MagicMock()
        scraper.view = MagicMock()
        scraper.view.metadata = MagicMock()
        scraper.view.metadata.scrape_mode = scrape_mode
        scraper.llm_scraper = MagicMock()
        scraper.llm_scraper.enabled = ai_enabled
        scraper.llm_scraper.scrape_series.return_value = {
            "title": "Test Series", "media_type": "tv", "confidence": 0.6,
        }
        scraper.llm_scraper.scrape_series_with_context.return_value = {
            "title": "Test Series", "media_type": "tv", "confidence": 0.8,
        }
        scraper.providers = [MagicMock(provider_type="tmdb", display_name="TMDb")]
        scraper._extract_context.return_value = {"title": "Test Series"}
        return scraper

    def test_series_ai_only_without_ai_falls_back(self):
        """Series ai_only + AI unavailable -> falls back to provider_first
        which attempts Provider search."""
        scraper = self._make_scraper(scrape_mode="ai_only", ai_enabled=False)
        # Provider search returns no items to force the fallback path
        search_result = MagicMock()
        search_result.items = []
        scraper.providers[0].search.return_value = search_result

        result = scrape_series_metadata(scraper, "Test Series")

        # Provider search was attempted (provider_first behavior)
        scraper.providers[0].search.assert_called()
        # After degradation, AI is not invoked
        assert result["scrape_trace"].get("ai_invoked") is False

    def test_series_hybrid_without_ai_falls_back(self):
        """Series hybrid + AI unavailable -> falls back to provider_first."""
        scraper = self._make_scraper(scrape_mode="hybrid", ai_enabled=False)
        search_result = MagicMock()
        search_result.items = []
        scraper.providers[0].search.return_value = search_result

        result = scrape_series_metadata(scraper, "Test Series")

        scraper.providers[0].search.assert_called()
        assert result["scrape_trace"].get("ai_invoked") is False


# ===========================================================================
# T3.5: Config validator degradation
# ===========================================================================

class TestConfigValidatorDegradation:
    """Validate that ai_only + missing fields is an error, hybrid + missing
    fields is a warning, both based on field completeness (not the legacy
    llm.enabled flag)."""

    def test_ai_only_without_llm_fields_is_error(self):
        from media_importer.core.config_validator import validate_config
        config = {
            "metadata": {"scrape_mode": "ai_only"},
            "llm": {"api_key": "", "base_url": "", "model": ""},
        }
        results = validate_config(config, test_llm=False, test_hermes=False)
        details = results.get("details", [])
        llm_items = [i for i in details if "scrape_mode_llm" in i.get("item", "")]
        assert any(i.get("status") == "error" for i in llm_items)

    def test_hybrid_without_llm_fields_is_warning(self):
        from media_importer.core.config_validator import validate_config
        config = {
            "metadata": {"scrape_mode": "hybrid"},
            "llm": {"api_key": "", "base_url": "", "model": ""},
        }
        results = validate_config(config, test_llm=False, test_hermes=False)
        details = results.get("details", [])
        hybrid_items = [i for i in details if "scrape_mode_hybrid" in i.get("item", "")]
        assert any(i.get("status") == "warning" for i in hybrid_items)


class TestScrapeMetadataForceMode:
    def _make_scraper(self, scrape_mode="provider_first", ai_enabled=True):
        scraper = MagicMock()
        scraper.view = MagicMock()
        scraper.view.metadata = MagicMock()
        scraper.view.metadata.scrape_mode = scrape_mode
        scraper.llm_scraper = MagicMock()
        scraper.llm_scraper.enabled = ai_enabled
        scraper._cleaner = MagicMock()
        scraper._cleaner.clean.return_value = MagicMock(
            clean_title="Test Movie", year=2024, season=None,
            episode=None, year_suspect=False, cjk_title=None,
        )
        scraper.providers = []
        scraper._search_all_providers.return_value = (None, [])
        scraper.confidence_engine = MagicMock()
        scraper.confidence_engine._config = {}
        scraper.confidence_engine.calculate_ai_only.return_value = MagicMock(
            final_confidence=0.5, scrape_trace={}, gate_blocked=False,
            search_conf=0, data_gate=0, confidence_detail={},
        )
        scraper.confidence_engine.calculate.return_value = MagicMock(
            final_confidence=0.8, scrape_trace={}, gate_blocked=False,
            search_conf=0.5, data_gate=0.8, confidence_detail={},
        )
        scraper.llm_scraper.scrape.return_value = {
            "title": "Test Movie", "year": 2024, "media_type": "movie",
            "confidence": 0.7,
        }
        return scraper

    def test_force_ai_only_overrides_configured_provider_first(self):
        scraper = self._make_scraper("provider_first", ai_enabled=True)
        result = scrape_metadata(scraper, "Test.Movie.2024.mkv", force_mode="ai_only")
        assert result["scrape_trace"]["scrape_mode"] == "ai_only"
        scraper._search_all_providers.assert_not_called()

    def test_force_hybrid_without_ai_returns_error_not_provider_fallback(self):
        scraper = self._make_scraper("provider_first", ai_enabled=False)
        result = scrape_metadata(scraper, "Test.Movie.2024.mkv", force_mode="hybrid")
        assert result["error"].startswith("AI 刮削未配置")
        assert result["scrape_trace"]["scrape_mode"] == "hybrid"
        scraper._search_all_providers.assert_not_called()

    def test_configured_hybrid_without_ai_still_falls_back(self):
        scraper = self._make_scraper("hybrid", ai_enabled=False)
        result = scrape_metadata(scraper, "Test.Movie.2024.mkv")
        assert result["scrape_trace"]["scrape_mode"] == "hybrid"
        assert result["scrape_trace"]["ai_invoke_reason"] == "AI未配置-已降级为provider_first"


class TestScrapePreviewHelpers:
    def test_decorate_scrape_preview_mode_from_result_fields(self):
        handler = type("Handler", (), {})()
        handler._decorate_scrape_preview_mode = __import__(
            "media_importer.api.tmdb_handlers",
            fromlist=["TMDbHandlersMixin"],
        ).TMDbHandlersMixin._decorate_scrape_preview_mode.__get__(handler)
        mode_data = {
            "result": {
                "confidence": 0.82,
                "confidence_detail": {"formula": "T × R × data_gate", "T": 0.9},
                "confidence_search": 0.82,
                "confidence_data_gate": 1.0,
                "provider_type": "tmdb",
                "provider_id": "123",
                "scrape_trace": {
                    "ai_invoked": True,
                    "ai_invoke_reason": "联合刮削",
                    "search_enhanced": False,
                },
            },
            "elapsed": 1.2,
        }
        handler._decorate_scrape_preview_mode(mode_data)
        assert mode_data["confidence_detail"]["formula"] == "T × R × data_gate"
        assert mode_data["ai_invoked"] is True
        assert mode_data["provider_type"] == "tmdb"
        assert mode_data["provider_id"] == "123"

    def test_build_scrape_preview_recommendation_picks_highest_confidence(self):
        handler = type("Handler", (), {})()
        handler._build_scrape_preview_recommendation = __import__(
            "media_importer.api.tmdb_handlers",
            fromlist=["TMDbHandlersMixin"],
        ).TMDbHandlersMixin._build_scrape_preview_recommendation.__get__(handler)
        recommendation = handler._build_scrape_preview_recommendation({
            "provider_first": {"result": {"confidence": 0.6}},
            "ai_only": {"result": {"confidence": 0.7}},
            "hybrid": {"result": {"confidence": 0.9}},
        })
        assert recommendation["best_mode"] == "hybrid"
        assert recommendation["best_confidence"] == 0.9