"""维度解析服务：基于显式来源记录逐维度追踪真实来源。

调用方必须传入显式的来源映射，不允许依赖 ai_invoked 全局推断。

处理顺序：
1. 文件分析维度 → file
2. Provider 直接映射维度 → provider:{provider_type}
3. AI 辅助分析维度 → ai_assist
4. AI 联网搜索维度 → ai_search
5. 未在任何显式来源中的维度 → unknown
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class DimensionResolutionResult:
    """维度解析结果。"""
    dimensions: dict = field(default_factory=dict)
    dim_sources: dict = field(default_factory=dict)


def resolve_dimension_sources(
    scrape_result: dict,
    file_dimensions: dict,
    provider_type: str = "tmdb",
    provider_dim_names: Optional[Set[str]] = None,
    ai_assist_dim_names: Optional[Set[str]] = None,
    ai_search_dim_names: Optional[Set[str]] = None,
) -> DimensionResolutionResult:
    """基于显式来源记录逐维度解析来源。

    Args:
        scrape_result: 刮削结果，包含 dimensions 字段
        file_dimensions: 文件分析维度 {dim_name: {value: ...}}
        provider_type: Provider 类型 (tmdb/douban)
        provider_dim_names: Provider 直接映射的维度名集合
        ai_assist_dim_names: AI 辅助分析产出的维度名集合
        ai_search_dim_names: AI 联网搜索产出的维度名集合

    Returns:
        DimensionResolutionResult 包含维度值、来源和确认原因

    来源判定优先级（高到低）：
    1. file_dimensions 中的维度 → file
    2. provider_dim_names 中的维度 → provider:{provider_type}
    3. ai_assist_dim_names 中的维度 → ai_assist
    4. ai_search_dim_names 中的维度 → ai_search
    5. 其他 → unknown
    """
    dimensions = scrape_result.get("dimensions", {}) or {}
    provider_dim_names = provider_dim_names or set()
    ai_assist_dim_names = ai_assist_dim_names or set()
    ai_search_dim_names = ai_search_dim_names or set()

    sources = {}

    file_dim_names = set(file_dimensions.keys()) if file_dimensions else set()

    for dim_name in dimensions:
        if dim_name in file_dim_names:
            sources[dim_name] = "file"
        elif dim_name in provider_dim_names:
            sources[dim_name] = f"provider:{provider_type}"
        elif dim_name in ai_assist_dim_names:
            sources[dim_name] = "ai_assist"
        elif dim_name in ai_search_dim_names:
            sources[dim_name] = "ai_search"
        else:
            sources[dim_name] = "unknown"

    return DimensionResolutionResult(
        dimensions=dimensions,
        dim_sources=sources,
    )
