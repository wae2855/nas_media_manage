"""兼容入口:metadata_scrape_flow 已迁移到 media_importer.features.scraping.metadata_scrape_flow。

本文件保留为旧路径兼容层,请勿新增依赖。生产代码应直接 import 新路径。
"""

from media_importer.features.scraping.metadata_scrape_flow import _check_dimension_completeness  # noqa: F401
from media_importer.features.scraping.metadata_scrape_flow import _inject_trace_fields  # noqa: F401
from media_importer.features.scraping.metadata_scrape_flow import _apply_confidence_result  # noqa: F401
from media_importer.features.scraping.metadata_scrape_flow import _build_minimal_result  # noqa: F401
from media_importer.features.scraping.metadata_scrape_flow import _get_enabled_dims  # noqa: F401
from media_importer.features.scraping.metadata_scrape_flow import _do_ai_clean  # noqa: F401
from media_importer.features.scraping.metadata_scrape_flow import _do_provider_search  # noqa: F401
from media_importer.features.scraping.metadata_scrape_flow import _build_provider_only_result  # noqa: F401
from media_importer.features.scraping.metadata_scrape_flow import scrape_metadata  # noqa: F401
from media_importer.features.scraping.metadata_scrape_flow import _scrape_provider_first  # noqa: F401
from media_importer.features.scraping.metadata_scrape_flow import scrape_series_metadata  # noqa: F401