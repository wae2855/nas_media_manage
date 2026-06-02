# Scraping Feature

刮削负责根据文件名、路径、AI 识别、TMDB/Provider 结果和置信度规则生成可入库的媒体元数据。

## Current Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/scraping/__init__.py` | Feature public API for metadata scraper, LLM scraper, confidence engine, and matcher/model helpers. |
| `media_importer/scraper/metadata_scraper.py` | High-level metadata scraping orchestration. |
| `media_importer/scraper/llm_scraper.py` | LLM prompt and parsing behavior. |
| `media_importer/scraper/confidence_engine.py` | Confidence scoring and review threshold decisions. |
| `media_importer/scraper/dimension_mapper.py` | Dimension mapping and category normalization. |
| `media_importer/scraper/providers/` | External metadata provider implementations. |

## Target Shape

- Move orchestration into `media_importer/features/scraping/`.
- Keep provider clients under `features/providers/` or infrastructure adapters depending on ownership.
- Keep confidence/review decisions aligned with `features/import_flow/services/review.py`.

## Related Areas

- Config: AI provider keys, TMDB keys, confidence thresholds, dimension rules.
- API: scrape config and manual task actions.
- Database: scrape result JSON and trace/debug fields.
- Frontend: scrape settings, task result display, review/confirm flows.

## Tests

- `tests/test_confidence_engine.py`
- Scrape-related API and import-flow tests.
- Provider tests when external calls are mocked.

## Migration Notes

- New app/API/import-flow code should import from `media_importer.features.scraping`.
- Until implementation files move, `media_importer/scraper/` remains implementation detail but is not the preferred feature entry.
- New scraping behavior must update `docs/architecture/scraping.md` and this feature doc.
