"""SceneStrategyResolver 单元测试（覆盖 T1.7 + 决策 14）。

验证：
- 默认值填充（来自 config_loader.setdefault）
- 用户自定义值保护
- primary 校验（空/无效）
- fallback 空值通过
- model_sequence 解析（无 fallback/有 fallback/去重）
- 未知场景抛错
"""
import os
import tempfile
from unittest.mock import patch

import pytest

from media_importer.features.scraping.scene_strategy import SceneStrategyResolver
from media_importer.core.config_view import ConfigView
from media_importer.core.config_loader import load_config


# ========================================================================
# Fixtures
# ========================================================================

def _make_view(**ai_scene_strategy_overrides):
    config = {
        "ai_scene_strategy": {
            "dimension_supplement": {"primary": "ai_assist", "fallback": ""},
            "dimension_mapping": {"primary": "ai_assist", "fallback": ""},
            "title_clean": {"primary": "ai_assist", "fallback": ""},
            "match_assist": {"primary": "ai_assist", "fallback": ""},
            "source_clean": {"primary": "ai_assist", "fallback": ""},
        },
    }
    config["ai_scene_strategy"].update(ai_scene_strategy_overrides)
    return ConfigView.from_dict(config)


def _load_minimal_config():
    """创建最小 YAML 并通过 load_config 加载，触发 setdefault 填充默认值。"""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write("{}")
    f.close()
    try:
        cfg = load_config(f.name)
    finally:
        os.unlink(f.name)
    return cfg


# ========================================================================
# 默认值（来自 config_loader.setdefault）
# ========================================================================

class TestSceneStrategyDefaults:
    def test_default_values_from_loader(self):
        """load_config({}) 后 5 个场景按 §2.1 默认值填充。"""
        cfg = _load_minimal_config()
        view = ConfigView.from_dict(cfg)
        assert view.ai_scene_strategy.dimension_supplement.primary == "ai_search"
        assert view.ai_scene_strategy.dimension_mapping.primary == "ai_assist"
        assert view.ai_scene_strategy.title_clean.primary == "ai_assist"
        assert view.ai_scene_strategy.match_assist.primary == "ai_search"
        assert view.ai_scene_strategy.source_clean.primary == "ai_assist"

    def test_default_values_fallback_empty(self):
        """load_config({}) 后所有场景 fallback 为空。"""
        cfg = _load_minimal_config()
        view = ConfigView.from_dict(cfg)
        for key in SceneStrategyResolver.SCENE_KEYS:
            section = getattr(view.ai_scene_strategy, key)
            assert section.fallback == "", f"{key}.fallback 应为空"


# ========================================================================
# 用户自定义值
# ========================================================================

class TestSceneStrategyUserOverride:
    def test_user_override_not_overwritten(self):
        """用户自定义值不被覆盖。"""
        resolver = SceneStrategyResolver(_make_view(
            dimension_supplement={"primary": "ai_search", "fallback": "ai_assist"},
        ))
        assert resolver.model_sequence("dimension_supplement") == ["ai_search", "ai_assist"]


# ========================================================================
# 校验
# ========================================================================

class TestSceneStrategyValidation:
    def test_primary_empty_raises(self):
        """empty primary 时 model_sequence 返回 []，_run_with_strategy_impl 兜底到 ai_search。"""
        resolver = SceneStrategyResolver(_make_view(
            dimension_mapping={"primary": "", "fallback": ""},
        ))
        assert resolver.model_sequence("dimension_mapping") == []

    def test_primary_invalid_still_accepted(self):
        """model_sequence 不校验值合法性（校验在上层 validator）。"""
        resolver = SceneStrategyResolver(_make_view(
            match_assist={"primary": "invalid_model", "fallback": ""},
        ))
        assert resolver.model_sequence("match_assist") == ["invalid_model"]

    def test_fallback_empty_ok(self):
        """fallback 为空时 model_sequence 返回 [primary]。"""
        resolver = SceneStrategyResolver(_make_view(
            title_clean={"primary": "ai_assist", "fallback": ""},
        ))
        assert resolver.model_sequence("title_clean") == ["ai_assist"]


# ========================================================================
# model_sequence 解析
# ========================================================================

class TestModelSequence:
    def test_no_fallback_returns_single(self):
        """fallback="" → [primary]。"""
        r = SceneStrategyResolver(_make_view(
            title_clean={"primary": "ai_search", "fallback": ""},
        ))
        assert r.model_sequence("title_clean") == ["ai_search"]

    def test_with_fallback_returns_two(self):
        """fallback 非空 → [primary, fallback]。"""
        r = SceneStrategyResolver(_make_view(
            source_clean={"primary": "ai_assist", "fallback": "ai_search"},
        ))
        assert r.model_sequence("source_clean") == ["ai_assist", "ai_search"]

    def test_dedup_removes_duplicate(self):
        """primary=fallback 时去重。"""
        r = SceneStrategyResolver(_make_view(
            dimension_supplement={"primary": "ai_search", "fallback": "ai_search"},
        ))
        assert r.model_sequence("dimension_supplement") == ["ai_search"]


# ========================================================================
# 未知场景
# ========================================================================

class TestUnknownScene:
    def test_unknown_scene_raises_value_error(self):
        """未知 scene 抛 ValueError。"""
        view = ConfigView.from_dict({})
        resolver = SceneStrategyResolver(view)
        with pytest.raises(ValueError, match="未知场景"):
            resolver.model_sequence("nonexistent_scene")
