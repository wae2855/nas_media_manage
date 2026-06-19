"""兼容入口:_llm_match_assist 已迁移到 media_importer.features.scraping.llm_match_assist。

本文件保留为旧路径兼容层,请勿新增依赖。生产代码应直接 import 新路径。
"""

from media_importer.features.scraping.llm_match_assist import _assemble_prompt  # noqa: F401
from media_importer.features.scraping.llm_match_assist import _build_match_assist_context  # noqa: F401
from media_importer.features.scraping.llm_match_assist import _build_match_assist_output_format  # noqa: F401
from media_importer.features.scraping.llm_match_assist import _extract_title_impl  # noqa: F401
from media_importer.features.scraping.llm_match_assist import _tier2_correct_impl  # noqa: F401