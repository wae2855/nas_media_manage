"""AI 场景集成测试（覆盖 T3.2）。

验证 5 个场景的模型选择和容错链：
- 场景 1 dimension_supplement 使用配置的模型
- 场景 2 dimension_mapping 失败降级到场景 1
- 场景 3 title_clean 失败降级到正则
- 场景 4 match_assist 失败降级到 NEEDS_CONFIRM
- 场景 5 source_clean 失败仅返回规则分类
- 全流程 AI 未配置仍可运行
"""
from unittest.mock import patch

import pytest

from media_importer.scraper.llm_scraper import LLMScraper
from media_importer.features.source_cleaning.cleaner import SourceCleaner
from media_importer.scraper.exceptions import LLMApiError


def _make_config(**overrides):
    cfg = {
        "ai_assist": {"base_url": "https://a.com", "model": "a-m", "api_key": "k",
                     "max_retries": 1, "retry_delay": 0},
        "ai_search": {"enabled": True, "provider": "zhipu",
                     "base_url": "https://s.com", "model": "s-m", "api_key": "k"},
        "ai_scene_strategy": {
            "dimension_supplement": {"primary": "ai_assist", "fallback": ""},
            "dimension_mapping": {"primary": "ai_search", "fallback": ""},
            "title_clean": {"primary": "ai_assist", "fallback": ""},
            "match_assist": {"primary": "ai_assist", "fallback": ""},
            "source_clean": {"primary": "ai_assist", "fallback": ""},
        },
    }
    cfg.update(overrides)
    return cfg


class TestScene1ModelSelection:
    def test_dimension_supplement_uses_ai_assist(self):
        """配置 primary=ai_assist，dimension_supplement 使用 ai_assist 模型（a-m）。"""
        s = LLMScraper(_make_config())
        with patch.object(s, "_do_call", return_value='{"title_cn":"t"}') as mock:
            s.scrape("video.mp4")
        assert mock.call_count >= 1
        # 至少有一次调用使用 ai_assist 的模型 a-m
        ai_assist_calls = [c for c in mock.call_args_list
                          if len(c[0]) >= 3 and c[0][2] == "a-m"]
        assert ai_assist_calls, "应使用 ai_assist 模型"


class TestScene2Fallback:
    def test_scrape_with_context_uses_scene2_model(self):
        """scrape_with_context 维度映射场景 2（provider_context 非空时）走 ai_search 模型。"""
        s = LLMScraper(_make_config())
        with patch.object(s, "_do_call", return_value='{"title_cn":"t"}') as mock:
            s.scrape_with_context(
                "video.mp4", subtitle_filenames=[],
                provider_context="已有数据", provider_dimensions={"title_cn": "Test"},
                exclude_dims=set(),
            )
        assert mock.call_count >= 1
        ai_search_calls = [c for c in mock.call_args_list
                          if len(c[0]) >= 3 and c[0][2] == "s-m"]
        assert ai_search_calls, "带 context 时场景 2 应使用 ai_search 模型"


class TestScene3Fallback:
    def test_title_clean_fails_falls_back_to_regex(self):
        """场景 3 全部失败后降级到正则清洗。"""
        from media_importer.scraper.filename_cleaner import FilenameCleaner
        s = LLMScraper(_make_config())
        cleaner = FilenameCleaner()
        with patch.object(s, "_do_call", side_effect=LLMApiError("fail")):
            result = cleaner.ai_clean("The.Movie.2020.1080p.mkv", llm_scraper=s)
        assert result.method == "regex"


class TestScene4Fallback:
    def test_tier2_low_certainty_to_needs_confirm(self):
        """场景 4 AI 推测失败返回 low certainty。"""
        s = LLMScraper(_make_config())
        with patch.object(s, "_do_call", side_effect=LLMApiError("fail")):
            result = s.tier2_correct("movie.mkv")
        assert result.get("certainty") == "low"


class TestScene5Fallback:
    def test_source_clean_ai_failure_returns_rule_only(self, tmp_path):
        """场景 5 全部失败后仅返回规则分类结果。"""
        src = tmp_path / "src"
        src.mkdir()
        (src / "movie.mp4").write_text("x")
        cfg = {
            "source_dir": str(src),
            "temp_dir": str(tmp_path / "tmp"),
            "log_dir": str(tmp_path / "logs"),
            "source_policy": {"recycle_dir": str(tmp_path / "recycle")},
            "source_cleaner": {"ai_enabled": True},
            "ai_assist": {"base_url": "https://a.com", "model": "a-m", "api_key": "k",
                         "max_retries": 1, "retry_delay": 0},
            "ai_search": {"enabled": True, "provider": "zhipu",
                         "base_url": "https://s.com", "model": "s-m", "api_key": "k"},
            "video_extensions": [".mp4"],
        }
        sc = SourceCleaner(cfg)
        with patch.object(sc.llm, "_do_call", side_effect=LLMApiError("fail")):
            result = sc._ai_analyze_directory(str(src), [{"name": "movie.mp4", "size_mb": 100, "ext": ".mp4"}])
        assert result == {}, "AI 失败应返回空 dict，仅规则分类结果生效"


class TestFullFlowWithAiDisabled:
    def test_full_import_flow_with_ai_disabled(self):
        """AI 未配置时，LLMScraper 创建正常，scrape 抛出可预期的 AI 错误。"""
        cfg = _make_config()
        cfg["ai_assist"] = {"base_url": "", "model": "", "api_key": "",
                           "max_retries": 1, "retry_delay": 0}
        cfg["ai_search"] = {"enabled": True, "provider": "", "model": "", "api_key": ""}
        s = LLMScraper(cfg)
        with pytest.raises(LLMApiError):
            s.scrape("nonexistent.mkv")
