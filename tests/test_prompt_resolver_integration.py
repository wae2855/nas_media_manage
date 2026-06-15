"""PromptResolver 全路径接入测试。

验证用户配置的提示词真实传入 _do_call。
"""

from unittest.mock import patch

import pytest


class TestPromptResolverIntegration:
    """验证 PromptResolver 提示词真实进入运行时。"""

    def test_dimension_mapping_prompt_used_in_scrape_with_context(self):
        """配置 prompt_dimension_mapping 后，scrape_with_context 使用自定义提示词。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        custom_prompt = "自定义维度映射提示词：请将Provider数据映射到维度"
        config = {
            "ai_assist": {
                "base_url": "https://test.example.com/v1",
                "model": "test-model",
                "api_key": "test-key",
                "prompt_dimension_mapping": custom_prompt,
            }
        }
        scraper = LLMScraper(config)

        with patch.object(scraper, '_do_call', return_value='{"result": "ok"}') as mock_call:
            scraper.scrape_with_context(
                video_filename="test.mp4",
                subtitle_filenames=[],
                provider_context="test context",
            )
            # 验证 _do_call 被调用且 system_prompt 包含自定义提示词
            assert mock_call.call_count > 0
            call_args = mock_call.call_args
            system_prompt = call_args[0][0] if call_args else ""
            assert custom_prompt in system_prompt, (
                f"system_prompt 应包含自定义提示词，实际: {system_prompt[:200]}"
            )

    def test_dimension_supplement_prompt_used_in_scrape(self):
        """配置 prompt_dimension_supplement 后，scrape 使用自定义提示词。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        custom_prompt = "自定义维度补全提示词：请联网搜索缺失维度"
        config = {
            "ai_search": {
                "enabled": True,
                "provider": "zhipu",
                "base_url": "https://test.example.com/v1",
                "model": "test-model",
                "api_key": "test-key",
                "prompt_dimension_supplement": custom_prompt,
            }
        }
        scraper = LLMScraper(config)

        with patch.object(scraper, '_do_call', return_value='{"result": "ok"}') as mock_call:
            scraper.scrape("test.mp4", [])
            assert mock_call.call_count > 0
            call_args = mock_call.call_args
            system_prompt = call_args[0][0] if call_args else ""
            assert custom_prompt in system_prompt, (
                f"system_prompt 应包含自定义提示词，实际: {system_prompt[:200]}"
            )

    def test_empty_prompt_falls_back_to_default(self):
        """空提示词时回退到 LLMPromptBuilder 默认值。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_assist": {
                "base_url": "https://test.example.com/v1",
                "model": "test-model",
                "api_key": "test-key",
                "prompt_dimension_mapping": "",  # 空
            }
        }
        scraper = LLMScraper(config)

        with patch.object(scraper, '_do_call', return_value='{"result": "ok"}') as mock_call:
            scraper.scrape_with_context(
                video_filename="test.mp4",
                subtitle_filenames=[],
                provider_context="test context",
            )
            assert mock_call.call_count > 0
            call_args = mock_call.call_args
            system_prompt = call_args[0][0] if call_args else ""
            # 应包含 LLMPromptBuilder 的默认内容
            assert len(system_prompt) > 0
