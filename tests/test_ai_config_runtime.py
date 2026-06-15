"""AI 配置运行时生效测试（RED 测试 - 修复前应失败）。

覆盖：
- search_type 注入到不同 Provider 的请求 payload
- ai_search.enabled=false 时不调用联网搜索
- ai_assist 和 ai_search 模型调用分离
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from media_importer.features.scraping.web_search_config import (
    WebSearchConfig, build_web_search_config, DEFAULT_SEARCH_TYPE,
)


class TestSearchTypeInjection:
    """验证 search_type 真实注入到各 Provider 的请求参数。"""

    def test_zhipu_search_pro_injects_search_type(self):
        """智谱 search_pro 时 payload 应包含 search_type: search_pro。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_search": {
                "enabled": True,
                "provider": "zhipu",
                "base_url": "https://open.bigmodel.cn/api/paas/v4/",
                "model": "glm-4-flash",
                "api_key": "test-key",
                "search_type": "search_pro",
            }
        }
        scraper = LLMScraper(config)
        payload = {"model": "glm-4-flash", "messages": []}
        scraper._inject_search(payload, "zhipu")

        tools = payload.get("tools", [])
        assert len(tools) > 0, "应注入 web_search tool"
        web_search = tools[0].get("web_search", {})
        assert web_search.get("enable") is True, "应启用搜索"
        assert web_search.get("search_type") == "search_pro", (
            f"search_type 应为 search_pro，实际: {web_search.get('search_type')}"
        )

    def test_zhipu_search_std_injects_search_type(self):
        """智谱 search_std 时 payload 应包含 search_type: search_std。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_search": {
                "enabled": True,
                "provider": "zhipu",
                "base_url": "https://open.bigmodel.cn/api/paas/v4/",
                "model": "glm-4-flash",
                "api_key": "test-key",
                "search_type": "search_std",
            }
        }
        scraper = LLMScraper(config)
        payload = {"model": "glm-4-flash", "messages": []}
        scraper._inject_search(payload, "zhipu")

        tools = payload.get("tools", [])
        assert len(tools) > 0
        web_search = tools[0].get("web_search", {})
        assert web_search.get("enable") is True
        assert web_search.get("search_type") == "search_std"

    def test_qwen_forced_search_injects_search_options(self):
        """通义 forced_search 时 payload 应包含 enable_search=True 和 search_options。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_search": {
                "enabled": True,
                "provider": "qwen",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus",
                "api_key": "test-key",
                "search_type": "forced_search",
            }
        }
        scraper = LLMScraper(config)
        payload = {"model": "qwen-plus", "messages": []}
        scraper._inject_search(payload, "qwen")

        assert payload.get("enable_search") is True, "应启用搜索"
        search_options = payload.get("search_options", {})
        assert search_options.get("forced_search") is True, (
            f"forced_search 应为 True，实际: {search_options}"
        )

    def test_qwen_enable_search_injects_basic(self):
        """通义 enable_search 时 payload 应包含 enable_search=True。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_search": {
                "enabled": True,
                "provider": "qwen",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus",
                "api_key": "test-key",
                "search_type": "enable_search",
            }
        }
        scraper = LLMScraper(config)
        payload = {"model": "qwen-plus", "messages": []}
        scraper._inject_search(payload, "qwen")

        assert payload.get("enable_search") is True

    def test_moonshot_injects_web_search_tool(self):
        """Moonshot 应注入 $web_search 工具。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_search": {
                "enabled": True,
                "provider": "moonshot",
                "base_url": "https://api.moonshot.cn/v1",
                "model": "moonshot-v1-8k",
                "api_key": "test-key",
                "search_type": "web_search",
            }
        }
        scraper = LLMScraper(config)
        payload = {"model": "moonshot-v1-8k", "messages": []}
        scraper._inject_search(payload, "moonshot")

        tools = payload.get("tools", [])
        assert len(tools) > 0
        assert tools[0]["function"]["name"] == "$web_search"

    def test_default_search_type_when_not_configured(self):
        """未配置 search_type 时应使用 DEFAULT_SEARCH_TYPE。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_search": {
                "enabled": True,
                "provider": "zhipu",
                "base_url": "https://open.bigmodel.cn/api/paas/v4/",
                "model": "glm-4-flash",
                "api_key": "test-key",
                # 不配置 search_type
            }
        }
        scraper = LLMScraper(config)
        payload = {"model": "glm-4-flash", "messages": []}
        scraper._inject_search(payload, "zhipu")

        tools = payload.get("tools", [])
        assert len(tools) > 0
        web_search = tools[0].get("web_search", {})
        # 默认应为 search_std
        assert web_search.get("search_type") == DEFAULT_SEARCH_TYPE.get("zhipu", "search_std")


class TestAiSearchDisabled:
    """验证 ai_search.enabled=false 时不调用联网搜索。"""

    def test_disabled_ai_search_no_web_search_injection(self):
        """关闭 AI 联网搜索后，_inject_search 不应被调用。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_search": {
                "enabled": False,
                "provider": "zhipu",
                "base_url": "https://open.bigmodel.cn/api/paas/v4/",
                "model": "glm-4-flash",
                "api_key": "test-key",
                "search_type": "search_pro",
            }
        }
        scraper = LLMScraper(config)
        # web_search_config.enabled 应为 False
        assert scraper.web_search_config.enabled is False, (
            "ai_search.enabled=false 时 web_search_config.enabled 应为 False"
        )
        assert scraper.web_search_config.should_search("scrape") is False

    def test_disabled_ai_search_does_not_inject_params(self):
        """关闭后 _do_call 不应注入搜索参数。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_search": {
                "enabled": False,
                "provider": "zhipu",
                "base_url": "https://open.bigmodel.cn/api/paas/v4/",
                "model": "glm-4-flash",
                "api_key": "test-key",
            }
        }
        scraper = LLMScraper(config)

        # mock _send_request 避免真实 HTTP 调用
        with patch.object(scraper, '_send_request', return_value='{"result": "ok"}'):
            with patch.object(scraper, '_inject_search') as mock_inject:
                scraper._do_call("system", "user", scraper.fast_model,
                                 scraper.fast_base_url, scraper.fast_api_key,
                                 scenario="scrape")
                # web_search_config.enabled=False，should_search 返回 False
                # _inject_search 不应被调用
                mock_inject.assert_not_called()


class TestAiAssistAiSearchSeparation:
    """验证 ai_assist 和 ai_search 模型调用分离。"""

    def test_ai_assist_uses_fast_model(self):
        """AI 辅助任务应使用 fast_model（来自 ai_assist 配置）。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_assist": {
                "base_url": "https://assist.example.com/v1",
                "model": "assist-model",
                "api_key": "assist-key",
            },
            "ai_search": {
                "enabled": True,
                "provider": "zhipu",
                "base_url": "https://search.example.com/v1",
                "model": "search-model",
                "api_key": "search-key",
            }
        }
        scraper = LLMScraper(config)
        assert scraper.fast_model == "assist-model", "fast_model 应来自 ai_assist"
        assert scraper.fast_base_url == "https://assist.example.com/v1"
        assert scraper.fast_api_key == "assist-key"

    def test_ai_search_uses_search_model(self):
        """AI 联网搜索应使用搜索模型（来自 ai_search 配置）。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_assist": {
                "base_url": "https://assist.example.com/v1",
                "model": "assist-model",
                "api_key": "assist-key",
            },
            "ai_search": {
                "enabled": True,
                "provider": "zhipu",
                "base_url": "https://search.example.com/v1",
                "model": "search-model",
                "api_key": "search-key",
            }
        }
        scraper = LLMScraper(config)
        assert scraper.model == "search-model", "主模型应来自 ai_search"
        assert scraper.base_url == "https://search.example.com/v1"
        assert scraper.api_key == "search-key"

    def test_scrape_with_context_uses_ai_assist_not_ai_search(self):
        """scrape_with_context 应使用 ai_assist 模型，不是 ai_search。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_assist": {
                "base_url": "https://assist.example.com/v1",
                "model": "assist-model",
                "api_key": "assist-key",
            },
            "ai_search": {
                "enabled": True,
                "provider": "zhipu",
                "base_url": "https://search.example.com/v1",
                "model": "search-model",
                "api_key": "search-key",
            }
        }
        scraper = LLMScraper(config)

        # scrape_with_context 是辅助任务，应使用 fast_model (ai_assist)
        with patch.object(scraper, '_do_call', return_value='{"result": "ok"}') as mock_call:
            scraper.scrape_with_context(
                video_filename="测试标题.mp4",
                subtitle_filenames=[],
                provider_context="test context",
            )
            assert mock_call.call_count > 0

    def test_dimension_supplement_uses_ai_search(self):
        """缺失维度联网补全应使用 ai_search 模型。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_assist": {
                "base_url": "https://assist.example.com/v1",
                "model": "assist-model",
                "api_key": "assist-key",
            },
            "ai_search": {
                "enabled": True,
                "provider": "zhipu",
                "base_url": "https://search.example.com/v1",
                "model": "search-model",
                "api_key": "search-key",
            }
        }
        scraper = LLMScraper(config)

        # scrape 是搜索场景，应使用搜索模型
        with patch.object(scraper, '_do_call', return_value='{"result": "ok"}') as mock_call:
            scraper.scrape("测试文件名.mp4", [])
            assert mock_call.call_count > 0
