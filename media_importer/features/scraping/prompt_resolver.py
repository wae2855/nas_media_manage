"""提示词解析器：从配置中解析各场景提示词。

当前事实源：所有 AI 提示词只通过 ai_assist.prompt_* / ai_search.prompt_dimension_supplement
配置项管理，运行时通过 PromptResolver 读取。

职责边界：
- PromptDefaults：唯一真默认值事实源，PromptResolver 留空时回退。
- PromptResolver：从配置项（ai_assist.prompt_* / ai_search.prompt_dimension_supplement）读取用户自定义提示词，
  留空时返回 PromptDefaults 对应字段，确保调用方拿到永远非空字符串。
"""

from dataclasses import dataclass

from media_importer.features.prompts.defaults import PromptDefaults


@dataclass
class PromptResolver:
    """提示词解析器，从配置中解析各场景提示词。

    用户配置的提示词为空字符串时，get_*_prompt() 返回 PromptDefaults 的内置真默认值。
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

    def get_title_clean_prompt(self) -> str:
        """获取标题清洗提示词；留空时返回 PromptDefaults 内置真默认。"""
        return self.prompt_title_clean or PromptDefaults.TITLE_CLEAN

    def get_match_assist_prompt(self) -> str:
        """获取匹配辅助提示词；留空时返回 PromptDefaults 内置真默认。"""
        return self.prompt_match_assist or PromptDefaults.MATCH_ASSIST

    def get_dimension_mapping_prompt(self) -> str:
        """获取维度映射提示词；留空时返回 PromptDefaults 内置真默认。"""
        return self.prompt_dimension_mapping or PromptDefaults.DIMENSION_MAPPING

    def get_source_clean_prompt(self) -> str:
        """获取源目录清理提示词；留空时返回 PromptDefaults 内置真默认。"""
        return self.prompt_source_clean or PromptDefaults.SOURCE_CLEAN

    def get_dimension_supplement_prompt(self) -> str:
        """获取维度补全提示词；留空时返回 PromptDefaults 内置真默认。"""
        return self.prompt_dimension_supplement or PromptDefaults.DIMENSION_SUPPLEMENT