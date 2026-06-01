# Import Pipeline

## Current Entry Points

- `media_importer/pipeline/runner.py`
- `media_importer/pipeline/steps.py`
- `media_importer/pipeline/steps_file.py`
- `media_importer/pipeline/steps_scrape.py`
- `media_importer/pipeline/confirm.py`
- `media_importer/domains/import_flow/`
- `media_importer/domains/import_flow/services/`
- `media_importer/pipeline/services/` compatibility aliases

## Current Flow

```text
scan -> copy -> scrape -> validate -> classify -> dedup -> rename -> import -> notify -> record
```

## Direction

pipeline 已引入：

- `Import Flow Domain`: `media_importer/domains/import_flow/`
- `TaskContext`: `media_importer/pipeline/context.py`
- `TaskLifecycle`: `media_importer/core/task_lifecycle.py`
- `ClassificationService`: `media_importer/domains/import_flow/services/classification.py`
- `DedupService`: `media_importer/domains/import_flow/services/dedup.py`
- `ImportService`: `media_importer/domains/import_flow/services/import_service.py`
- `SourceCleanupService`: `media_importer/domains/import_flow/services/source_cleanup.py`
- `ReviewDecisionService`: `media_importer/domains/import_flow/services/review.py`

当前 `TaskContext` 和 `TaskLifecycle` 已接入 runner、confirm 和 retry 逻辑。分类、去重、导入、源文件清理和审核决策已从 step 内抽成 service；step 主要保留进度、日志和 DB 状态写入。

`media_importer/domains/import_flow/` 是入库流程业务域入口。Phase 6D 已将 pipeline services 实现迁移到 `domains/import_flow/services/`；`pipeline/services/` 保留旧 import 和 patch 路径兼容。

## Change Guide

- 改分类路径规则：先看 `domains/import_flow/services/classification.py`。
- 改同名策略：先看 `domains/import_flow/services/dedup.py`，涉及回收站时再看 `SourceCleanupService`。
- 改入库移动、字幕落库、确认入库：先看 `domains/import_flow/services/import_service.py`。
- 改置信度、人工审核、数据门控：先看 `domains/import_flow/services/review.py`。
- 改状态字段：先看 `TaskLifecycle`。
