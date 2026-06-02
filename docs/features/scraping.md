# Scraping Feature

刮削负责根据文件名、路径、AI 识别、TMDB/Provider 结果和置信度规则生成可入库的媒体元数据。

## Current Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/scraping/__init__.py` | Feature public API for metadata scraper, LLM scraper, confidence engine, and matcher/model helpers. |
| `media_importer/features/scraping/metadata_scraper.py` | High-level metadata scraping orchestration. |
| `media_importer/features/scraping/confidence_engine.py` | Confidence scoring and review threshold decisions. |
| `media_importer/features/scraping/confidence_models.py` | Confidence config, result dataclasses, and shared parsing patterns. |
| `media_importer/features/scraping/dimension_manager.py` | Dimension mapping, tier checks, and category normalization. |
| `media_importer/scraper/metadata_scraper.py` | Thin legacy import wrapper for `MetadataScraper`. |
| `media_importer/scraper/confidence_models.py` | Thin legacy import wrapper for confidence models. |
| `media_importer/scraper/confidence_engine.py` | Thin legacy import wrapper for `ConfidenceEngine`. |
| `media_importer/scraper/dimension_manager.py` | Thin legacy import wrapper for dimension helpers. |
| `media_importer/scraper/llm_scraper.py` | LLM prompt and parsing behavior. |
| `media_importer/scraper/tmdb_client.py` | TMDB client and error type, exposed through the scraping feature. |
| `media_importer/scraper/providers/` | External metadata provider implementations. |

## Current Consumers

- TMDB API handlers import `TMDbClient` and `TMDbError` from `media_importer.features.scraping`.
- Dimension API handlers import tier checks from `media_importer.features.scraping`.
- Import-flow scrape steps import file-dimension lookup from `media_importer.features.scraping`.
- `MetadataScraper`, `ConfidenceEngine`, confidence models, and dimension mapping have moved under `media_importer/features/scraping/`; remaining `media_importer/scraper/` files are implementation details until migrated.

## Target Shape

- Continue moving LLM and provider-adjacent scraping implementation into `media_importer/features/scraping/`.
- Keep provider clients under `features/providers/` or infrastructure adapters depending on ownership.
- Keep confidence/review decisions aligned with `features/import_flow/services/review.py`.

## Related Areas

- Config: AI provider keys, TMDB keys, confidence thresholds, dimension rules.
- API: scrape config and manual task actions.
- Database: scrape result JSON and trace/debug fields.
- Frontend: scrape settings, task result display, review/confirm flows.

## Tests

- `tests/test_confidence_engine.py`
- `tests/test_feature_entrypoints.py`
- Scrape-related API and import-flow tests.
- Provider tests when external calls are mocked.

## Migration Notes

- New app/API/import-flow code should import from `media_importer.features.scraping`.
- Until implementation files move, `media_importer/scraper/` remains implementation detail but is not the preferred feature entry.
- New scraping behavior must update `docs/architecture/scraping.md` and this feature doc.
