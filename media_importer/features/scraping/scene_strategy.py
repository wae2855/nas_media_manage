"""场景策略解析器：根据配置决定每个 AI 场景的模型调用顺序。

5 个场景：dimension_supplement / dimension_mapping / title_clean / match_assist / source_clean。
每个场景的 primary 必填，fallback 可空（空时只尝试 primary）。
"""

from media_importer.core.config_view import ConfigView


class SceneStrategyResolver:
    SCENE_KEYS = (
        "dimension_supplement",
        "dimension_mapping",
        "title_clean",
        "match_assist",
        "source_clean",
    )

    def __init__(self, view: ConfigView):
        self.view = view

    def model_sequence(self, scene: str) -> list:
        """返回 [primary] 或 [primary, fallback]，过滤空值和重复。"""
        if scene not in self.SCENE_KEYS:
            raise ValueError(f"未知场景: {scene}")
        section = getattr(self.view.ai_scene_strategy, scene)
        result = [section.primary] if section.primary else []
        if section.fallback and section.fallback not in result:
            result.append(section.fallback)
        return result