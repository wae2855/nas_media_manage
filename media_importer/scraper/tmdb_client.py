"""兼容入口:tmdb_client 已迁移到 media_importer.features.providers.tmdb_client。

本文件保留为旧路径兼容层,请勿新增依赖。生产代码应直接 import 新路径。
"""

from media_importer.features.providers.tmdb_client import TMDbClient  # noqa: F401
from media_importer.features.providers.tmdb_client import TMDbError  # noqa: F401