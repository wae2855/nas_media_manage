import json
from typing import Dict, Any


class LLMPromptBuilder:
    """维度数据容器，供 LLMScraper 运行时读取维度列表。

    提示词构建功能已迁移至 PromptResolver + PromptDefaults。
    """

    def __init__(self, dimensions=None):
        self.dimensions = dimensions or []
        self._provider_prompts = {}

    def load_dimensions(self, dimensions):
        self.dimensions = dimensions
