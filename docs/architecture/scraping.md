# Scraping Architecture

## Responsibilities

- 清洗文件名。
- 调用 Provider 搜索元数据。
- 调用 LLM 整理结果。
- 计算置信度。
- 映射分类维度。

## Entry Points

- `media_importer/features/scraping/metadata_scraper.py`
- `media_importer/features/scraping/confidence_engine.py`
- `media_importer/features/scraping/confidence_models.py`
- `media_importer/features/scraping/dimension_manager.py`
- `media_importer/features/providers/`
- `media_importer/features/prompts/prompt_builder.py`
- `media_importer/scraper/metadata_scraper.py` legacy import wrapper
- `media_importer/scraper/llm_scraper.py`
- `media_importer/scraper/llm_prompts.py` legacy import wrapper
- `media_importer/scraper/confidence_engine.py` legacy import wrapper
- `media_importer/scraper/confidence_models.py` legacy import wrapper
- `media_importer/scraper/dimension_manager.py` legacy import wrapper
- `media_importer/scraper/tmdb_client.py`
- `media_importer/scraper/providers/` legacy import wrappers

## Current Flow

```text
filename -> filename cleaner -> provider search/details -> LLM normalization -> confidence engine -> dimensions
```

`MetadataScraper` 是 import-flow 使用的刮削门面，真实实现位于 `media_importer/features/scraping/metadata_scraper.py`。它协调文件名清洗、Provider 查询、LLM 结构化和置信度计算。

`LLMScraper` 负责 LLM 调用和响应解析。提示词模板构建真实实现位于 `media_importer/features/prompts/prompt_builder.py`，提示词文件由配置目录加载，Provider-specific prompts 由相关 API handler 维护。

`ConfidenceEngine` 负责把刮削结果、搜索置信度和数据来源门控转换为置信度等级，真实实现位于 `media_importer/features/scraping/confidence_engine.py`，共享模型位于 `media_importer/features/scraping/confidence_models.py`。import-flow 的最终审核动作由 `ReviewDecisionService` 决定。

`DimensionManager` 相关函数负责维度配置读取和文件维度映射，真实实现位于 `media_importer/features/scraping/dimension_manager.py`；刮削 step 会把文件推导维度合并进刮削维度。

上层 API 和 import-flow 代码应通过 `media_importer.features.scraping` 访问 TMDB client、维度管理、置信度和 scraper 门面；Provider registry 和类型应通过 `media_importer.features.providers` 访问。`media_importer/scraper/` 当前只保留 legacy wrappers 和待迁移实现。

## Extension Points

- 新 Provider：在 `features/providers/` 实现 `MetadataProvider`，注册到 provider registry。
- 新维度映射：更新 `features/scraping/dimension_manager.py`、DB 维度配置、文档和测试。
- 新置信度规则：更新 `features/scraping/confidence_engine.py`、`features/import_flow/services/review.py` 和置信度测试。
- 新提示词配置：更新 `features/prompts/prompt_builder.py`、prompts API、配置文档和 UI 测试。

## Tests

- `tests/test_confidence_engine.py`
- `tests/test_feature_entrypoints.py`
- `tests/test_confidence_config_ui.py`
- `tests/test_confidence_engine.py`
- `tests/test_import_flow_services.py` for review decision boundaries
