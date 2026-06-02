# Scraping Architecture

## Responsibilities

- 清洗文件名。
- 调用 Provider 搜索元数据。
- 调用 LLM 整理结果。
- 计算置信度。
- 映射分类维度。

## Entry Points

- `media_importer/scraper/metadata_scraper.py`
- `media_importer/scraper/llm_scraper.py`
- `media_importer/scraper/llm_prompts.py`
- `media_importer/scraper/confidence_engine.py`
- `media_importer/scraper/dimension_manager.py`
- `media_importer/scraper/tmdb_client.py`
- `media_importer/scraper/providers/`

## Current Flow

```text
filename -> filename cleaner -> provider search/details -> LLM normalization -> confidence engine -> dimensions
```

`MetadataScraper` 是 import-flow 使用的刮削门面。它协调文件名清洗、Provider 查询、LLM 结构化和置信度计算。

`LLMScraper` 负责 LLM 调用和提示词装配。提示词文件由配置目录加载，Provider-specific prompts 由相关 API handler 维护。

`ConfidenceEngine` 负责把刮削结果、搜索置信度和数据来源门控转换为置信度等级。import-flow 的最终审核动作由 `ReviewDecisionService` 决定。

`dimension_manager.py` 负责维度配置读取和文件维度映射；刮削 step 会把文件推导维度合并进刮削维度。

上层 API 和 import-flow 代码应通过 `media_importer.features.scraping` 访问 TMDB client、维度管理、置信度和 scraper 门面。`media_importer/scraper/` 当前只作为实现位置。

## Extension Points

- 新 Provider：实现 `MetadataProvider`，注册到 provider registry。
- 新维度映射：更新 dimension manager、DB 维度配置、文档和测试。
- 新置信度规则：更新 `confidence_engine.py`、`features/import_flow/services/review.py` 和置信度测试。
- 新提示词配置：更新 prompts API、配置文档和 UI 测试。

## Tests

- `tests/test_confidence_engine.py`
- `tests/test_feature_entrypoints.py`
- `tests/test_confidence_config_ui.py`
- `tests/test_confidence_engine.py`
- `tests/test_import_flow_services.py` for review decision boundaries
