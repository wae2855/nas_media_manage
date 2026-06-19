"""兼容入口：title_matcher 已迁移到 media_importer.features.scraping.title_matcher。

本文件保留为旧路径兼容层,请勿新增依赖。生产代码应直接 import 新路径。
"""

from media_importer.features.scraping.title_matcher import (  # noqa: F401
    TitleMatcher,
    _similarity,
)