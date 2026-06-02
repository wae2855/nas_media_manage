# Module: Scraper

## Code

- `media_importer/scraper/metadata_scraper.py`
- `media_importer/scraper/llm_scraper.py`
- `media_importer/scraper/llm_prompts.py`
- `media_importer/scraper/confidence_engine.py`
- `media_importer/scraper/confidence_models.py`
- `media_importer/scraper/filename_cleaner.py`
- `media_importer/scraper/title_matcher.py`
- `media_importer/scraper/dimension_manager.py`

## Responsibility

文件名清洗、Provider 查询、LLM 整理、置信度计算、维度映射。

## Boundary

scraper 负责“识别是什么”，不负责“放到哪里”。

- 入库路径分类在 `features/import_flow/services/classification.py`。
- 人工确认/审核动作在 `features/import_flow/services/review.py`。
- Provider 注册在 `scraper/providers/`。
- 维度配置和文件维度推导在 `scraper/dimension_manager.py`。

## Extension Points

- 新 Provider：先看 [scraper-providers.md](scraper-providers.md)。
- 新置信度规则：更新 `confidence_engine.py` 和 import-flow review service。
- 新维度：同步 DB 维度配置、`dimension_manager.py`、前端维度页和测试。
- 新提示词字段：同步 prompts API、配置示例和 UI。

## Tests

- `tests/test_confidence_engine.py`
- `tests/test_confidence_config_ui.py`
- `tests/test_confidence_engine.py`
- `tests/test_pipeline_services.py`
