# Import Pipeline

## Current Entry Points

- `media_importer/features/import_flow/runner.py`
- `media_importer/features/import_flow/`
- `media_importer/features/import_flow/steps/`
- `media_importer/features/import_flow/steps/file.py`
- `media_importer/features/import_flow/steps/scrape.py`
- `media_importer/features/import_flow/confirm.py`
- `media_importer/features/import_flow/services/`

## Current Flow

```text
scan -> copy -> scrape -> validate -> classify -> dedup -> rename -> import -> notify -> record
```

## Direction

Import flow 已引入：

- `Import Flow Feature`: `media_importer/features/import_flow/`
- `TaskContext`: `media_importer/features/import_flow/context.py`
- `TaskLifecycle`: `media_importer/core/task_lifecycle.py`
- `ClassificationService`: `media_importer/features/import_flow/services/classification.py`
- `DedupService`: `media_importer/features/import_flow/services/dedup.py`
- `ImportService`: `media_importer/features/import_flow/services/import_service.py`
- `SourceCleanupService`: `media_importer/features/source_files/cleanup_service.py`
- `ReviewDecisionService`: `media_importer/features/import_flow/services/review.py`

当前 `TaskContext` 和 `TaskLifecycle` 已接入 runner、confirm 和 retry 逻辑。分类、去重、导入和审核决策已从 step 内抽成 import-flow service；源文件清理策略已独立到 `features/source_files`；step 主要保留进度、日志和 DB 状态写入。

`media_importer/features/import_flow/` 是入库流程业务域入口。旧 `media_importer/pipeline/` 包装层已归档，不再作为当前可导入入口。新代码、测试和文档必须直接使用 `media_importer.features.import_flow`。

## Change Guide

- 改分类路径规则：先看 `features/import_flow/services/classification.py`。
- 改同名策略：先看 `features/import_flow/services/dedup.py`，涉及回收站时再看 `SourceCleanupService`。
- 改入库移动、字幕落库、确认入库：先看 `features/import_flow/services/import_service.py`。
- 改成功入库、跳过或临时文件后的源文件处理：先看 `features/source_files/cleanup_service.py`。
- 改匹配级别、人工确认、匹配疑虑：先看 `features/import_flow/services/review.py`。
- 改流程 step 顺序、进度、日志或 DB 状态写入：先看 `features/import_flow/steps/`。
- 改状态字段：先看 `TaskLifecycle`。
