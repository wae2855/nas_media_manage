# Module: Pipeline

## Code

- `media_importer/pipeline/context.py`
- `media_importer/pipeline/runner.py`
- `media_importer/pipeline/steps.py`
- `media_importer/pipeline/steps_file.py`
- `media_importer/pipeline/steps_scrape.py`
- `media_importer/pipeline/confirm.py`
- `media_importer/pipeline/services/classification.py`
- `media_importer/pipeline/services/dedup.py`
- `media_importer/pipeline/services/import_service.py`
- `media_importer/pipeline/services/source_cleanup.py`
- `media_importer/pipeline/services/review.py`
- `media_importer/pipeline/utils.py`

## Responsibility

任务处理编排，包括复制、刮削、验证、分类、去重、入库、确认、重分类和通知。

业务策略优先放在 `pipeline/services/`：

- `ClassificationService`: 刮削结果到入库目录。
- `DedupService`: 同名检测和 skip/rename/replace/quality 决策。
- `ImportService`: 普通入库和确认入库复用的文件移动与字幕落库。
- `SourceCleanupService`: 源文件、临时文件、回收站和空目录清理。
- `ReviewDecisionService`: 刮削置信度和数据门控到人工确认/审核/失败的决策。

## Direction

已引入 `TaskContext`、`TaskLifecycle` 和 pipeline services。后续重点是让 services 改用 `ConfigView`，减少裸 `config` 访问。

## Tests

- `tests/test_full_flow.py`
- `tests/test_pipeline_services.py`
- `tests/test_e2e_file_processing.py`
- `tests/test_task_operations.py`
