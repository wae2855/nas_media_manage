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
- `media_importer/scraper/providers/`

## Extension Points

- 新 Provider：实现 `MetadataProvider`，注册到 provider registry。
- 新维度映射：更新 dimension manager、DB 维度配置、文档和测试。
