# Import Flow Feature

入库流程负责把扫描到的视频任务从源文件推进到刮削、分类、去重、移动入库、人工确认和状态落库。

## Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/import_flow/runner.py` | Pipeline runner and high-level task orchestration. |
| `media_importer/features/import_flow/run_file_service.py` | API-facing manual run actions: batch `run_all` and single-file path/ext validation, task creation, and background `process_one` start. |
| `media_importer/features/import_flow/context.py` | Task-scoped mutable context and update field extraction. |
| `media_importer/features/import_flow/steps/` | File and scrape step mixins. |
| `media_importer/features/import_flow/scan_service.py` | Source scan and task-aware scan filtering entrypoint for runner, CLI, and watcher. |
| `media_importer/features/import_flow/services/` | Classification, dedup, import, file operation, and review decisions. |
| `media_importer/features/import_flow/services/classification_rules.py` | Path rule matching and filename/path template rendering. |
| `media_importer/features/import_flow/services/dedup_rules.py` | Duplicate detection, quality comparison, and rename suggestion rules. |
| `media_importer/features/import_flow/services/naming.py` | Filename and subtitle naming rules. |
| `media_importer/features/source_files/` | Source file cleanup and companion-file strategy used by import-flow. |
| `media_importer/features/import_flow/confirm.py` | Manual confirmation, preview, and reclassification behavior. `preview_task` updates metadata/dimensions/filename and re-runs classification without importing. `confirm_task` accepts `confirmed_title`/`override_source` and records `confirmed_override`/`confirmed_title`/`override_source` in DB. `reclassify_task` is now preview-only (compatibility). |
| `media_importer/infrastructure/filesystem/file_copier.py` | Temp copy infrastructure used by the copy step. |

## Related Areas

- API: task and import actions in `media_importer/api/`.
- Manual batch and single-file processing use `media_importer.features.import_flow.run_file_service`.
- Database: task rows, status constants, scrape result fields.
- Config: path rules, duplicate handling, match level review, source cleanup policy.
- Frontend: task list, task detail, confirm/preview/reclassify/scrape-search actions.

## Tests

- `tests/test_feature_import_flow.py`
- `tests/test_feature_import_flow_run_file.py`
- `tests/test_import_flow_services.py`
- `tests/test_feature_entrypoints.py`

## Change Notes

- New code should import from `media_importer.features.import_flow`.
- Classification rules and template rendering belong to `features/import_flow/services/classification_rules.py`; `storage/classifier.py` is only a compatibility alias.
- Dedup rules belong to `features/import_flow/services/dedup_rules.py`; `storage/dedup_checker.py` is only a compatibility alias.
- Scan orchestration belongs to `features/import_flow/scan_service.py`; `storage/file_scanner.py` is only a compatibility alias.
- Manual run orchestration belongs to `features/import_flow/run_file_service.py`; API handlers should not call `run_all`, perform path/ext validation, or create tasks directly for manual run requests.
- Filename and subtitle naming rules belong to `features/import_flow/services/naming.py`.
- 目标片库冲突检测只扫描本任务实际 `import_path`，结构化快照保存在 `dedup_result`，检测时不得回收或移动现有文件。旧 `skip/rename/replace/quality` 运行配置统一按 `confirm` 处理。
- 未决冲突只能逐项选择 `keep_existing | keep_both | replace_existing`；替换使用 SHA-256 确认快照、长复制后再次复核、旧文件本地回收和 no-replace 发布，普通/批量确认不得绕过。
- 待入库处理副本不得来自任何目标片库根；回收服务只有内部 `confirmed_target_replace` 协议能接收片库现有文件，其他原因码一律拒绝。
- Import move mechanics belong to `features/import_flow/services/file_operations.py`; source file cleanup strategy belongs to `features/source_files/`; `storage/file_mover.py` only keeps compatibility exports.
- File copy, path safety, permission checks, safe move/delete, and fingerprint infrastructure should be imported from `media_importer.infrastructure.filesystem`.
- Behavior changes must update `docs/architecture/import-pipeline.md` and this file together.
