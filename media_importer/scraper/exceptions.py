"""兼容入口:exceptions 已迁移到 media_importer.features.scraping.errors。

本文件保留为旧路径兼容层,请勿新增依赖。生产代码应直接 import 新路径。
"""

from media_importer.features.scraping.errors import LLMApiError  # noqa: F401
from media_importer.features.scraping.errors import LLMWebSearchError  # noqa: F401
from media_importer.features.scraping.errors import LLMScrapeError  # noqa: F401