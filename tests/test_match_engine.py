"""三级匹配引擎单元测试。"""

import unittest
from unittest.mock import MagicMock, patch
from media_importer.features.scraping.match_engine import MatchEngine
from media_importer.features.scraping.match_models import MatchResult, MatchConcern
from media_importer.features.scraping.confidence_models import CleanResult
from media_importer.features.providers.base import SearchResult


class TestTier1ExactMatch(unittest.TestCase):
    """第一级精确匹配测试。"""

    def setUp(self):
        self.engine = MatchEngine()
        self.provider = MagicMock()
        self.provider.__class__.__name__ = "MockProvider"

    def test_english_title_with_year_exact_match(self):
        """英文名+年份精确匹配 → AUTO_PASS"""
        from media_importer.features.providers.base import SearchItem
        self.provider.search.return_value = SearchResult(items=[
            SearchItem(
                item_id="27205", title="Inception", year=2010, media_type="movie",
                provider_type="tmdb", original_title="Inception", poster_url=None,
                vote_average=None, raw_data={},
            )
        ])
        with patch.object(self.engine.title_matcher, 'match_standard') as mock_match:
            mock_match.return_value = MagicMock(level="L1", T=1.0)
            result = self.engine.match("Inception.2010.1080p.BluRay.mkv", [self.provider])
        self.assertEqual(result.match_level, "AUTO_PASS")
        self.assertEqual(result.match_tier, 1)

    def test_no_year_multiple_exact_matches(self):
        """无年份多同名 → NEEDS_CONFIRM + NO_YEAR_MULTI_MATCH"""
        from media_importer.features.providers.base import SearchItem
        self.provider.search.return_value = SearchResult(items=[
            SearchItem(item_id="1", title="Spider-Man", year=2002, media_type="movie",
                       provider_type="tmdb", original_title="Spider-Man", poster_url=None,
                       vote_average=None, raw_data={}),
            SearchItem(item_id="2", title="Spider-Man", year=2017, media_type="movie",
                       provider_type="tmdb", original_title="Spider-Man", poster_url=None,
                       vote_average=None, raw_data={}),
        ])
        with patch.object(self.engine.title_matcher, 'match_standard') as mock_match:
            mock_match.return_value = MagicMock(level="L3", T=0.7)
            result = self.engine.match("Spider-Man.mkv", [self.provider])
        self.assertEqual(result.match_level, "NEEDS_CONFIRM")
        concern_codes = [c.code for c in result.concerns]
        self.assertIn("NO_YEAR_MULTI_MATCH", concern_codes)

    def test_no_title_extracted(self):
        """无法提取标题 → NEEDS_CONFIRM + NO_TITLE"""
        with patch.object(self.engine.filename_cleaner, 'clean') as mock_clean:
            mock_clean.return_value = CleanResult(clean_title="", cjk_title="")
            result = self.engine.match("video.mkv", [self.provider])
        self.assertEqual(result.match_level, "NEEDS_CONFIRM")
        concern_codes = [c.code for c in result.concerns]
        self.assertIn("NO_TITLE", concern_codes)

    def test_provider_search_exception(self):
        """Provider 搜索异常 → 不崩溃，进入第三级"""
        self.provider.search.side_effect = Exception("API timeout")
        with patch.object(self.engine.filename_cleaner, 'clean') as mock_clean:
            mock_clean.return_value = CleanResult(clean_title="Test", cjk_title="", year=2020)
            result = self.engine.match("Test.2020.mkv", [self.provider])
        self.assertIn(result.match_level, ("NEEDS_CONFIRM",))

    def test_no_provider_results(self):
        """Provider 无结果 → NEEDS_CONFIRM + NO_PROVIDER_RESULT"""
        self.provider.search.return_value = SearchResult(items=[])
        with patch.object(self.engine.filename_cleaner, 'clean') as mock_clean:
            mock_clean.return_value = CleanResult(clean_title="Test", cjk_title="", year=2023)
            result = self.engine.match("Test.2023.mkv", [self.provider])
        self.assertEqual(result.match_level, "NEEDS_CONFIRM")
        concern_codes = [c.code for c in result.concerns]
        self.assertIn("NO_PROVIDER_RESULT", concern_codes)

    def test_cjk_title_priority(self):
        """CJK 标题优先搜索"""
        from media_importer.features.providers.base import SearchItem
        self.provider.search.return_value = SearchResult(items=[
            SearchItem(item_id="123", title="The Wandering Earth", year=2019, media_type="movie",
                       provider_type="tmdb", original_title="The Wandering Earth", poster_url=None,
                       vote_average=None, raw_data={}),
        ])
        with patch.object(self.engine.title_matcher, 'match_standard') as mock_match:
            mock_match.return_value = MagicMock(level="L1", T=1.0)
            with patch.object(self.engine.filename_cleaner, 'clean') as mock_clean:
                mock_clean.return_value = CleanResult(clean_title="The Wandering Earth", cjk_title="流浪地球", year=2019)
                result = self.engine.match("流浪地球.2019.mkv", [self.provider])
        self.assertEqual(result.match_level, "AUTO_PASS")
        # 验证 provider 用 cjk_title 搜索
        call_args = self.provider.search.call_args_list
        self.assertEqual(call_args[0][0][0], "流浪地球")


class TestConcernGeneration(unittest.TestCase):
    """疑虑原因生成测试。"""

    def test_concern_has_required_fields(self):
        """每个 concern 都有 code + message + detail"""
        concern = MatchConcern(
            code="NO_YEAR_MULTI_MATCH",
            message="找到 3 部同名作品",
            detail="搜索 'Spider-Man' 返回 3 条精确匹配",
        )
        self.assertEqual(concern.code, "NO_YEAR_MULTI_MATCH")
        self.assertTrue(concern.message)
        self.assertTrue(concern.detail)

    def test_all_concern_codes_defined(self):
        """7 种 concern.code 都已定义"""
        valid_codes = {
            "NO_YEAR_MULTI_MATCH", "YEAR_MISMATCH", "FUZZY_TITLE",
            "NO_PROVIDER_RESULT", "NO_TITLE", "CONFLICTING_INFO", "AI_UNCERTAIN",
        }
        self.assertEqual(len(valid_codes), 7)


class TestMatchResultSerialization(unittest.TestCase):
    """MatchResult 序列化测试。"""

    def test_to_dict(self):
        """MatchResult.to_dict() 可序列化"""
        result = MatchResult(
            match_level="AUTO_PASS",
            provider_id=27205,
            provider_title="Inception",
            match_tier=1,
            concerns=[MatchConcern(code="NO_TITLE", message="test", detail="test")],
        )
        d = result.to_dict()
        self.assertEqual(d["match_level"], "AUTO_PASS")
        self.assertEqual(len(d["concerns"]), 1)
        self.assertEqual(d["concerns"][0]["code"], "NO_TITLE")

    def test_to_dict_empty(self):
        """空 MatchResult.to_dict()"""
        result = MatchResult(match_level="NEEDS_CONFIRM")
        d = result.to_dict()
        self.assertEqual(d["match_level"], "NEEDS_CONFIRM")
        self.assertEqual(len(d["concerns"]), 0)
        self.assertEqual(len(d["trace"]), 0)


if __name__ == "__main__":
    unittest.main()


class TestTier2ContextMatch(unittest.TestCase):
    """第二级上下文辅助匹配测试。"""

    def setUp(self):
        self.engine = MatchEngine()
        self.provider = MagicMock()
        self.provider.__class__.__name__ = "MockProvider"

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    @patch('media_importer.features.scraping.match_engine.MatchEngine._collect_context')
    def test_ai_high_certainty_selects_context_pass(self, mock_context, mock_tier1):
        """AI 高确定性选中 → CONTEXT_PASS"""
        from media_importer.features.providers.base import SearchItem
        mock_context.return_value = {"parent_folder": "Inception"}
        self.provider.search.return_value = SearchResult(items=[
            SearchItem(item_id="27205", title="Inception", year=2010, media_type="movie",
                       provider_type="tmdb", original_title="Inception", poster_url=None,
                       vote_average=None, raw_data={}),
        ])
        with patch.object(self.engine.title_matcher, 'match_standard') as mock_match:
            mock_match.return_value = MagicMock(level="L5", T=0.6)
            with patch('media_importer.scraper.llm_scraper.LLMScraper.tier2_correct') as mock_correct:
                mock_correct.return_value = {
                    "corrected_title": "Inception",
                    "corrected_year": 2010,
                    "media_type_hint": "movie",
                    "certainty": "high",
                    "reason": "标题匹配且上级文件夹名一致",
                    "suggestion": "Inception",
                }
                result = self.engine.match(
                    "Inception.2010.1080p.BluRay.mkv", [self.provider],
                    video_path="/movies/Inception/Inception.2010.1080p.BluRay.mkv"
                )
        self.assertEqual(result.match_level, "CONTEXT_PASS")
        self.assertEqual(result.match_tier, 2)

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    @patch('media_importer.features.scraping.match_engine.MatchEngine._collect_context')
    def test_ai_low_certainty_falls_to_tier3(self, mock_context, mock_tier1):
        """AI 低确定性 → NEEDS_CONFIRM（停在第二级，不搜Provider）"""
        mock_context.return_value = {"parent_folder": "Movies"}
        with patch('media_importer.scraper.llm_scraper.LLMScraper.tier2_correct') as mock_correct:
            mock_correct.return_value = {
                "corrected_title": "SomeMovie",
                "corrected_year": None,
                "media_type_hint": None,
                "certainty": "low",
                "reason": "无法确定标题",
                "suggestion": "SomeMovie",
            }
            result = self.engine.match(
                "SomeMovie.2020.mkv", [self.provider],
                video_path="/movies/Movies/SomeMovie.2020.mkv"
            )
        self.assertEqual(result.match_level, "NEEDS_CONFIRM")
        self.assertEqual(result.match_tier, 2)
        concern_codes = [c.code for c in result.concerns]
        self.assertIn("AI_UNCERTAIN", concern_codes)

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    @patch('media_importer.features.scraping.match_engine.MatchEngine._collect_context')
    def test_ai_no_match_selected_index_minus1(self, mock_context, mock_tier1):
        """AI 低确定性 → NEEDS_CONFIRM（停在第二级，空候选列表）"""
        mock_context.return_value = {}
        with patch('media_importer.scraper.llm_scraper.LLMScraper.tier2_correct') as mock_correct:
            mock_correct.return_value = {
                "corrected_title": "UnknownFile",
                "corrected_year": None,
                "media_type_hint": None,
                "certainty": "low",
                "reason": "候选与文件名不匹配",
                "suggestion": "UnknownFile",
            }
            result = self.engine.match(
                "UnknownFile.mkv", [self.provider],
                video_path="/downloads/UnknownFile.mkv"
            )
        self.assertEqual(result.match_level, "NEEDS_CONFIRM")
        self.assertEqual(result.match_tier, 2)

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    @patch('media_importer.features.scraping.match_engine.MatchEngine._collect_context')
    def test_ai_call_failure_falls_to_tier3(self, mock_context, mock_tier1):
        """AI 调用失败 → 不崩溃，进入第三级"""
        from media_importer.features.providers.base import SearchItem
        mock_context.return_value = {}
        self.provider.search.return_value = SearchResult(items=[
            SearchItem(item_id="1", title="Test", year=2020, media_type="movie",
                       provider_type="tmdb", original_title="Test", poster_url=None,
                       vote_average=None, raw_data={}),
        ])
        with patch.object(self.engine.title_matcher, 'match_standard') as mock_match:
            mock_match.return_value = MagicMock(level="L5", T=0.6)
            with patch('media_importer.scraper.llm_scraper.LLMScraper') as MockLLM:
                MockLLM.return_value.tier2_judge.side_effect = Exception("API timeout")
                result = self.engine.match(
                    "Test.2020.mkv", [self.provider],
                    video_path="/downloads/Test.2020.mkv"
                )
        self.assertEqual(result.match_level, "NEEDS_CONFIRM")
        concern_codes = [c.code for c in result.concerns]
        self.assertIn("AI_UNCERTAIN", concern_codes)

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    @patch('media_importer.features.scraping.match_engine.MatchEngine._collect_context')
    def test_no_candidates_skips_tier2(self, mock_context, mock_tier1):
        """无候选列表 → 跳过第二级，直接进入第三级"""
        mock_context.return_value = {}
        self.provider.search.return_value = SearchResult(items=[])
        with patch.object(self.engine.title_matcher, 'match_standard') as mock_match:
            result = self.engine.match(
                "RandomFile.2023.mkv", [self.provider],
                video_path="/downloads/RandomFile.2023.mkv"
            )
        self.assertEqual(result.match_level, "NEEDS_CONFIRM")

    def test_collect_context_with_valid_path(self):
        """_collect_context 从合法路径收集上下文"""
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = os.path.join(tmpdir, "Inception.2010")
            os.makedirs(parent, exist_ok=True)
            video_path = os.path.join(parent, "Inception.2010.1080p.BluRay.mkv")
            # 创建同级视频文件
            open(os.path.join(parent, "Inception.2010.1080p.BluRay.mp4"), "w").close()
            context = self.engine._collect_context(video_path)
        self.assertEqual(context.get("parent_folder"), "Inception.2010")
        self.assertIn("sibling_files", context)
        self.assertTrue(any("mp4" in f for f in context["sibling_files"]))


class TestTier3UserConfirm(unittest.TestCase):
    """第三级用户确认测试。"""

    def setUp(self):
        self.engine = MatchEngine()
        self.provider = MagicMock()
        self.provider.__class__.__name__ = "MockProvider"

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    @patch('media_importer.features.scraping.match_engine._tier2_context_match_impl', return_value=None)
    def test_tier3_returns_needs_confirm(self, mock_tier2, mock_tier1):
        """第一级和第二级都未匹配 → NEEDS_CONFIRM"""
        from media_importer.features.providers.base import SearchItem
        self.provider.search.return_value = SearchResult(items=[
            SearchItem(item_id="1", title="Test Movie", year=2020, media_type="movie",
                       provider_type="tmdb", original_title="Test Movie", poster_url=None,
                       vote_average=None, raw_data={}),
        ])
        with patch.object(self.engine.title_matcher, 'match_standard') as mock_match:
            mock_match.return_value = MagicMock(level="L6", T=0.4)
            result = self.engine.match("Test.2020.mkv", [self.provider])
        self.assertEqual(result.match_level, "NEEDS_CONFIRM")
        self.assertEqual(result.match_tier, 3)

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    @patch('media_importer.features.scraping.match_engine._tier2_context_match_impl', return_value=None)
    def test_tier3_includes_candidates(self, mock_tier2, mock_tier1):
        """第三级结果包含候选列表"""
        from media_importer.features.providers.base import SearchItem
        self.provider.search.return_value = SearchResult(items=[
            SearchItem(item_id="1", title="Movie A", year=2020, media_type="movie",
                       provider_type="tmdb", original_title="Movie A", poster_url=None,
                       vote_average=None, raw_data={}),
            SearchItem(item_id="2", title="Movie B", year=2021, media_type="movie",
                       provider_type="tmdb", original_title="Movie B", poster_url=None,
                       vote_average=None, raw_data={}),
        ])
        with patch.object(self.engine.title_matcher, 'match_standard') as mock_match:
            mock_match.return_value = MagicMock(level="L6", T=0.4)
            result = self.engine.match("Test.2020.mkv", [self.provider])
        self.assertEqual(result.match_level, "NEEDS_CONFIRM")
        self.assertTrue(len(result.candidates) > 0)

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    @patch('media_importer.features.scraping.match_engine._tier2_context_match_impl', return_value=None)
    def test_tier3_has_concerns(self, mock_tier2, mock_tier1):
        """第三级结果包含疑虑原因"""
        from media_importer.features.providers.base import SearchItem
        self.provider.search.return_value = SearchResult(items=[
            SearchItem(item_id="1", title="Test", year=2020, media_type="movie",
                       provider_type="tmdb", original_title="Test", poster_url=None,
                       vote_average=None, raw_data={}),
        ])
        with patch.object(self.engine.title_matcher, 'match_standard') as mock_match:
            mock_match.return_value = MagicMock(level="L6", T=0.4)
            result = self.engine.match("Test.2020.mkv", [self.provider])
        self.assertTrue(len(result.concerns) > 0)

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    @patch('media_importer.features.scraping.match_engine._tier2_context_match_impl', return_value=None)
    def test_tier3_trace_includes_step3(self, mock_tier2, mock_tier1):
        """第三级追踪包含 tier=3 步骤"""
        from media_importer.features.providers.base import SearchItem
        self.provider.search.return_value = SearchResult(items=[
            SearchItem(item_id="1", title="Test", year=2020, media_type="movie",
                       provider_type="tmdb", original_title="Test", poster_url=None,
                       vote_average=None, raw_data={}),
        ])
        with patch.object(self.engine.title_matcher, 'match_standard') as mock_match:
            mock_match.return_value = MagicMock(level="L6", T=0.4)
            result = self.engine.match("Test.2020.mkv", [self.provider])
        tier3_steps = [s for s in result.trace_steps if s.tier == 3]
        self.assertTrue(len(tier3_steps) > 0)


class TestMatchEngineEndToEnd(unittest.TestCase):
    """三级匹配引擎端到端测试。"""

    def setUp(self):
        self.engine = MatchEngine()
        self.provider = MagicMock()
        self.provider.__class__.__name__ = "MockProvider"

    def test_tier1_auto_pass_skips_tier2_tier3(self):
        """第一级精确匹配 → 不进入第二级和第三级"""
        from media_importer.features.providers.base import SearchItem
        self.provider.search.return_value = SearchResult(items=[
            SearchItem(item_id="27205", title="Inception", year=2010, media_type="movie",
                       provider_type="tmdb", original_title="Inception", poster_url=None,
                       vote_average=None, raw_data={}),
        ])
        with patch.object(self.engine.title_matcher, 'match_standard') as mock_match:
            mock_match.return_value = MagicMock(level="L1", T=1.0)
            result = self.engine.match("Inception.2010.1080p.BluRay.mkv", [self.provider])
        self.assertEqual(result.match_level, "AUTO_PASS")
        self.assertEqual(result.match_tier, 1)
        tier2_steps = [s for s in result.trace_steps if s.tier == 2]
        tier3_steps = [s for s in result.trace_steps if s.tier == 3]
        self.assertEqual(len(tier2_steps), 0)
        self.assertEqual(len(tier3_steps), 0)

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    @patch('media_importer.features.scraping.match_engine._tier2_context_match_impl')
    def test_tier2_context_pass_skips_tier3(self, mock_tier2, mock_tier1):
        """第二级上下文匹配 → 不进入第三级"""
        mock_tier2.return_value = MatchResult(
            match_level="CONTEXT_PASS",
            provider_id=27205,
            provider_title="Inception",
            match_tier=2,
            confirm_reason="AI辅助匹配",
        )
        result = self.engine.match("Inception.2010.mkv", [self.provider])
        self.assertEqual(result.match_level, "CONTEXT_PASS")
        self.assertEqual(result.match_tier, 2)

    @patch('media_importer.features.scraping.match_engine._tier1_exact_match_impl', return_value=None)
    @patch('media_importer.features.scraping.match_engine._tier2_context_match_impl', return_value=None)
    def test_all_tiers_fail_returns_needs_confirm(self, mock_tier2, mock_tier1):
        """三级全部未匹配 → NEEDS_CONFIRM"""
        from media_importer.features.providers.base import SearchItem
        self.provider.search.return_value = SearchResult(items=[
            SearchItem(item_id="1", title="Random", year=2020, media_type="movie",
                       provider_type="tmdb", original_title="Random", poster_url=None,
                       vote_average=None, raw_data={}),
        ])
        with patch.object(self.engine.title_matcher, 'match_standard') as mock_match:
            mock_match.return_value = MagicMock(level="L7", T=0.0)
            result = self.engine.match("RandomFile.2020.mkv", [self.provider])
        self.assertEqual(result.match_level, "NEEDS_CONFIRM")

    def test_no_title_returns_needs_confirm_immediately(self):
        """无法提取标题 → 直接 NEEDS_CONFIRM，不调用 Provider"""
        with patch.object(self.engine.filename_cleaner, 'clean') as mock_clean:
            mock_clean.return_value = CleanResult(clean_title="", cjk_title="")
            result = self.engine.match("video.mkv", [self.provider])
        self.assertEqual(result.match_level, "NEEDS_CONFIRM")
        self.provider.search.assert_not_called()