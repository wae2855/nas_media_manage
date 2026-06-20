"""Phase P/Q/R: is_valid、selected_candidate_id 与 FAILED 状态整合测试。"""

from unittest.mock import MagicMock, patch

import pytest

from media_importer.features.scraping.match_engine import MatchEngine
from media_importer.features.scraping.match_models import MatchResult
from media_importer.features.providers.base import SearchResult, SearchItem


class TestPhaseP_IsValid:
    """Phase P: is_valid=false → FAILED"""

    def _make_engine(self):
        engine = MatchEngine()
        engine._pending_concerns = []
        engine._pending_trace = []
        engine._pending_candidates = []
        return engine

    def _make_search_item(self, item_id="1", title="Test Movie", year=2020):
        return SearchItem(
            item_id=item_id, title=title, year=year, media_type="movie",
            provider_type="tmdb", original_title=title, poster_url=None,
            vote_average=None, raw_data={},
        )

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    @patch('media_importer.features.scraping._match_tiers_impl._collect_context_impl')
    def test_is_valid_false_returns_failed(self, mock_context, mock_tier1):
        """is_valid=false → match_level=FAILED，selected_candidate=None"""
        engine = self._make_engine()
        provider = MagicMock()
        provider.__class__.__name__ = "MockProvider"
        mock_context.return_value = {"parent_folder": "Movies"}
        provider.search.return_value = SearchResult(items=[
            self._make_search_item(item_id="123", title="Random", year=2020),
        ])
        with patch('media_importer.features.scraping.llm_scraper.LLMScraper.tier2_correct') as mock_correct:
            mock_correct.return_value = {
                "is_valid": False,
                "corrected_title": "",
                "corrected_year": None,
                "media_type_hint": None,
                "certainty": "",
                "reason": "文件名为随机字符，无法识别",
                "short_reason": "随机字符文件名",
                "suggestion": "",
            }
            result = engine.match("123uyyt.mkv", [provider],
                                  video_path="/movies/123uyyt.mkv")

        assert result.match_level == "FAILED"
        assert result.selected_candidate is None
        assert result.tier_short_reason == "随机字符文件名"
        assert any("INVALID_FILENAME" in str(c.code) for c in result.concerns)

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    @patch('media_importer.features.scraping._match_tiers_impl._collect_context_impl')
    def test_is_valid_true_high_certainty_passes(self, mock_context, mock_tier1):
        """is_valid=true, certainty=high → CONTEXT_PASS"""
        engine = self._make_engine()
        provider = MagicMock()
        provider.__class__.__name__ = "MockProvider"
        mock_context.return_value = {"parent_folder": "Movies"}
        provider.search.return_value = SearchResult(items=[
            self._make_search_item(item_id="27205", title="Inception", year=2010),
        ])
        with patch('media_importer.features.scraping.llm_scraper.LLMScraper.tier2_correct') as mock_correct:
            mock_correct.return_value = {
                "is_valid": True,
                "corrected_title": "Inception",
                "corrected_year": 2010,
                "media_type_hint": "movie",
                "certainty": "high",
                "reason": "标题和年份明确",
                "short_reason": "AI 高确定性匹配通过",
                "suggestion": "Inception",
            }
            result = engine.match("Inception.2010.mkv", [provider],
                                  video_path="/movies/Inception.2010.mkv")

        assert result.match_level == "CONTEXT_PASS"
        assert result.match_tier == 2
        assert result.provider_title == "Inception"


class TestPhaseP_SelectedCandidateId:
    """Phase P: selected_candidate_id 指定候选"""

    def _make_engine(self):
        engine = MatchEngine()
        engine._pending_concerns = []
        engine._pending_trace = []
        engine._pending_candidates = [
            {
                "id": "637", "title": "La vita è bella",
                "year": 1997, "media_type": "movie",
                "provider_type": "tmdb", "vote_average": 8.6,
                "popularity": 50, "vote_count": 10000,
            },
            {
                "id": "638", "title": "Life Is Beautiful",
                "year": 2002, "media_type": "movie",
                "provider_type": "tmdb", "vote_average": 6.5,
                "popularity": 10, "vote_count": 500,
            },
        ]
        return engine

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    def test_selected_candidate_id_picks_correct(self, mock_tier1):
        """selected_candidate_id 指定 Tier1 候选 → 直接采用"""
        engine = self._make_engine()
        provider = MagicMock()
        provider.__class__.__name__ = "MockProvider"
        # 如果 selected_candidate_id 生效，不会调 provider.search
        with patch('media_importer.features.scraping._match_tiers_impl._collect_context_impl') as mock_context:
            mock_context.return_value = {"parent_folder": "Movies"}
            with patch('media_importer.features.scraping.llm_scraper.LLMScraper.tier2_correct') as mock_correct:
                mock_correct.return_value = {
                    "is_valid": True,
                    "corrected_title": "La vita è bella",
                    "corrected_year": 1997,
                    "media_type_hint": "movie",
                    "certainty": "high",
                    "selected_candidate_id": "637",
                    "reason": "匹配 Tier1 候选 637",
                    "short_reason": "AI 高确定性匹配通过",
                    "suggestion": "La vita è bella",
                }
                result = engine.match("La.vita.e.bella.1997.mkv", [provider],
                                      video_path="/movies/La.vita.e.bella.1997.mkv")

        assert result.match_level == "CONTEXT_PASS"
        assert result.selected_candidate is not None
        assert result.selected_candidate.provider_id == "637"
        assert result.selected_candidate.title == "La vita è bella"

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    def test_selected_candidate_id_not_in_tier1_falls_back(self, mock_tier1):
        """selected_candidate_id 不在 Tier1 → 按 year 匹配 Tier1 候选"""
        engine = self._make_engine()
        provider = MagicMock()
        provider.__class__.__name__ = "MockProvider"
        provider.search.return_value = SearchResult(items=[
            SearchItem(item_id="999", title="New Result", year=1997,
                       media_type="movie", provider_type="tmdb",
                       original_title="New", poster_url=None,
                       vote_average=None, raw_data={}),
        ])
        with patch('media_importer.features.scraping._match_tiers_impl._collect_context_impl') as mock_context:
            mock_context.return_value = {"parent_folder": "Movies"}
            with patch('media_importer.features.scraping.llm_scraper.LLMScraper.tier2_correct') as mock_correct:
                mock_correct.return_value = {
                    "is_valid": True,
                    "corrected_title": "La vita è bella",
                    "corrected_year": 1997,
                    "media_type_hint": "movie",
                    "certainty": "high",
                    "selected_candidate_id": "nonexistent",
                    "reason": "回退搜索",
                    "short_reason": "AI 高确定性匹配通过",
                    "suggestion": "La vita è bella",
                }
                result = engine.match("La.vita.e.bella.1997.mkv", [provider],
                                      video_path="/movies/La.vita.e.bella.1997.mkv")

        # selected_candidate_id 不在 Tier1，但 year 匹配的 Tier1 候选被采用
        assert result.match_level == "CONTEXT_PASS"
        assert result.selected_candidate is not None
        assert result.selected_candidate.provider_id == "637"


class TestPhaseQ_FailedState:
    """Phase Q: FAILED 状态透传到正式流程"""

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    @patch('media_importer.features.scraping._match_tiers_impl._collect_context_impl')
    def test_failed_no_selected_candidate(self, mock_context, mock_tier1):
        """FAILED 状态下 selected_candidate=None"""
        engine = MatchEngine()
        engine._pending_concerns = []
        engine._pending_trace = []
        mock_context.return_value = {"parent_folder": "Movies"}
        provider = MagicMock()
        provider.__class__.__name__ = "MockProvider"
        with patch('media_importer.features.scraping.llm_scraper.LLMScraper.tier2_correct') as mock_correct:
            mock_correct.return_value = {
                "is_valid": False,
                "certainty": "",
                "corrected_title": "",
                "corrected_year": None,
                "media_type_hint": None,
                "reason": "文件名为随机字符",
                "short_reason": "随机字符",
                "suggestion": "",
            }
            result = engine.match("asdfgh.mkv", [provider],
                                  video_path="/movies/asdfgh.mkv")
        assert result.selected_candidate is None
        assert result.match_level == "FAILED"

    def test_to_dict_failed_no_selected_candidate(self):
        """to_dict() FAILED 不报错"""
        r = MatchResult(match_level="FAILED", match_tier=2)
        d = r.to_dict()
        assert d["match_level"] == "FAILED"
        assert d["selected_candidate"] is None
        assert "confirm_reason" not in d
