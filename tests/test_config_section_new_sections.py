"""build_section_config_update 新增 section 测试（RED - 修复前应失败）。

覆盖 T1.13：
- ai_apikey：合并 ai_assist/ai_search；*** 和 空 api_key 不覆盖
- ai_prompts：仅写入 prompt_* 字段
- ai_scene_strategy：5 场景完整；缺场景报错
"""
import pytest

from media_importer.features.configuration import build_section_config_update


def test_ai_apikey_merges_subsections():
    out = build_section_config_update('ai_apikey', {
        'ai_assist': {'api_key': '', 'model': 'gpt-4'},
        'ai_search': {'api_key': '***'},
    }, {
        'ai_assist': {'api_key': 'real-assist-key', 'model': 'old-m'},
        'ai_search': {'api_key': 'real-search-key', 'model': 'm2'},
    })
    assert out['ai_assist']['api_key'] == 'real-assist-key', out
    assert out['ai_assist']['model'] == 'gpt-4', out
    assert out['ai_search']['api_key'] == 'real-search-key', out


def test_ai_apikey_rejects_empty_data():
    with pytest.raises(ValueError) as exc_info:
        build_section_config_update('ai_apikey', {}, {})
    assert str(exc_info.value)  # any ValueError is acceptable


def test_ai_prompts_keeps_other_fields():
    out = build_section_config_update('ai_prompts', {
        'ai_assist': {'prompt_title_clean': 'my prompt'},
    }, {'ai_assist': {'base_url': 'http://a.com', 'model': 'm'}})
    assert out['ai_assist']['base_url'] == 'http://a.com'
    assert out['ai_assist']['model'] == 'm'
    assert out['ai_assist']['prompt_title_clean'] == 'my prompt'


def test_ai_prompts_writes_dimension_supplement_to_ai_search():
    out = build_section_config_update('ai_prompts', {
        'ai_search': {'prompt_dimension_supplement': 'my supplement prompt'},
    }, {'ai_search': {'api_key': 'real-key'}})
    assert 'ai_search' in out
    assert out['ai_search']['prompt_dimension_supplement'] == 'my supplement prompt'
    assert out['ai_search']['api_key'] == 'real-key'


def test_ai_scene_strategy_writes_all_five_scenes():
    data = {scene: {'primary': 'ai_assist', 'fallback': ''} for scene in (
        'dimension_supplement', 'dimension_mapping', 'title_clean',
        'match_assist', 'source_clean',
    )}
    out = build_section_config_update('ai_scene_strategy', data, {})
    assert 'ai_scene_strategy' in out
    assert set(out['ai_scene_strategy'].keys()) == {
        'dimension_supplement', 'dimension_mapping', 'title_clean',
        'match_assist', 'source_clean',
    }


def test_ai_scene_strategy_missing_scene_raises():
    with pytest.raises(ValueError) as exc_info:
        build_section_config_update('ai_scene_strategy', {
            'match_assist': {'primary': 'ai_search', 'fallback': ''},
        }, {})
    assert '缺少场景' in str(exc_info.value)