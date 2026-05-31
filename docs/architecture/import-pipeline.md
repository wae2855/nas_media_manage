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

后续 pipeline 会逐步引入：

- `TaskContext`
- `TaskLifecycle`
- `ClassificationService`
- `DedupService`
- `ImportService`
- `SourceCleanupService`
- `ReviewDecisionService`

本文件在服务化重构完成后再补全详细事实。
