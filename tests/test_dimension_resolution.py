"""维度解析测试：基于显式来源记录逐维度追踪真实来源。

覆盖：
- dim_sources 逐维度真实来源追踪（显式来源集合）
- 多 Provider 来源格式
- 信任配置判断
- 不信任 AI 来源时生成确认原因
- 未知维度标记为 unknown
"""


from media_importer.features.scraping.dimension_resolution import (
    resolve_dimension_sources,
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
        )
        assert resolution.dim_sources["resolution_tier"] == "file"
        assert resolution.dim_sources["media_type"] == "provider:tmdb"

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
        )
        assert resolution.dim_sources["resolution_tier"] == "file"


class TestDimensionTrustCheck:
    """验证信任配置判断。"""
