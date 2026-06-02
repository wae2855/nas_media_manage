# Providers Feature

Provider 能力负责接入 TMDB 或后续外部元数据源，并为刮削流程提供统一的查询和匹配结果。

## Current Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/providers/__init__.py` | Feature public API for provider registry and factory functions. |
| `media_importer/features/providers/base.py` | Provider interface and shared result/detail dataclasses. |
| `media_importer/features/providers/tmdb_provider.py` | TMDB provider implementation. |
| `media_importer/scraper/providers/` | Thin legacy import wrappers for provider modules. |
| `media_importer/features/scraping/metadata_scraper.py` | Calls providers during scrape orchestration. |
| `media_importer/core/config_view.py` | Reads provider-related configuration values. |

## Related Areas

- Config: provider enablement, API keys, language, region, timeout.
- API: provider configuration and scrape endpoints.
- Tests: provider behavior should be mocked, deterministic, and network-free by default.

## Target Shape

- Keep provider-specific client code isolated from import flow.
- New API/scraping code should import registry functions and provider types from `media_importer.features.providers`.
- Add a new provider by updating provider docs, config loader/migration/validator, API/frontend settings, and tests.
- If provider selection affects architecture, add an ADR.

## Tests

- Provider unit tests with mocked HTTP responses.
- Scraping integration tests with provider calls stubbed.
