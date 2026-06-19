"""兼容入口:llm_scraper 已迁移到 media_importer.features.scraping.llm_scraper。

本文件保留为旧路径兼容层,请勿新增依赖。生产代码应直接 import 新路径。

注意:re-export 包含旧 llm_scraper.py 顶层曾暴露的全部符号,以兼容测试和老代码
通过 `from media_importer.scraper.llm_scraper import X` 的入口。
"""

from media_importer.features.scraping.llm_scraper import LLMScraper  # noqa: F401
from media_importer.features.scraping.errors import LLMScrapeError  # noqa: F401
from media_importer.features.scraping.errors import LLMApiError  # noqa: F401
from media_importer.features.scraping.errors import LLMWebSearchError  # noqa: F401
from media_importer.features.scraping.llm_match_assist import _assemble_prompt  # noqa: F401