"""_retry_with_fallback_impl / _call_with_retry_impl 单元测试（覆盖 T1.8-T1.10）。

验证：
- 首次成功不重试
- primary 失败后切 fallback
- 无 fallback 时抛最后一个错误
- 未知 scene 抛 ValueError（由 SceneStrategyResolver 保证）
"""
from unittest.mock import patch

import pytest

from media_importer.scraper.llm_scraper import LLMScraper
from media_importer.scraper.exceptions import LLMApiError, LLMScrapeError


def _make_config(**overrides):
    cfg = {
        "ai_assist": {"base_url": "https://a.com", "model": "a-m", "api_key": "k",
                     "max_retries": 2, "retry_delay": 0},
        "ai_search": {"enabled": True, "provider": "zhipu",
                     "base_url": "https://s.com", "model": "s-m", "api_key": "k",
                     "search_type": "search_std"},
        "ai_scene_strategy": {
            "match_assist": {"primary": "ai_assist", "fallback": ""},
        },
    }
    cfg.update(overrides)
    return cfg


# _retry_with_fallback 返回经 _parse_response_impl 处理后的 dict，
# 包含 title_cn/title_en/year/type/dimensions 等额外字段。
# 使用 call_with_prompt（走 _call_with_retry_impl）测试原始字符串返回。


class TestRetrySuccessFirst:
    def test_retry_success_on_first_attempt(self):
        """首次成功不重试（_do_call 只调用一次）。"""
        s = LLMScraper(_make_config())
        with patch.object(s, "_do_call", return_value="ok result") as mock:
            result = s.call_with_prompt("p", "u", scene="match_assist", scenario="scrape")
        assert mock.call_count == 1
        assert result == "ok result"


class TestRetrySwitchesToFallback:
    def test_retry_switches_to_fallback_model(self):
        """primary 重试 max_retries 次失败后切到 fallback。"""
        cfg = _make_config()
        cfg["ai_scene_strategy"] = {
            "match_assist": {"primary": "ai_assist", "fallback": "ai_search"},
        }
        s = LLMScraper(cfg)
        def _call(system_prompt, user_content, model, base_url, api_key, scenario=None):
            if model == "a-m":
                raise LLMApiError("primary fail")
            return "fallback_ok"
        with patch.object(s, "_do_call", side_effect=_call):
            result = s.call_with_prompt("p", "u", scene="match_assist", scenario="scrape")
        assert result == "fallback_ok"


class TestRetryNoFallback:
    def test_retry_no_fallback_raises_last_error(self):
        """fallback="" 时重试失败后抛最后一个错误。"""
        s = LLMScraper(_make_config())
        with patch.object(s, "_do_call", side_effect=LLMApiError("always fail")):
            with pytest.raises(LLMApiError, match="always fail"):
                s._retry_with_fallback("p", "u", scene="match_assist", scenario="scrape")


class TestRetryUnknownScene:
    def test_retry_unknown_scene_raises(self):
        """未知 scene 抛 ValueError。"""
        s = LLMScraper(_make_config())
        with pytest.raises(ValueError, match="未知场景"):
            s._retry_with_fallback("p", "u", scene="nonexistent_scene")
