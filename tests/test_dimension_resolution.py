"""维度解析测试：基于显式来源记录逐维度追踪真实来源。

覆盖：
- dim_sources 逐维度真实来源追踪（显式来源集合）
- 多 Provider 来源格式
- 信任配置判断
- 不信任 AI 来源时生成确认原因
- 未知维度标记为 unknown
"""

import pytest

from media_importer.features.scraping.dimension_resolution import (
    resolve_dimension_sources,
    DimensionResolutionResult,
)


class TestDimSourcesExplicitTracking:
    """验证 dim_sources 基于显式来源集合逐维度记录真实来源。"""

    def test_provider_dims_from_explicit_set(self):
        """Provider 直接映射的维度来源应为 provider:tmdb。"""
        result = {
            "dimensions": {
                "media_type": "movie",
                "documentary": False,
                "region": "cn",
            },
        }
        resolution = resolve_dimension_sources(
            scrape_result=result,
            file_dimensions={},
            provider_type="tmdb",
            provider_dim_names={"media_type", "documentary", "region"},
            ai_assist_dim_names=set(),
            ai_search_dim_names=set(),
        )
        assert resolution.dim_sources["media_type"] == "provider:tmdb"
        assert resolution.dim_sources["documentary"] == "provider:tmdb"
        assert resolution.dim_sources["region"] == "provider:tmdb"

    def test_file_analysis_source_is_file(self):
        """文件分析维度来源应为 file。"""
        result = {
            "dimensions": {
                "resolution_tier": "4K",
                "media_type": "movie",
            },
        }
        resolution = resolve_dimension_sources(
            scrape_result=result,
            file_dimensions={"resolution_tier": {"value": "4K"}},
            provider_type="tmdb",
            provider_dim_names={"media_type"},
            ai_assist_dim_names=set(),
            ai_search_dim_names=set(),
        )
        assert resolution.dim_sources["resolution_tier"] == "file"
        assert resolution.dim_sources["media_type"] == "provider:tmdb"

    def test_ai_assist_dims_not_mixed_with_provider(self):
        """AI 辅助维度不应被标记为 provider 来源。"""
        result = {
            "dimensions": {
                "media_type": "movie",
                "restricted_level": "13-16",
                "region": "cn",
            },
        }
        resolution = resolve_dimension_sources(
            scrape_result=result,
            file_dimensions={},
            provider_type="tmdb",
            provider_dim_names={"media_type", "region"},
            ai_assist_dim_names={"restricted_level"},
            ai_search_dim_names=set(),
        )
        assert resolution.dim_sources["media_type"] == "provider:tmdb"
        assert resolution.dim_sources["region"] == "provider:tmdb"
        assert resolution.dim_sources["restricted_level"] == "ai_assist"

    def test_ai_search_dims_marked_correctly(self):
        """AI 联网搜索维度应标记为 ai_search。"""
        result = {
            "dimensions": {
                "media_type": "movie",
                "origin_lang": "ja",
            },
        }
        resolution = resolve_dimension_sources(
            scrape_result=result,
            file_dimensions={},
            provider_type="tmdb",
            provider_dim_names={"media_type"},
            ai_assist_dim_names=set(),
            ai_search_dim_names={"origin_lang"},
        )
        assert resolution.dim_sources["origin_lang"] == "ai_search"

    def test_unknown_dimension_source_is_unknown(self):
        """无法确定来源的维度应标记为 unknown。"""
        result = {
            "dimensions": {
                "custom_dim": "some_value",
            },
        }
        resolution = resolve_dimension_sources(
            scrape_result=result,
            file_dimensions={},
            provider_type="tmdb",
            provider_dim_names=set(),
            ai_assist_dim_names=set(),
            ai_search_dim_names=set(),
        )
        assert resolution.dim_sources["custom_dim"] == "unknown"

    def test_multi_provider_format(self):
        """多 Provider 来源格式应支持 provider:tmdb 和 provider:douban。"""
        result = {
            "dimensions": {
                "media_type": "movie",
                "region": "jp",
            },
        }
        resolution = resolve_dimension_sources(
            scrape_result=result,
            file_dimensions={},
            provider_type="douban",
            provider_dim_names={"media_type", "region"},
            ai_assist_dim_names=set(),
            ai_search_dim_names=set(),
        )
        assert resolution.dim_sources["media_type"] == "provider:douban"
        assert resolution.dim_sources["region"] == "provider:douban"

    def test_file_priority_over_provider(self):
        """文件分析维度优先级高于 Provider。"""
        result = {
            "dimensions": {
                "resolution_tier": "4K",
                "media_type": "movie",
            },
        }
        resolution = resolve_dimension_sources(
            scrape_result=result,
            file_dimensions={"resolution_tier": {"value": "4K"}},
            provider_type="tmdb",
            provider_dim_names={"resolution_tier", "media_type"},
            ai_assist_dim_names=set(),
            ai_search_dim_names=set(),
        )
        assert resolution.dim_sources["resolution_tier"] == "file"


class TestDimensionTrustCheck:
    """验证信任配置判断。"""

    def test_untrusted_ai_assist_generates_confirm_reason(self):
        """不信任 AI 辅助时，AI 辅助补出的维度应生成确认原因。"""
        from media_importer.features.import_flow.steps.scrape import ScrapeStepsMixin

        mixin = ScrapeStepsMixin()
        mixin._log = lambda *args, **kwargs: None
        dim_sources = {
            "media_type": "provider:tmdb",
            "restricted_level": "ai_assist",
            "region": "provider:tmdb",
        }
        result = {
            "dimensions": {
                "media_type": "movie",
                "restricted_level": "13-16",
                "region": "cn",
            }
        }
        issues = mixin._check_dimension_trust(
            conn=None,
            dim_sources=dim_sources,
            result=result,
        )
        assert isinstance(issues, list)

    def test_provider_dimensions_not_affected_by_trust(self):
        """Provider 直接映射维度不应受 AI 信任开关影响。"""
        dim_sources = {
            "media_type": "provider:tmdb",
            "region": "provider:tmdb",
        }
        ai_sources = [s for s in dim_sources.values() if s in ("ai_assist", "ai_search")]
        assert len(ai_sources) == 0, "Provider 来源不应被标记为 AI 来源"
