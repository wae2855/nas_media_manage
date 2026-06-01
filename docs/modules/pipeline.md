# Module: Pipeline

## Code

- `media_importer/domains/import_flow/context.py`
- `media_importer/pipeline/context.py` compatibility alias
- `media_importer/pipeline/runner.py`
- `media_importer/pipeline/steps.py`
- `media_importer/pipeline/steps_file.py`
- `media_importer/pipeline/steps_scrape.py`
- `media_importer/pipeline/confirm.py`
- `media_importer/domains/import_flow/services/classification.py`
- `media_importer/domains/import_flow/services/dedup.py`
- `media_importer/domains/import_flow/services/import_service.py`
- `media_importer/domains/import_flow/services/source_cleanup.py`
- `media_importer/domains/import_flow/services/review.py`
- `media_importer/pipeline/services/` compatibility aliases
- `media_importer/pipeline/utils.py`

## Responsibility

任务处理编排，包括复制、刮削、验证、分类、去重、入库、确认、重分类和通知。

业务策略优先放在 `domains/import_flow/services/`：

- `ClassificationService`: 刮削结果到入库目录。
- `DedupService`: 同名检测和 skip/rename/replace/quality 决策。
- `ImportService`: 普通入库和确认入库复用的文件移动与字幕落库。
- `SourceCleanupService`: 源文件、临时文件、回收站和空目录清理。
- `ReviewDecisionService`: 刮削置信度和数据门控到人工确认/审核/失败的决策。

## Direction

已引入 `TaskContext`、`TaskLifecycle` 和 import-flow services。import-flow services 已改用 `ConfigView` 读取高频配置。

Phase 6A 已新增 `media_importer/domains/import_flow/` 作为业务域兼容入口；pipeline 仍是当前实现所在地。

Phase 6D services 已将 `pipeline/services/` 实现迁移到 `media_importer/domains/import_flow/services/`；旧 `pipeline/services/*` 保留 import 和 patch 路径兼容。

Phase 6D context 已将 `TaskContext` 实现迁移到 `media_importer/domains/import_flow/context.py`；旧 `pipeline/context.py` 保留兼容别名。

## Tests

- `tests/test_full_flow.py`
- `tests/test_pipeline_services.py`
- `tests/test_e2e_file_processing.py`
- `tests/test_task_operations.py`
