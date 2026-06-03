# Source Files Feature

源文件策略负责入库任务完成、跳过或临时文件清理时，如何处理原始视频、字幕和伴生文件。它是独立业务 feature，不再归入 import-flow 的内部 service。

## Ownership

- 判断源文件、字幕和伴生文件的处理范围。
- 根据配置生成允许操作目录和入库根目录。
- 调用回收站处理源文件保留、跳过、替换和成功入库后的清理。
- 对明确属于临时目录的中转文件执行安全删除。

## Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/source_files/cleanup_service.py` | `SourceCleanupService` and result model for post-import, skip, existing-import recycle, and temp cleanup decisions. |
| `media_importer/features/source_files/operations.py` | Companion discovery, source file deletion within allowed dirs, non-media cleanup, and empty parent dir cleanup. |
| `media_importer/features/source_files/config_paths.py` | Source-file allowed directory and import root calculation from configuration. |
| `media_importer/features/source_files/__init__.py` | Public source-files feature API. |
| `media_importer/features/import_flow/services/source_cleanup.py` | Compatibility wrapper only. |

## Related Areas

- Import flow: runner, dedup, and import services use `SourceCleanupService`.
- Recycle: destructive source/library file handling goes through `features/recycle`.
- Filesystem infrastructure: direct path validation, permission checks, safe move/delete, and fingerprint helpers live in `infrastructure/filesystem`.
- Config: `paths.source_dir`, `paths.temp_dir`, `paths.path_rules`, `source_policy.recycle_dir`, `source_policy.cleanup_source_after_done`.

## Tests

- `tests/test_import_flow_services.py`
- `tests/test_recycle_safety.py`
- `tests/test_feature_entrypoints.py`
- `tests/test_architecture_guards.py`

## Change Notes

- New code should import source cleanup behavior from `media_importer.features.source_files`.
- `features/source_files` must not depend on `features/import_flow`; import-flow may depend on source-files.
- Do not add source file strategy back to `storage/file_mover.py` or import-flow internal wrappers.
- Any destructive behavior change must update `docs/standards/safety.md`, `docs/architecture/storage-filesystem.md`, and recycle/source-files tests.
