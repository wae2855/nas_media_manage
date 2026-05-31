# Module: Scraper Providers

## Code

- `media_importer/scraper/providers/base.py`
- `media_importer/scraper/providers/__init__.py`
- `media_importer/scraper/providers/tmdb_provider.py`

## Responsibility

定义元数据源抽象，注册和创建 Provider。

## Extension Rule

新增 Provider 应实现 `MetadataProvider`，注册到 provider registry，并补充配置、API、测试和文档。
