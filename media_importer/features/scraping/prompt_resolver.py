"""提示词解析器：从配置中解析各场景提示词。

当前事实源：所有 AI 提示词只通过 ai_assist.prompt_* / ai_search.prompt_dimension_supplement
配置项管理，运行时通过 PromptResolver 读取。

职责边界：
- PromptResolver：负责从配置项（ai_assist.prompt_* / ai_search.prompt_dimension_supplement）读取用户自定义提示词
- LLMPromptBuilder：仅作为内置默认提示词（DEFAULT_SYSTEM_PROMPT、provider context template）的兜底实现

运行时调用方（llm_scraper.py）先尝试 PromptResolver.get_*_prompt()，
返回 None（空字符串）时回退到 LLMPromptBuilder 的对应方法。
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PromptResolver:
    """提示词解析器，从配置中解析各场景提示词。

    用户配置的提示词为空字符串时，get_*_prompt() 返回 None，
    调用方应回退到 LLMPromptBuilder 的内置默认提示词。
    """

    prompt_title_clean: str = ""
    prompt_match_assist: str = ""
    prompt_dimension_mapping: str = ""
    prompt_source_clean: str = ""
    prompt_dimension_supplement: str = ""

    @classmethod
    def from_config(cls, config: dict) -> "PromptResolver":
        """从配置字典构建 PromptResolver。

        优先读取 ai_assist / ai_search 中的用户配置提示词。
        """
        from media_importer.core.config_view import ConfigView

        cfg_view = ConfigView.from_dict(config)
        ai_assist = cfg_view.ai_assist
        ai_search = cfg_view.ai_search

        return cls(
            prompt_title_clean=ai_assist.prompt_title_clean or "",
            prompt_match_assist=ai_assist.prompt_match_assist or "",
            prompt_dimension_mapping=ai_assist.prompt_dimension_mapping or "",
            prompt_source_clean=ai_assist.prompt_source_clean or "",
            prompt_dimension_supplement=ai_search.prompt_dimension_supplement or "",
        )

    def get_title_clean_prompt(self) -> Optional[str]:
        """获取标题清洗提示词，空字符串返回 None（使用默认值）。"""
        return self.prompt_title_clean or None

    def get_match_assist_prompt(self) -> Optional[str]:
        """获取匹配辅助提示词，空字符串返回 None（使用默认值）。"""
        return self.prompt_match_assist or None

    def get_dimension_mapping_prompt(self) -> Optional[str]:
        """获取维度映射提示词，空字符串返回 None（使用默认值）。"""
        return self.prompt_dimension_mapping or None

    def get_source_clean_prompt(self) -> Optional[str]:
        """获取源目录清理提示词，空字符串返回 None（使用默认值）。"""
        return self.prompt_source_clean or None

    def get_dimension_supplement_prompt(self) -> Optional[str]:
        """获取维度补全提示词，空字符串返回 None（使用默认值）。"""
        return self.prompt_dimension_supplement or None
