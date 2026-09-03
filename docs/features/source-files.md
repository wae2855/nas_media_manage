# Source Files Feature

源文件策略负责入库任务完成或跳过时，如何处理原始视频、字幕和伴生文件。它是独立业务 feature，不再归入 import-flow 的内部 service。

## Ownership

- 判断源文件、字幕和伴生文件的处理范围。
- 根据配置生成允许操作目录和入库根目录。
- 按 `source_policy.disposal_mode` 把已确认垃圾或成功来源单元移入本地回收，或交给 ADR-0019 的任务删除隔离区永久清理；嵌套挂载点、符号链接、特殊文件、未知账本路径或片库重叠一律失败关闭。

## Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/source_files/cleanup_service.py` | `SourceCleanupService` and result model for post-import, skip, and existing-import source decisions. |
| `media_importer/features/source_files/operations.py` | Companion discovery, source file deletion within allowed dirs, non-media cleanup, and empty parent dir cleanup. |
| `media_importer/features/source_files/config_paths.py` | Source-file allowed directory and import root calculation from configuration. |
| `media_importer/features/source_files/__init__.py` | Public source-files feature API. |
| `media_importer/features/import_flow/services/source_cleanup.py` | Compatibility wrapper only. |

## Related Areas

- Import flow: runner, dedup, and import services use `SourceCleanupService`.
- Recycle: destructive source/library file handling goes through `features/recycle`.
- Filesystem infrastructure: direct path validation, permission checks, safe move/delete, and fingerprint helpers live in `infrastructure/filesystem`.
- Config: `paths.source_dir`, `paths.library_roots`, `paths.path_rules`, `source_policy.recycle_dir`, `source_policy.mode`, `source_policy.disposal_mode`.
- `source_units.py` 以源根第一层文件夹或“根直属文件集合”建立快照；聚合门禁只在所有媒体任务成功后回收，失败/跳过/变化均等待。
- watcher 启动及每轮来源扫描后先查 SQLite 待处理来源单元；只有存在待处理记录才访问对应来源并重试，不扫描目标片库。物理快照逐项未变化的旧记录可以补齐一次冻结媒体候选证据，任何差异都阻断并保留来源。
- 最后一条任务已经安全入库但尚未落终态时，可用 `completing_task_id` 参与聚合门禁；该任务必须仍为 `PENDING/RUNNING` 且 `import_success=1`，其他同组任务仍必须是 `SUCCESS/DONE`。整组处理完成或明确失败后，最后任务才进入终态。

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
- `permanent_delete` 只允许删除同一来源根内已落账本的任务专属 `.nas-media-delete-<unit-id>.deleting` 隔离区；不得对原始来源路径或目标片库调用通用删除。
- 本地来源使用 device/inode 身份；明确的远程挂载使用挂载身份与稳定文件树事实，兼容 rclone rename 后虚拟 inode 改变。远程删除仍只在已验证隔离区内执行，挂载变化、未知成员、链接或特殊文件均停下。
- 活动账本会在后台协调时续做；旧版账本仅在当前来源仍明确为远程挂载且路径、账本成员和隔离区全部吻合时兼容。任意非成功恢复结果原样写入任务，不再继续检查已被认领的原路径。
## 媒体候选过滤

扫描、来源单元和源清理共用 `features/source_files/media_candidates.py`。判定只有 `ACCEPT` / `IGNORE_PROMOTION` / `IGNORE_SMALL_COMPANION`，本身不移动或删除文件。默认小视频门槛是 50 MB、同单元主视频至少 500 MB、小视频不超过主视频 2%；体积条件必须同时满足才能忽略。无法读取、证据冲突或独立短片统一保守进入 `ACCEPT`。

高确信广告词来自 `data/media_candidate_patterns.v1.json`；用户可增加自定义名称模式，但不能清空系统预置。被忽略文件不创建任务，但依然进入来源单元物理快照和最终处置复核；`preserve_all` 下始终保留。

来源处置结果同时写入任务的 `source_cleanup_status` 与用户可读说明。影片已入库但来源仍等待、阻断或失败时，详情必须明确显示来源仍被保留；不得仅显示整体完成而隐藏来源状态。
