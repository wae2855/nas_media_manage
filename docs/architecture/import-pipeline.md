# Import Pipeline

## Current Entry Points

- `media_importer/pipeline/runner.py`
- `media_importer/pipeline/steps.py`
- `media_importer/pipeline/steps_file.py`
- `media_importer/pipeline/steps_scrape.py`
- `media_importer/pipeline/confirm.py`

## Current Flow

```text
scan -> copy -> scrape -> validate -> classify -> dedup -> rename -> import -> notify -> record
```

## Direction

pipeline 已开始逐步引入：

- `TaskContext`: `media_importer/pipeline/context.py`
- `TaskLifecycle`: `media_importer/core/task_lifecycle.py`
- `ClassificationService`
- `DedupService`
- `ImportService`
- `SourceCleanupService`
- `ReviewDecisionService`

当前 `TaskContext` 和 `TaskLifecycle` 已接入 runner、confirm 和 retry 逻辑。服务化重构完成后再补全详细事实。
