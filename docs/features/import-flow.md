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
| `media_importer/pipeline/` | Temporary wrapper for old imports; not the preferred source of truth. |

## Related Areas

- API: task and import actions in `media_importer/api/`.
- Database: task rows, status constants, scrape result fields.
- Config: path rules, duplicate handling, review thresholds, source cleanup policy.
- Frontend: task list, task detail, confirm/reclassify actions.

## Tests

- `tests/test_feature_import_flow.py`
- `tests/test_pipeline_services.py`
- `tests/test_feature_entrypoints.py`

## Migration Notes

- New code should import from `media_importer.features.import_flow`.
- Old `media_importer.pipeline` wrappers can be archived after route/API/tests no longer need patch compatibility.
- Behavior changes must update `docs/architecture/import-pipeline.md` and this file together.
