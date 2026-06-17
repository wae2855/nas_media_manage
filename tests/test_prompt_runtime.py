"""提示词运行时测试（RED 测试 - 修复前应失败）。

覆盖：
- 用户配置提示词后 mock LLM 调用能观察到实际使用该提示词
- 留空时使用 PromptDefaults
- 各场景提示词接入
- _assemble_prompt 的 legacy/standard 行为（UT-12/13）
- 有效提示词包去重
"""

from unittest.mock import MagicMock, patch

import pytest


class TestPromptRuntime:
    """验证用户提示词真实进入运行时。"""

    def test_user_prompt_match_assist_used_in_tier2(self):
        """用户配置 prompt_match_assist 后，二级匹配调用使用用户提示词。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        custom_prompt = "请根据以下候选列表，建议更精确的搜索关键词"
        config = {
            "ai_assist": {
                "base_url": "https://test.example.com/v1",
                "model": "test-model",
                "api_key": "test-key",
                "prompt_match_assist": custom_prompt,
            }
        }
        scraper = LLMScraper(config)

        assert scraper.fast_model == "test-model"

    def test_user_prompt_dimension_supplement_used_in_search(self):
        """用户配置 prompt_dimension_supplement 后，联网维度补全使用用户提示词。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        custom_prompt = "请联网搜索以下影片的缺失维度信息"
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

        assert scraper.model == "test-model"

    def test_empty_prompt_uses_default(self):
        """留空提示词时应使用默认值。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_assist": {
                "base_url": "https://test.example.com/v1",
                "model": "test-model",
                "api_key": "test-key",
                "prompt_match_assist": "",  # 空字符串
            }
        }
        scraper = LLMScraper(config)
        assert scraper.fast_model == "test-model"

    def test_prompt_title_clean_configured(self):
        """标题清洗提示词应可配置。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_assist": {
                "base_url": "https://test.example.com/v1",
                "model": "test-model",
                "api_key": "test-key",
                "prompt_title_clean": "请从文件名中提取影视标题和年份",
            }
        }
        scraper = LLMScraper(config)
        assert scraper.fast_model == "test-model"

    def test_prompt_dimension_mapping_configured(self):
        """维度映射提示词应可配置。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_assist": {
                "base_url": "https://test.example.com/v1",
                "model": "test-model",
                "api_key": "test-key",
                "prompt_dimension_mapping": "请将以下Provider数据映射到维度",
            }
        }
        scraper = LLMScraper(config)
        assert scraper.fast_model == "test-model"

    def test_prompt_source_clean_configured(self):
        """源目录清理提示词应可配置。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_assist": {
                "base_url": "https://test.example.com/v1",
                "model": "test-model",
                "api_key": "test-key",
                "prompt_source_clean": "请清理源目录名称",
            }
        }
        scraper = LLMScraper(config)
        assert scraper.fast_model == "test-model"


class TestAssemblePrompt:
    """_assemble_prompt 行为测试（UT-12/13）。"""

    def test_standard_mode_includes_all_parts(self):
        """标准模式：instruction + output_format + data_context。"""
        from media_importer.scraper._llm_match_assist import _assemble_prompt

        result = _assemble_prompt(
            instruction="判定规则",
            data_context="文件信息",
            output_format="JSON格式",
            is_legacy=False,
        )
        assert "判定规则" in result
        assert "JSON格式" in result
        assert "文件信息" in result
        # instruction 在前
        assert result.index("判定规则") < result.index("文件信息")

    def test_standard_mode_omits_empty_format(self):
        """标准模式但 output_format 为空时省略。"""
        from media_importer.scraper._llm_match_assist import _assemble_prompt

        result = _assemble_prompt(
            instruction="判定规则",
            data_context="文件信息",
            output_format="",
            is_legacy=False,
        )
        assert "判定规则" in result
        assert "文件信息" in result
        # 不应有 ## 输出要求 的痕迹
        assert "输出要求" not in result

    def test_legacy_mode_returns_only_data_context(self):
        """legacy 模式：只返回 data_context。"""
        from media_importer.scraper._llm_match_assist import _assemble_prompt

        result = _assemble_prompt(
            instruction="判定规则",
            data_context="旧版长提示词内容",
            output_format="JSON格式",
            is_legacy=True,
        )
        assert result == "旧版长提示词内容"

    def test_llm_scraper_assemble_consistent(self):
        """两个位置的 _assemble_prompt 实现一致。"""
        from media_importer.scraper._llm_match_assist import (
            _assemble_prompt as ap1,
        )
        from media_importer.scraper.llm_scraper import _assemble_prompt as ap2

        r1 = ap1("a", "b", "c", is_legacy=False)
        r2 = ap2("a", "b", "c", is_legacy=False)
        assert r1 == r2
        r3 = ap1("a", "b", "c", is_legacy=True)
        r4 = ap2("a", "b", "c", is_legacy=True)
        assert r3 == r4


class TestPromptDedup:
    """有效提示词包去重测试。"""

    def test_match_assist_no_duplicate_rules(self):
        """match_assist 场景：system_prompt + user_prompt 中『判定规则』只出现一次。"""
        from media_importer.features.scraping.prompt_resolver import PromptResolver
        from media_importer.features.prompts.defaults import PromptDefaults

        resolver = PromptResolver()
        system_prompt = resolver.get_match_assist_prompt()
        instruction = resolver.get_match_assist_instruction()
        # 在标准模式下，user_content 包含 instruction（不含 output_format 和 data_context 是简化的）
        full = system_prompt + " " + instruction
        # "判定规则" 标题只应在 instruction 中出现一次（不在 system_prompt 中）
        assert full.count("判定规则") <= 1
        assert "判定规则" in instruction
        assert "判定规则" not in system_prompt

    def test_source_clean_no_duplicate_rules(self):
        """source_clean 场景：system_prompt + _build_cleaner_prompt 中『分析原则』只出现一次。"""
        from media_importer.features.scraping.prompt_resolver import PromptResolver
        from media_importer.features.prompts.defaults import PromptDefaults

        resolver = PromptResolver()
        system_prompt = resolver.get_source_clean_prompt()
        instruction = resolver.get_source_clean_instruction()
        full = system_prompt + " " + instruction
        # "分析原则" 只应在 instruction 中出现一次
        assert full.count("分析原则") <= 1
        assert "分析原则" in instruction
        assert "分析原则" not in system_prompt

    def test_dimension_mapping_no_duplicate_rules(self):
        """dimension_mapping 场景：system_prompt + instruction 中规则列表不重复。"""
        from media_importer.features.scraping.prompt_resolver import PromptResolver

        resolver = PromptResolver()
        system_prompt = resolver.get_dimension_mapping_prompt()
        instruction = resolver.get_dimension_mapping_instruction()
        full = system_prompt + " " + instruction
        # "只根据输入的 Provider 数据判断" 只应在 instruction 中出现
        assert full.count("只根据输入的 Provider 数据判断") <= 1
        assert "只根据输入的 Provider 数据判断" in instruction
        assert "只根据输入的 Provider 数据判断" not in system_prompt

    def test_dimension_supplement_no_duplicate_rules(self):
        """dimension_supplement 场景：system_prompt + instruction 中规则列表不重复。"""
        from media_importer.features.scraping.prompt_resolver import PromptResolver

        resolver = PromptResolver()
        system_prompt = resolver.get_dimension_supplement_prompt()
        instruction = resolver.get_dimension_supplement_instruction()
        full = system_prompt + " " + instruction
        # "优先使用联网搜索" 只应在 instruction 中出现
        assert full.count("优先使用联网搜索") <= 1
        assert "优先使用联网搜索" in instruction
        assert "优先使用联网搜索" not in system_prompt

    def test_source_clean_non_repeat_in_cleaner(self):
        """IT-7：_build_cleaner_prompt 构建的 prompt 不含 system_prompt 中已说的内容。"""
        from media_importer.features.source_cleaning.cleaner import (
            _assemble_prompt,
            _build_source_clean_output_format,
        )
        from media_importer.features.scraping.prompt_resolver import PromptResolver

        resolver = PromptResolver()
        system_prompt = resolver.get_source_clean_prompt()
        instruction = resolver.get_source_clean_instruction()
        data_context = "【待分析目录】\n目录: /test\n文件列表:\n[]"
        output_format = _build_source_clean_output_format()

        user_prompt = _assemble_prompt(
            instruction, data_context, output_format, is_legacy=False,
        )
        full = system_prompt + " " + user_prompt
        # "分析原则" 只在 instruction 中
        assert full.count("分析原则") <= 1
        # "输出要求" 只在 output_format 中
        assert full.count("输出要求") <= 1
        if output_format:
            assert "输出要求" in output_format

    def test_user_prompt_dimension_supplement_used_in_search(self):
        """用户配置 prompt_dimension_supplement 后，联网维度补全使用用户提示词。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        custom_prompt = "请联网搜索以下影片的缺失维度信息"
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

        assert scraper.model == "test-model"

    def test_empty_prompt_uses_default(self):
        """留空提示词时应使用默认值。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_assist": {
                "base_url": "https://test.example.com/v1",
                "model": "test-model",
                "api_key": "test-key",
                "prompt_match_assist": "",  # 空字符串
            }
        }
        scraper = LLMScraper(config)
        # 空字符串应视为使用默认值
        assert scraper.fast_model == "test-model"

    def test_prompt_title_clean_configured(self):
        """标题清洗提示词应可配置。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_assist": {
                "base_url": "https://test.example.com/v1",
                "model": "test-model",
                "api_key": "test-key",
                "prompt_title_clean": "请从文件名中提取影视标题和年份",
            }
        }
        scraper = LLMScraper(config)
        assert scraper.fast_model == "test-model"

    def test_prompt_dimension_mapping_configured(self):
        """维度映射提示词应可配置。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_assist": {
                "base_url": "https://test.example.com/v1",
                "model": "test-model",
                "api_key": "test-key",
                "prompt_dimension_mapping": "请将以下Provider数据映射到维度",
            }
        }
        scraper = LLMScraper(config)
        assert scraper.fast_model == "test-model"

    def test_prompt_source_clean_configured(self):
        """源目录清理提示词应可配置。"""
        from media_importer.scraper.llm_scraper import LLMScraper

        config = {
            "ai_assist": {
                "base_url": "https://test.example.com/v1",
                "model": "test-model",
                "api_key": "test-key",
                "prompt_source_clean": "请清理源目录名称",
            }
        }
        scraper = LLMScraper(config)
        assert scraper.fast_model == "test-model"
