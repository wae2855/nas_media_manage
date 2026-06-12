"""Tests for LLM web search integration.

Covers:
- WebSearchConfig dataclass (auto-detect provider)
- Web search scenario routing
- Search injection per provider (zhipu, qwen, moonshot)
- Error classification for search vs non-search errors
- Config migration from MCP to web_search
- LLMConfig field changes
- detect_provider function
- Kimi/Moonshot multi-turn tool_calls handling
"""
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from media_importer.features.scraping.web_search_config import (
    WebSearchConfig, detect_provider, SUPPORTED_PROVIDERS, PROVIDER_DETECTION_MAP,
)
from media_importer.core.config_view import ConfigView
from media_importer.core.config_migrations import _migrate_mcp_to_web_search


# ========================================================================
# WebSearchConfig unit tests
# ========================================================================

class TestWebSearchConfig:
    def test_default_disabled(self):
        cfg = WebSearchConfig()
        assert cfg.enabled is False
        assert cfg.detected_provider is None
        assert cfg.should_search("scrape") is False
        assert cfg.should_search("series_scrape") is False
        assert cfg.supports_web_search() is False

    def test_enabled_with_detected_provider(self):
        cfg = WebSearchConfig(enabled=True, detected_provider="zhipu")
        assert cfg.should_search("scrape") is True
        assert cfg.should_search("series_scrape") is True
        assert cfg.should_search("source_cleaner") is False
        assert cfg.should_search("extract_title") is False
        assert cfg.supports_web_search() is True

    def test_enabled_but_no_detected_provider(self):
        cfg = WebSearchConfig(enabled=True, detected_provider=None)
        assert cfg.should_search("scrape") is False
        assert cfg.supports_web_search() is False

    def test_disabled_ignores_scenario(self):
        cfg = WebSearchConfig(enabled=False, detected_provider="qwen",
                              enabled_for_scrape=True)
        assert cfg.should_search("scrape") is False

    def test_scenario_flags_respected(self):
        cfg = WebSearchConfig(enabled=True, detected_provider="qwen",
                              enabled_for_scrape=False,
                              enabled_for_series_scrape=True)
        assert cfg.should_search("scrape") is False
        assert cfg.should_search("series_scrape") is True

    def test_unknown_scenario_returns_false(self):
        cfg = WebSearchConfig(enabled=True, detected_provider="zhipu")
        assert cfg.should_search("unknown_scenario") is False
        assert cfg.should_search("source_cleaner") is False

    def test_frozen_dataclass(self):
        cfg = WebSearchConfig(enabled=True, detected_provider="zhipu")
        with pytest.raises(AttributeError):
            cfg.enabled = False

    def test_effective_provider(self):
        cfg = WebSearchConfig(detected_provider="qwen")
        assert cfg.effective_provider() == "qwen"

    def test_built_from_llm_config_dict(self):
        ws_dict = {
            "enabled": True,
            "enabled_for_scrape": True,
            "enabled_for_series_scrape": False,
        }
        cfg = WebSearchConfig(**ws_dict)
        assert cfg.enabled is True
        assert cfg.should_search("scrape") is False
        assert cfg.should_search("series_scrape") is False


# ========================================================================
# detect_provider tests
# ========================================================================

class TestDetectProvider:
    def test_detect_zhipu_bigmodel(self):
        assert detect_provider("https://open.bigmodel.cn/api/paas/v4") == "zhipu"

    def test_detect_zhipu_direct(self):
        assert detect_provider("https://api.zhipuai.cn/v1") == "zhipu"

    def test_detect_qwen_dashscope(self):
        assert detect_provider("https://dashscope.aliyuncs.com/compatible-mode/v1") == "qwen"

    def test_detect_qwen_aliyun(self):
        assert detect_provider("https://aliyun.example.com/v1") == "qwen"

    def test_detect_moonshot(self):
        assert detect_provider("https://api.moonshot.cn/v1") == "moonshot"

    def test_detect_unknown_returns_none(self):
        assert detect_provider("https://api.openai.com/v1") is None

    def test_detect_empty_url(self):
        assert detect_provider("") is None

    def test_detect_none_url(self):
        assert detect_provider(None) is None

    def test_supported_providers_has_all_expected(self):
        expected = {"zhipu", "qwen", "moonshot"}
        assert set(SUPPORTED_PROVIDERS.keys()) == expected


# ========================================================================
# Search injection tests
# ========================================================================

class TestSearchInjection:
    def test_zhipu_injection(self):
        from media_importer.scraper.llm_scraper import LLMScraper
        scraper = LLMScraper({"llm": {"api_key": "test", "base_url": "https://test.com/v1", "model": "test"}})
        payload = {"model": "test", "messages": []}
        scraper._inject_search(payload, "zhipu")
        assert "tools" in payload
        assert payload["tools"][0]["type"] == "web_search"

    def test_qwen_injection(self):
        from media_importer.scraper.llm_scraper import LLMScraper
        scraper = LLMScraper({"llm": {"api_key": "test", "base_url": "https://test.com/v1", "model": "test"}})
        payload = {"model": "test", "messages": []}
        scraper._inject_search(payload, "qwen")
        assert payload.get("enable_search") is True

    def test_moonshot_injection(self):
        from media_importer.scraper.llm_scraper import LLMScraper
        scraper = LLMScraper({"llm": {"api_key": "test", "base_url": "https://test.com/v1", "model": "test"}})
        payload = {"model": "test", "messages": []}
        scraper._inject_search(payload, "moonshot")
        assert "tools" in payload
        assert payload["tools"][0]["type"] == "builtin_function"
        assert payload["tools"][0]["function"]["name"] == "$web_search"

    def test_supported_providers_has_all_expected(self):
        expected = {"zhipu", "qwen", "moonshot"}
        assert set(SUPPORTED_PROVIDERS.keys()) == expected


# ========================================================================
# Error classification tests
# ========================================================================

class TestErrorClassification:
    def test_auth_error(self):
        from media_importer.scraper.llm_scraper import LLMScraper, LLMApiError
        scraper = LLMScraper({"llm": {"api_key": "test", "base_url": "https://test.com/v1", "model": "test"}})
        err = scraper._classify_error(401, {})
        assert isinstance(err, LLMApiError)
        assert "auth" in str(err).lower()

    def test_rate_limit(self):
        from media_importer.scraper.llm_scraper import LLMScraper, LLMApiError
        scraper = LLMScraper({"llm": {"api_key": "test", "base_url": "https://test.com/v1", "model": "test"}})
        err = scraper._classify_error(429, {"error": "rate limit exceeded"})
        assert isinstance(err, LLMApiError)

    def test_web_search_quota_error(self):
        from media_importer.scraper.llm_scraper import LLMScraper, LLMWebSearchError
        scraper = LLMScraper({"llm": {"api_key": "test", "base_url": "https://test.com/v1", "model": "test"}})
        err = scraper._classify_error(429, {"error": "web_search quota exceeded"})
        assert isinstance(err, LLMWebSearchError)

    def test_web_search_not_available(self):
        from media_importer.scraper.llm_scraper import LLMScraper, LLMWebSearchError
        scraper = LLMScraper({"llm": {"api_key": "test", "base_url": "https://test.com/v1", "model": "test"}})
        err = scraper._classify_error(400, {"error": "web_search tool not available"})
        assert isinstance(err, LLMWebSearchError)

    def test_server_error(self):
        from media_importer.scraper.llm_scraper import LLMScraper, LLMApiError
        scraper = LLMScraper({"llm": {"api_key": "test", "base_url": "https://test.com/v1", "model": "test"}})
        err = scraper._classify_error(500, {})
        assert isinstance(err, LLMApiError)


# ========================================================================
# Exception hierarchy tests
# ========================================================================

class TestExceptionHierarchy:
    def test_llm_scrape_error_is_api_error(self):
        from media_importer.scraper.llm_scraper import LLMScrapeError, LLMApiError
        assert issubclass(LLMScrapeError, LLMApiError)

    def test_llm_web_search_error_is_standalone(self):
        from media_importer.scraper.llm_scraper import LLMWebSearchError, LLMApiError
        assert issubclass(LLMWebSearchError, Exception)
        assert not issubclass(LLMWebSearchError, LLMApiError)


# ========================================================================
# Config migration tests
# ========================================================================

class TestConfigMigration:
    def test_mcp_to_web_search_basic(self):
        config = {
            "llm": {
                "provider": "openai",
                "mcp": {
                    "enabled": True,
                    "scenarios": {
                        "scrape": True,
                        "series_scrape": False,
                    },
                },
            }
        }
        _migrate_mcp_to_web_search(config)
        assert "mcp" not in config["llm"]
        assert "provider" not in config["llm"]
        ws = config["llm"]["web_search"]
        assert ws["enabled"] is True
        assert ws["enabled_for_scrape"] is True
        assert ws["enabled_for_series_scrape"] is False

    def test_mcp_disabled_no_web_search(self):
        config = {"llm": {"mcp": {"enabled": False}}}
        _migrate_mcp_to_web_search(config)
        assert "web_search" not in config["llm"]
        assert "mcp" not in config["llm"]

    def test_no_mcp_no_change(self):
        config = {"llm": {"api_key": "sk-test"}}
        _migrate_mcp_to_web_search(config)
        assert "web_search" not in config["llm"]
        assert "mcp" not in config["llm"]

    def test_provider_removed_even_without_mcp(self):
        config = {"llm": {"provider": "openai", "api_key": "sk-test"}}
        _migrate_mcp_to_web_search(config)
        assert "provider" not in config["llm"]


# ========================================================================
# LLMConfig field tests
# ========================================================================

class TestLLMConfig:
    def test_source_cleaner_model_three_level_fallback(self):
        llm_raw = {
            "api_key": "sk-test",
            "base_url": "https://test.com/v1",
            "model": "gpt-4o",
            "fast_model": "gpt-4o-mini",
            "source_cleaner_model": "",
        }
        config = {"llm": llm_raw}
        view = ConfigView.from_dict(config)
        assert view.llm.source_cleaner_model == "gpt-4o-mini"

    def test_source_cleaner_model_explicit(self):
        llm_raw = {
            "api_key": "sk-test",
            "base_url": "https://test.com/v1",
            "model": "gpt-4o",
            "fast_model": "gpt-4o-mini",
            "source_cleaner_model": "custom-cleaner",
        }
        config = {"llm": llm_raw}
        view = ConfigView.from_dict(config)
        assert view.llm.source_cleaner_model == "custom-cleaner"


# ========================================================================
# LLMScraper web search integration tests
# ========================================================================

class TestLLMScraperWebSearch:
    def test_auto_detect_provider_from_base_url(self):
        config = {
            "llm": {
                "api_key": "sk-test",
                "base_url": "https://open.bigmodel.cn/api/paas/v4",
                "model": "glm-4-flash",
                "web_search": {"enabled": True},
            }
        }
        from media_importer.scraper.llm_scraper import LLMScraper
        scraper = LLMScraper(config)
        assert scraper.web_search_config.enabled is True
        assert scraper.web_search_config.detected_provider == "zhipu"
        assert scraper.web_search_config.supports_web_search() is True

    def test_no_detect_for_unknown_url(self):
        config = {
            "llm": {
                "api_key": "sk-test",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o",
                "web_search": {"enabled": True},
            }
        }
        from media_importer.scraper.llm_scraper import LLMScraper
        scraper = LLMScraper(config)
        assert scraper.web_search_config.enabled is True
        assert scraper.web_search_config.detected_provider is None
        assert scraper.web_search_config.supports_web_search() is False

    def test_search_injection_in_do_call(self):
        config = {
            "llm": {
                "api_key": "sk-test",
                "base_url": "https://open.bigmodel.cn/api/paas/v4",
                "model": "glm-4-flash",
                "web_search": {"enabled": True},
            }
        }
        from media_importer.scraper.llm_scraper import LLMScraper
        scraper = LLMScraper(config)

        mock_response = json.dumps({
            "choices": [{"message": {"content": "test response"}, "finish_reason": "stop"}]
        }).encode("utf-8")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value.read.return_value = mock_response
            result = scraper._do_call(
                "system", "user", "glm-4-flash",
                "https://open.bigmodel.cn/api/paas/v4", "sk-test", scenario="scrape"
            )
            assert result == "test response"

    def test_search_fallback_on_error(self):
        config = {
            "llm": {
                "api_key": "sk-test",
                "base_url": "https://open.bigmodel.cn/api/paas/v4",
                "model": "glm-4-flash",
                "web_search": {"enabled": True},
            }
        }
        from media_importer.scraper.llm_scraper import LLMScraper, LLMWebSearchError
        scraper = LLMScraper(config)

        mock_response = json.dumps({
            "choices": [{"message": {"content": "fallback response"}, "finish_reason": "stop"}]
        }).encode("utf-8")

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise LLMWebSearchError("web search quota exceeded")
            mock = MagicMock()
            mock.__enter__ = MagicMock(return_value=mock)
            mock.__exit__ = MagicMock(return_value=False)
            mock.read.return_value = mock_response
            return mock

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = side_effect
            result = scraper._do_call(
                "system", "user", "glm-4-flash",
                "https://open.bigmodel.cn/api/paas/v4", "sk-test", scenario="scrape"
            )
            assert result == "fallback response"
            assert call_count[0] == 2

    def test_moonshot_multi_turn_tool_calls(self):
        """Test that Kimi/Moonshot $web_search multi-turn flow is handled."""
        config = {
            "llm": {
                "api_key": "sk-test",
                "base_url": "https://api.moonshot.cn/v1",
                "model": "moonshot-v1-128k",
                "web_search": {"enabled": True},
            }
        }
        from media_importer.scraper.llm_scraper import LLMScraper
        scraper = LLMScraper(config)

        # First response: tool_calls with $web_search
        first_response = json.dumps({
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_123",
                        "type": "function",
                        "function": {"name": "$web_search", "arguments": '{"query": "Inception movie"}'}
                    }]
                },
                "finish_reason": "tool_calls"
            }]
        }).encode("utf-8")

        # Second response: final answer
        second_response = json.dumps({
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": '{"title_cn": "盗梦空间", "title_en": "Inception", "year": 2010}'
                },
                "finish_reason": "stop"
            }]
        }).encode("utf-8")

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            mock = MagicMock()
            mock.__enter__ = MagicMock(return_value=mock)
            mock.__exit__ = MagicMock(return_value=False)
            mock.read.return_value = first_response if call_count[0] == 1 else second_response
            return mock

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = side_effect
            result = scraper._do_call(
                "system", "user", "moonshot-v1-128k",
                "https://api.moonshot.cn/v1", "sk-test", scenario="scrape"
            )
            assert "盗梦空间" in result
            assert call_count[0] == 2
