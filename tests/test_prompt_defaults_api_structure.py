"""/api/config/prompt-defaults 响应结构测试。

覆盖 T1.12：
- 返回结构含 `prompts` 和 `descriptions` 两层
- prompts 包含 5 个场景的默认提示词
- descriptions 包含 5 个场景的功能说明文案
"""
from media_importer.features.prompts import PromptDefaults


def test_prompt_defaults_returns_prompts_and_descriptions():
    """T1.12 验收：/api/config/prompt-defaults 返回结构升级。"""
    all_data = PromptDefaults.get_all()
    assert "prompts" in all_data, f"返回结构应含 prompts 层，实际 keys: {list(all_data.keys())}"
    assert "instructions" in all_data, f"返回结构应含 instructions 层"
    expected_prompt_keys = {
        "prompt_title_clean", "prompt_match_assist",
        "prompt_dimension_mapping", "prompt_dimension_supplement",
        "prompt_source_clean",
    }
    expected_instruction_keys = {
        "prompt_match_assist_instruction",
        "prompt_dimension_mapping_instruction",
        "prompt_dimension_supplement_instruction",
        "prompt_source_clean_instruction",
    }
    assert set(all_data["prompts"].keys()) == expected_prompt_keys
    assert set(all_data["instructions"].keys()) == expected_instruction_keys
    expected_desc_keys = expected_prompt_keys | expected_instruction_keys
    assert set(all_data["descriptions"].keys()) == expected_desc_keys
    # 每条 description 都是非空字符串
    for key, desc in all_data["descriptions"].items():
        assert isinstance(desc, str) and desc.strip(), f"{key} description 应为非空字符串"


def test_prompt_defaults_prompts_match_default_constants():
    """T1.12：prompts 的 5 个值与 PromptDefaults 字段一致。"""
    all_data = PromptDefaults.get_all()
    assert all_data["prompts"]["prompt_title_clean"] == PromptDefaults.TITLE_CLEAN
    assert all_data["prompts"]["prompt_match_assist"] == PromptDefaults.MATCH_ASSIST
    assert all_data["prompts"]["prompt_dimension_mapping"] == PromptDefaults.DIMENSION_MAPPING
    assert all_data["prompts"]["prompt_dimension_supplement"] == PromptDefaults.DIMENSION_SUPPLEMENT
    assert all_data["prompts"]["prompt_source_clean"] == PromptDefaults.SOURCE_CLEAN