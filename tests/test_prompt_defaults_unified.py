"""PromptDefaults + PromptResolver 单元测试（覆盖 T1.1-T1.3）。

验证：
- get_all() 结构完整性
- get_*_prompt() 留空时返回 PromptDefaults 真默认
- 用户自定义值优先
- 各使用点无内联兜底
"""
import pytest

from media_importer.features.prompts.defaults import PromptDefaults
from media_importer.features.scraping.prompt_resolver import PromptResolver


# ========================================================================
# PromptDefaults
# ========================================================================

class TestPromptDefaults:
    def test_get_all_structure(self):
        """get_all() 返回 {prompts: {...}, descriptions: {...}}。"""
        result = PromptDefaults.get_all()
        assert "prompts" in result
        assert "descriptions" in result
        assert len(result["prompts"]) == 5
        assert len(result["descriptions"]) == 5
        for prompt_key in (
            "prompt_title_clean", "prompt_match_assist",
            "prompt_dimension_mapping", "prompt_dimension_supplement",
            "prompt_source_clean",
        ):
            assert prompt_key in result["prompts"]
            assert result["prompts"][prompt_key] != ""
            assert prompt_key in result["descriptions"]
            assert result["descriptions"][prompt_key] != ""

    def test_each_default_is_non_empty(self):
        """5 个默认提示词全部非空。"""
        assert PromptDefaults.TITLE_CLEAN != ""
        assert PromptDefaults.MATCH_ASSIST != ""
        assert PromptDefaults.DIMENSION_MAPPING != ""
        assert PromptDefaults.DIMENSION_SUPPLEMENT != ""
        assert PromptDefaults.SOURCE_CLEAN != ""

    def test_dimension_defaults_are_different(self):
        """DIMENSION_MAPPING 与 DIMENSION_SUPPLEMENT 不同（Phase 2 验收修复）。"""
        assert PromptDefaults.DIMENSION_MAPPING != PromptDefaults.DIMENSION_SUPPLEMENT

    def test_descriptions_cover_all_prompts(self):
        """每个 prompt 都有对应的描述。"""
        result = PromptDefaults.get_all()
        prompt_keys = set(result["prompts"].keys())
        desc_keys = set(result["descriptions"].keys())
        assert prompt_keys == desc_keys


# ========================================================================
# PromptResolver
# ========================================================================

class TestPromptResolverDefaults:
    def test_returns_default_when_empty(self):
        """get_*_prompt() 留空时返回 PromptDefaults 对应字段。"""
        r = PromptResolver()
        assert r.get_title_clean_prompt() == PromptDefaults.TITLE_CLEAN
        assert r.get_match_assist_prompt() == PromptDefaults.MATCH_ASSIST
        assert r.get_dimension_mapping_prompt() == PromptDefaults.DIMENSION_MAPPING
        assert r.get_dimension_supplement_prompt() == PromptDefaults.DIMENSION_SUPPLEMENT
        assert r.get_source_clean_prompt() == PromptDefaults.SOURCE_CLEAN

    def test_returns_user_value_when_configured(self):
        """配置了自定义值时返回用户值。"""
        r = PromptResolver(
            prompt_title_clean="my custom title prompt",
            prompt_dimension_mapping="my custom mapping prompt",
        )
        assert r.get_title_clean_prompt() == "my custom title prompt"
        assert r.get_dimension_mapping_prompt() == "my custom mapping prompt"

    def test_returns_default_when_field_empty_string(self):
        """空字符串时仍回退到 PromptDefaults。"""
        r = PromptResolver(prompt_title_clean="")
        assert r.get_title_clean_prompt() == PromptDefaults.TITLE_CLEAN


# ========================================================================
# 无内联兜底检查
# ========================================================================

class TestNoInlineFallback:
    def test_no_inline_fallback_in_resolver(self):
        """PromptResolver.get_*_prompt() 使用 `or PromptDefaults.XXX` 而非内联字符串。"""
        import inspect
        for method_name in (
            "get_title_clean_prompt", "get_match_assist_prompt",
            "get_dimension_mapping_prompt", "get_source_clean_prompt",
            "get_dimension_supplement_prompt",
        ):
            method = getattr(PromptResolver, method_name)
            source = inspect.getsource(method)
            assert "PromptDefaults." in source, f"{method_name} 应引用 PromptDefaults 而非内联兜底"
            assert "你是一个" not in source, f"{method_name} 不应包含内联兜底提示词"
