# Import Flow Feature

入库流程负责把扫描到的视频任务从源文件推进到刮削、分类、去重、移动入库、人工确认和状态落库。

## Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/import_flow/runner.py` | Pipeline runner and high-level task orchestration. |
| `media_importer/features/import_flow/context.py` | Task-scoped mutable context and update field extraction. |
| `media_importer/features/import_flow/steps/` | File and scrape step mixins. |
| `media_importer/features/import_flow/services/` | Classification, dedup, import, source cleanup, and review decisions. |
| `media_importer/features/import_flow/confirm.py` | Manual confirmation and reclassification behavior. |

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
- Behavior changes must update `docs/architecture/import-pipeline.md` and this file together.
