"""维度 trace 数据链路测试。

验证 scrape_trace 中的 provider_dimensions / ai_assist_dimensions / ai_search_dimensions
被正确写入和读取。
"""

import pytest

from media_importer.features.scraping.dimension_resolution import resolve_dimension_sources


class TestDimensionTraceDataLink:
    """验证 scrape_trace 显式来源被正确解析。"""

    def test_provider_dims_from_trace(self):
        """scrape_trace.provider_dimensions 中的维度应标记为 provider:tmdb。"""
        result = {
            "dimensions": {
                "media_type": "movie",
                "documentary": False,
                "region": "cn",
            },
            "scrape_trace": {
                "provider_dimensions": {
                    "media_type": "tmdb",
                    "documentary": "tmdb",
                    "region": "tmdb",
                },
            },
        }
        provider_dim_names = set(result["scrape_trace"]["provider_dimensions"].keys())
        resolution = resolve_dimension_sources(
            scrape_result=result,
            file_dimensions={},
            provider_type="tmdb",
            provider_dim_names=provider_dim_names,
            ai_assist_dim_names=set(),
            ai_search_dim_names=set(),
        )
        assert resolution.dim_sources["media_type"] == "provider:tmdb"
        assert resolution.dim_sources["documentary"] == "provider:tmdb"
        assert resolution.dim_sources["region"] == "provider:tmdb"

    def test_mixed_sources_from_trace(self):
        """混合来源：provider + ai_assist + ai_search 各维度正确标记。"""
        result = {
            "dimensions": {
                "media_type": "movie",
                "documentary": False,
                "restricted_level": "13-16",
                "origin_lang": "ja",
                "resolution_tier": "4K",
            },
            "scrape_trace": {
                "provider_dimensions": {
                    "media_type": "tmdb",
                    "documentary": "tmdb",
                },
                "ai_assist_dimensions": {
                    "restricted_level": "ai_assist",
                },
                "ai_search_dimensions": {
                    "origin_lang": "ai_search",
                },
            },
        }
        provider_dim_names = set(result["scrape_trace"]["provider_dimensions"].keys())
        ai_assist_dim_names = set(result["scrape_trace"]["ai_assist_dimensions"].keys())
        ai_search_dim_names = set(result["scrape_trace"]["ai_search_dimensions"].keys())

        resolution = resolve_dimension_sources(
            scrape_result=result,
            file_dimensions={"resolution_tier": {"value": "4K"}},
            provider_type="tmdb",
            provider_dim_names=provider_dim_names,
            ai_assist_dim_names=ai_assist_dim_names,
            ai_search_dim_names=ai_search_dim_names,
        )
        assert resolution.dim_sources["media_type"] == "provider:tmdb"
        assert resolution.dim_sources["documentary"] == "provider:tmdb"
        assert resolution.dim_sources["restricted_level"] == "ai_assist"
        assert resolution.dim_sources["origin_lang"] == "ai_search"
        assert resolution.dim_sources["resolution_tier"] == "file"

    def test_no_trace_fallback_to_unknown(self):
        """无 scrape_trace 时，维度应标记为 unknown。"""
        result = {
            "dimensions": {
                "custom_dim": "value",
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
