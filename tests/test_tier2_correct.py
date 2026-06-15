"""第二级 AI 标题纠正单元测试（tier2_correct 方法）。"""

from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestTier2Correct:
    """验证 tier2_correct 能正确处理各种文件名场景。"""

    def _make_scraper(self, config=None):
        from media_importer.scraper.llm_scraper import LLMScraper
        if config is None:
            config = {
                "ai_assist": {
                    "base_url": "https://test.example.com/v1",
                    "model": "test-model",
                    "api_key": "test-key",
                }
            }
        return LLMScraper(config)

    def test_tc01_2160p_resolution_misidentified(self):
        """TC-01: 2160P分辨率误识别 → certainty=medium"""
        scraper = self._make_scraper()
        mock_response = (
            '{"corrected_title": "美丽人生", "corrected_year": null, '
            '"media_type_hint": "movie", "certainty": "medium", '
            '"reason": "标题含2160P，识别为分辨率后缀", "suggestion": "美丽人生"}'
        )
        with patch.object(scraper, '_do_call', return_value=mock_response):
            result = scraper.tier2_correct(
                original_filename="美丽人生.2160P.mkv",
                path_context={"parent_folder": "电影"},
                clean_title="美丽人生",
            )
        assert result["corrected_title"] == "美丽人生"
        assert result["corrected_year"] is None
        assert result["certainty"] == "medium"
        assert "分辨率" in result["reason"]

    def test_tc02_title_contains_number(self):
        """TC-02: 标题内含数字（银翼杀手2049）→ certainty=high"""
        scraper = self._make_scraper()
        mock_response = (
            '{"corrected_title": "银翼杀手2049", "corrected_year": 2017, '
            '"media_type_hint": "movie", "certainty": "high", '
            '"reason": "2049是标题固定部分，2017是年份", "suggestion": "银翼杀手2049"}'
        )
        with patch.object(scraper, '_do_call', return_value=mock_response):
            result = scraper.tier2_correct(
                original_filename="银翼杀手2049.2017.BluRay.2160p.mkv",
            )
        assert result["corrected_title"] == "银翼杀手2049"
        assert result["corrected_year"] == 2017
        assert result["certainty"] == "high"

    def test_tc03_title_is_number_2012(self):
        """TC-03: 标题就是数字2012 → certainty=high"""
        scraper = self._make_scraper()
        mock_response = (
            '{"corrected_title": "2012", "corrected_year": 2009, '
            '"media_type_hint": "movie", "certainty": "high", '
            '"reason": "标题就是数字2012", "suggestion": "2012"}'
        )
        with patch.object(scraper, '_do_call', return_value=mock_response):
            result = scraper.tier2_correct(
                original_filename="2012.2009.1080p.BluRay.mkv",
            )
        assert result["corrected_title"] == "2012"
        assert result["corrected_year"] == 2009
        assert result["certainty"] == "high"

    def test_tc04_title_is_number_2046(self):
        """TC-04: 标题就是数字2046 → certainty=high"""
        scraper = self._make_scraper()
        mock_response = (
            '{"corrected_title": "2046", "corrected_year": 2004, '
            '"media_type_hint": "movie", "certainty": "high", '
            '"reason": "标题就是数字2046", "suggestion": "2046"}'
        )
        with patch.object(scraper, '_do_call', return_value=mock_response):
            result = scraper.tier2_correct(
                original_filename="2046.2004.720p.mkv",
            )
        assert result["corrected_title"] == "2046"
        assert result["corrected_year"] == 2004
        assert result["certainty"] == "high"

    def test_tc05_no_year_tv_episode(self):
        """TC-05: 无年份剧集 → media_type_hint=tv, certainty=medium"""
        scraper = self._make_scraper()
        mock_response = (
            '{"corrected_title": "jinji", "corrected_year": null, '
            '"media_type_hint": "tv", "certainty": "medium", '
            '"reason": "可能是剧集，标题为jinji", "suggestion": "jinji"}'
        )
        with patch.object(scraper, '_do_call', return_value=mock_response):
            result = scraper.tier2_correct(
                original_filename="jinji.S01E02.mp4",
                path_context={"parent_folder": "紧急"},
            )
        assert result["corrected_title"] == "jinji"
        assert result["media_type_hint"] == "tv"
        assert result["certainty"] == "medium"

    def test_tc06_standard_naming(self):
        """TC-06: 标准命名 → certainty=high"""
        scraper = self._make_scraper()
        mock_response = (
            '{"corrected_title": "xXx: Return of Xander Cage", "corrected_year": 2017, '
            '"media_type_hint": "movie", "certainty": "high", '
            '"reason": "标准命名，标题和年份明确", "suggestion": "xXx: Return of Xander Cage"}'
        )
        with patch.object(scraper, '_do_call', return_value=mock_response):
            result = scraper.tier2_correct(
                original_filename="xXx.Return.of.Xander.Cage.2017.1080p.BluRay.x264-CHDWEB.mkv",
            )
        assert result["corrected_title"] == "xXx: Return of Xander Cage"
        assert result["corrected_year"] == 2017
        assert result["certainty"] == "high"

    def test_tc07_ai_exception_fallback(self):
        """TC-07: AI异常兜底 → certainty=low"""
        scraper = self._make_scraper()
        with patch.object(scraper, '_do_call', side_effect=Exception("API error")):
            result = scraper.tier2_correct(
                original_filename="test.mkv",
                clean_title="test",
            )
        assert result["certainty"] == "low"
        assert "AI 解析失败" in result["reason"]
        # 降级时应使用 clean_title 作为 corrected_title
        assert result["corrected_title"] == "test"

    def test_tc08_custom_prompt_used(self):
        """TC-08: 自定义提示词生效"""
        custom_prompt = "你是一个自定义的影视标题纠正助手。"
        config = {
            "ai_assist": {
                "base_url": "https://test.example.com/v1",
                "model": "test-model",
                "api_key": "test-key",
                "prompt_match_assist": custom_prompt,
            }
        }
        scraper = self._make_scraper(config)
        mock_response = (
            '{"corrected_title": "Test", "corrected_year": null, '
            '"media_type_hint": null, "certainty": "high", '
            '"reason": "自定义测试", "suggestion": "Test"}'
        )
        with patch.object(scraper, '_do_call', return_value=mock_response) as mock_call:
            result = scraper.tier2_correct(
                original_filename="test.mkv",
            )
        # 验证使用了自定义提示词（通过检查 _do_call 被调用）
        mock_call.assert_called_once()
        call_args = mock_call.call_args[0]
        assert call_args[0] == custom_prompt, "应使用自定义提示词而非默认值"
        assert result["certainty"] == "high"

    def test_tc07b_parse_think_tag_response(self):
        """TC-07b: AI返回含 think 标签的响应也能正确解析"""
        scraper = self._make_scraper()
        mock_response = (
            "让我们分析这个文件名...\n"
            "<｜end▁of▁thinking｜>\n\n"
            '```json\n{"corrected_title": "美丽人生", "corrected_year": null, '
            '"media_type_hint": "movie", "certainty": "medium", '
            '"reason": "标题含2160P", "suggestion": "美丽人生"}\n```'
        )
        with patch.object(scraper, '_do_call', return_value=mock_response):
            result = scraper.tier2_correct(
                original_filename="美丽人生.2160P.mkv",
                clean_title="美丽人生",
            )
        assert result["corrected_title"] == "美丽人生"
        assert result["certainty"] == "medium"
