# Import Flow Feature

入库流程负责把扫描到的视频任务从源文件推进到刮削、分类、去重、移动入库、人工确认和状态落库。

## Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/import_flow/runner.py` | Pipeline runner and high-level task orchestration. |
| `media_importer/features/import_flow/run_file_service.py` | API-facing manual run actions: batch `run_all` and single-file path/ext validation, task creation, and background `process_one` start. |
| `media_importer/features/import_flow/context.py` | Task-scoped mutable context and update field extraction. |
| `media_importer/features/import_flow/progress.py` | Throttled persistence for truthful phase and byte progress. |
| `media_importer/features/import_flow/bundle_recovery.py` | Fingerprint- and task-bound restart recovery for interrupted video/subtitle bundle publication. |
| `media_importer/features/import_flow/steps/` | File and scrape step mixins. |
| `media_importer/features/import_flow/scan_service.py` | Source scan and task-aware scan filtering entrypoint for runner, CLI, and watcher. |
| `media_importer/features/import_flow/services/` | Classification, dedup, import, file operation, and review decisions. |
| `media_importer/features/import_flow/services/reorganization.py` | 把已完成兜底作品作为独立任务整组移动到正式规则目录，并更新父子任务关联结果。 |
| `media_importer/features/import_flow/services/classification_rules.py` | Path rule matching and filename/path template rendering. |
| `media_importer/features/import_flow/services/dedup_rules.py` | Duplicate detection, quality comparison, and rename suggestion rules. |
| `media_importer/features/import_flow/services/naming.py` | Filename and subtitle naming rules. |
| `media_importer/features/source_files/` | Source file cleanup and companion-file strategy used by import-flow. |
| `media_importer/features/import_flow/confirm.py` | Manual confirmation, preview, and reclassification behavior. `preview_task` updates metadata/dimensions/filename and re-runs classification without importing. `confirm_task` accepts `confirmed_title`/`override_source` and records `confirmed_override`/`confirmed_title`/`override_source` in DB. `reclassify_task` is now preview-only (compatibility). |

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
- `replace_existing` 当前只对不带字幕的单视频冲突开放。待入库作品包含字幕时，整包替换尚未具备同一提交事务，必须隐藏/拒绝替换，只允许保留现有或另存一份。
- 待入库处理副本不得来自任何目标片库根；回收服务只有内部 `confirmed_target_replace` 协议能接收片库现有文件，其他原因码一律拒绝。
- Import move mechanics belong to `features/import_flow/services/file_operations.py`; source file cleanup strategy belongs to `features/source_files/`; `storage/file_mover.py` only keeps compatibility exports.
- Path safety, permission checks, safe move/delete, and fingerprint infrastructure should be imported from `media_importer.infrastructure.filesystem`; target-side verified copy and bundle publication belong to `services/file_operations.py`.
- Import/source-cleanup progress must use the structured filesystem phase callback and `TaskProgressReporter`; do not write SQLite once per 1 MB chunk or label SHA-256 verification as copying.
- Terminal success is persisted after source-unit coordination. `import_success=1` is useful audit evidence, but restart recovery may only declare success when every persisted bundle member at the final path matches its SHA-256.
- 新作品先完成刮削、校验、规则分类、命名、目标片库重名检查和全部人工决定；此前不得传输大视频。决定完成后从来源直接写入目标侧本任务暂存，字幕先发布、视频最后发布。中心中转和旧任务断点均不支持。
- 正常入库不保留来源文件名：刮削后按 `filename_templates` 生成 `final_filename`，电视剧模板保留任务自身的季集号；只有用户在待确认阶段显式保存自定义文件名时才以该人工结果继续。
- 直接来源复制在同一次校验复制中取得 SHA-256，避免复制前再完整读取一次多 GB 来源。文件包清单记录普通入库 `copy` 或片库重新整理 `move`；启动恢复对普通入库只清理本任务目标临时成员并保留来源，对重新整理才退回原片库位置。
- 来源在复制或来源哈希期间发生变化时立即停止并提示等待稳定；只有来源快照稳定而目标摘要不一致时，普通入库才清理本任务 `.copying` 并从空临时文件安全重试一次。第二次仍不一致时明确提示检查目标存储/挂载并失败关闭，SHA-256 与来源保留门禁不变。
- 重试清空所有运行结果并从来源重新刮削、决策和传输；不续跑步骤、不复用 `.copying`。完整提交恢复会保留来源，避免重启阶段无感补做来源删除。
- 兜底目录不是自动成功路径：即使刮削已自动通过，只要分类结果使用兜底，任务必须先停在 `AWAIT_REVIEW`，用户明确接受后才可入库。后续重新整理不重跑来源复制/清理，而以片库内现存影片和随片字幕为来源，复用同一文件包事务移动到正式规则目录；同名目标一律暂停且不覆盖。
- Behavior changes must update `docs/architecture/import-pipeline.md` and this file together.
