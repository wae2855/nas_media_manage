# Source Cleaning Feature

源目录清理负责识别源目录中的广告、说明文件、空目录、异常小视频等可清理对象，并通过回收站执行安全清理。

## Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/source_cleaning/cleaner.py` | Preview and execute source cleanup decisions. |
| `media_importer/features/source_cleaning/application_service.py` | Feature application entry for preview, execute, status, records, and task-path aggregation. |
| `media_importer/features/source_cleaning/records.py` | Cleaner record repository facade. |
| `media_importer/storage/source_cleaner.py` | Compatibility wrapper for old imports. |
| `media_importer/api/source_cleaner_handlers.py` | HTTP actions for preview, execute, records, and status. |

## Related Areas

- Config: `source_cleaner`, `source_dir`, `video_extensions`, `subtitle_extensions`, `source_policy.recycle_dir`.
- Database: source cleaner execution records.
- Frontend: config/source cleanup controls.
- Safety: every delete-like action must go through recycle.

## Tests

- `tests/test_feature_source_cleaning.py`
- Config/API tests that cover source cleaner settings.
- Recycle tests for cleanup safety.

## Migration Notes

- New code should import from `media_importer.features.source_cleaning`.
- API/CLI style callers should prefer `application_service.py` instead of reassembling task paths or status payloads themselves.
- If cleanup categories change, update `docs/architecture/source-cleaner.md`, API docs, and UI wording together.
