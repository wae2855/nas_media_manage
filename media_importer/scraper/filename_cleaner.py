"""兼容入口：filename_cleaner 已迁移到 media_importer.features.scraping.filename_cleaner。

本文件保留为旧路径兼容层,请勿新增依赖。生产代码应直接 import 新路径。
"""

from media_importer.features.scraping.filename_cleaner import (  # noqa: F401
    FilenameCleaner,
)