"""第二级匹配引擎分流单元测试（tier2 新方案）。"""

from unittest.mock import MagicMock, patch

import pytest

from media_importer.features.scraping.match_engine import MatchEngine
from media_importer.features.scraping.match_models import MatchResult, MatchConcern
from media_importer.features.scraping.confidence_models import CleanResult
from media_importer.features.providers.base import SearchResult, SearchItem


class TestTier2MatchEngine:
    """验证 _tier2_context_match 按确定性分流逻辑。"""

    def _make_engine(self):
        engine = MatchEngine()
        engine._pending_concerns = []
        engine._pending_trace = []
        return engine

    def _make_search_item(self, item_id="1", title="Test Movie", year=2020):
        return SearchItem(
            item_id=item_id, title=title, year=year, media_type="movie",
            provider_type="tmdb", original_title=title, poster_url=None,
            vote_average=None, raw_data={},
        )

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    @patch('media_importer.features.scraping._match_tiers_impl._collect_context_impl')
    def test_tc09_high_certainty_returns_context_pass(self, mock_context, mock_tier1):
        """TC-09: high certainty → _tier2_context_match 返回 CONTEXT_PASS"""
        engine = self._make_engine()
        provider = MagicMock()
        provider.__class__.__name__ = "MockProvider"
        mock_context.return_value = {"parent_folder": "Movies"}
        provider.search.return_value = SearchResult(items=[
            self._make_search_item(item_id="27205", title="Inception", year=2010),
        ])
        with patch('media_importer.scraper.llm_scraper.LLMScraper.tier2_correct') as mock_correct:
            mock_correct.return_value = {
                "corrected_title": "Inception",
                "corrected_year": 2010,
                "media_type_hint": "movie",
                "certainty": "high",
                "reason": "标题和年份明确",
                "suggestion": "Inception",
            }
            result = engine.match(
                "Inception.2010.1080p.mkv", [provider],
                video_path="/movies/Inception.2010.1080p.mkv"
            )
        assert result.match_level == "CONTEXT_PASS"
        assert result.match_tier == 2
        assert result.provider_title == "Inception"

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    @patch('media_importer.features.scraping._match_tiers_impl._collect_context_impl')
    def test_tc10_medium_certainty_returns_needs_confirm(self, mock_context, mock_tier1):
        """TC-10: medium certainty → _tier2_context_match 返回 NEEDS_CONFIRM"""
        engine = self._make_engine()
        provider = MagicMock()
        provider.__class__.__name__ = "MockProvider"
        mock_context.return_value = {"parent_folder": "Movies"}
        provider.search.return_value = SearchResult(items=[
            self._make_search_item(item_id="1", title="Some Movie", year=2020),
        ])
        with patch('media_importer.scraper.llm_scraper.LLMScraper.tier2_correct') as mock_correct:
            mock_correct.return_value = {
                "corrected_title": "Some Movie",
                "corrected_year": 2020,
                "media_type_hint": "movie",
                "certainty": "medium",
                "reason": "中等确定性，标题可能为 Some Movie",
                "suggestion": "Some Movie",
            }
            result = engine.match(
                "Some.Movie.2020.mkv", [provider],
                video_path="/movies/Some.Movie.2020.mkv"
            )
        assert result.match_level == "NEEDS_CONFIRM"
        assert result.match_tier == 2
        assert result.confirm_reason != ""
        assert len(result.candidates) > 0

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    @patch('media_importer.features.scraping._match_tiers_impl._collect_context_impl')
    def test_tc11_low_certainty_returns_needs_confirm_no_search(self, mock_context, mock_tier1):
        """TC-11: low certainty → NEEDS_CONFIRM，不搜Provider"""
        engine = self._make_engine()
        provider = MagicMock()
        provider.__class__.__name__ = "MockProvider"
        mock_context.return_value = {}
        with patch('media_importer.scraper.llm_scraper.LLMScraper.tier2_correct') as mock_correct:
            mock_correct.return_value = {
                "corrected_title": "Unknown",
                "corrected_year": None,
                "media_type_hint": None,
                "certainty": "low",
                "reason": "无法确定标题",
                "suggestion": "Unknown",
            }
            result = engine._tier2_context_match(
                "Unknown", "", None, None, None, [provider],
                "/downloads/RandomFile.mkv"
            )
        assert result is not None
        assert result.match_level == "NEEDS_CONFIRM"
        assert result.match_tier == 2
        assert len(result.candidates) == 0
        provider.search.assert_not_called()

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    @patch('media_importer.features.scraping._match_tiers_impl._collect_context_impl')
    def test_tc12_ai_exception_fallthrough(self, mock_context, mock_tier1):
        """TC-12: AI异常 → _tier2_context_match 返回 None（进入第三级）"""
        engine = self._make_engine()
        provider = MagicMock()
        provider.__class__.__name__ = "MockProvider"
        mock_context.return_value = {"parent_folder": "Movies"}
        with patch('media_importer.scraper.llm_scraper.LLMScraper') as MockLLM:
            MockLLM.return_value.tier2_correct.side_effect = Exception("API timeout")
            result = engine.match(
                "Test.2020.mkv", [provider],
                video_path="/movies/Test.2020.mkv"
            )
        assert result.match_level == "NEEDS_CONFIRM"
        assert result.match_tier == 3

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    @patch('media_importer.features.scraping._match_tiers_impl._collect_context_impl')
    def test_high_certainty_no_provider_result_falls_to_medium(self, mock_context, mock_tier1):
        """high certainty 但 Provider 无结果 → 降级为 medium"""
        engine = self._make_engine()
        provider = MagicMock()
        provider.__class__.__name__ = "MockProvider"
        mock_context.return_value = {}
        provider.search.return_value = SearchResult(items=[])
        with patch('media_importer.scraper.llm_scraper.LLMScraper.tier2_correct') as mock_correct:
            mock_correct.return_value = {
                "corrected_title": "RareFilm",
                "corrected_year": 2020,
                "media_type_hint": "movie",
                "certainty": "high",
                "reason": "高确定性但可能稀有",
                "suggestion": "RareFilm",
            }
            result = engine.match(
                "RareFilm.2020.mkv", [provider],
                video_path="/downloads/RareFilm.2020.mkv"
            )
        assert result.match_level == "NEEDS_CONFIRM"

    def test_collect_context_with_source_dir(self):
        """_collect_context_impl 从 source_dir 提取 path_segments"""
        from media_importer.features.scraping._match_tiers_impl import _collect_context_impl
        context = _collect_context_impl("/movies", "/movies/action/2024/Test.2024.mkv")
        assert "path_segments" in context
        assert context["path_segments"] == ["action", "2024"]
