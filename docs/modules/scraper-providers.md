# Module: Scraper Providers

## Code

- `media_importer/scraper/providers/base.py`
- `media_importer/scraper/providers/__init__.py`
- `media_importer/scraper/providers/tmdb_provider.py`

## Responsibility

定义元数据源抽象，注册和创建 Provider。

Provider 只负责外部元数据源的搜索、详情获取和结果归一化，不直接写任务状态、文件路径或入库目录。

## Extension Rule

新增 Provider 应实现 `MetadataProvider`，注册到 provider registry，并补充配置、API、测试和文档。

## Sync Checklist

- `media_importer/scraper/providers/`
- `media_importer/scraper/metadata_scraper.py`
- `media_importer/api/provider_handlers.py`
- `media_importer/webui/js/config.js` or provider UI area
- `config.yaml.example`
- `docs/architecture/scraping.md`
- `tests/test_api_routes.py` if API routes change
