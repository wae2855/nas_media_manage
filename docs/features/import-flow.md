# Import Flow Feature

入库流程负责把扫描到的视频任务从源文件推进到刮削、分类、去重、移动入库、人工确认和状态落库。

## Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/import_flow/runner.py` | Pipeline runner and high-level task orchestration. |
| `media_importer/features/import_flow/context.py` | Task-scoped mutable context and update field extraction. |
| `media_importer/features/import_flow/steps/` | File and scrape step mixins. |
| `media_importer/features/import_flow/services/` | Classification, dedup, import, source cleanup, and review decisions. |
| `media_importer/features/import_flow/services/classification_rules.py` | Path rule matching and filename/path template rendering. |
| `media_importer/features/import_flow/services/dedup_rules.py` | Duplicate detection, quality comparison, and rename suggestion rules. |
| `media_importer/features/import_flow/confirm.py` | Manual confirmation and reclassification behavior. |
| `media_importer/infrastructure/filesystem/file_copier.py` | Temp copy infrastructure used by the copy step. |

## Related Areas

- API: task and import actions in `media_importer/api/`.
- Database: task rows, status constants, scrape result fields.
- Config: path rules, duplicate handling, review thresholds, source cleanup policy.
- Frontend: task list, task detail, confirm/reclassify actions.

## Tests

- `tests/test_feature_import_flow.py`
- `tests/test_import_flow_services.py`
- `tests/test_feature_entrypoints.py`

## Change Notes

- New code should import from `media_importer.features.import_flow`.
- Classification rules and template rendering belong to `features/import_flow/services/classification_rules.py`; `storage/classifier.py` is only a compatibility alias.
- Dedup rules belong to `features/import_flow/services/dedup_rules.py`; `storage/dedup_checker.py` is only a compatibility alias.
- File copy infrastructure should be imported from `media_importer.infrastructure.filesystem`.
- Behavior changes must update `docs/architecture/import-pipeline.md` and this file together.
