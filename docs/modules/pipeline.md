# Module: Pipeline

## Code

- `media_importer/domains/import_flow/context.py`
- `media_importer/pipeline/context.py` compatibility alias
- `media_importer/domains/import_flow/runner.py`
- `media_importer/pipeline/runner.py` compatibility alias
- `media_importer/domains/import_flow/steps/`
- `media_importer/domains/import_flow/steps/file.py`
- `media_importer/domains/import_flow/steps/scrape.py`
- `media_importer/pipeline/steps.py` compatibility alias
- `media_importer/pipeline/steps_file.py` compatibility alias
- `media_importer/pipeline/steps_scrape.py` compatibility alias
- `media_importer/domains/import_flow/confirm.py`
- `media_importer/pipeline/confirm.py` compatibility alias
- `media_importer/domains/import_flow/utils.py`
- `media_importer/pipeline/utils.py` compatibility alias
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

Phase 6A 已新增 `media_importer/domains/import_flow/` 作为业务域兼容入口；旧 pipeline public imports 保持兼容。

Phase 6D services 已将 `pipeline/services/` 实现迁移到 `media_importer/domains/import_flow/services/`；旧 `pipeline/services/*` 保留 import 和 patch 路径兼容。

Phase 6D context 已将 `TaskContext` 实现迁移到 `media_importer/domains/import_flow/context.py`；旧 `pipeline/context.py` 保留兼容别名。

Phase 6D confirm 已将确认/重分类实现迁移到 `media_importer/domains/import_flow/confirm.py`；旧 `pipeline/confirm.py` 保留兼容别名。

Phase 6D runner 已将 `PipelineRunner` 实现迁移到 `media_importer/domains/import_flow/runner.py`；旧 `pipeline/runner.py` 和 `media_importer.pipeline.PipelineRunner` 保留兼容入口。

Phase 6D steps 已将 `StepsMixin`、`FileStepsMixin` 和 `ScrapeStepsMixin` 实现迁移到 `media_importer/domains/import_flow/steps/`；旧 `pipeline/steps.py`、`pipeline/steps_file.py` 和 `pipeline/steps_scrape.py` 保留兼容别名。

Phase 6E entrypoints 已将 API 服务入口和 CLI 组件构建入口改为直接导入 `media_importer.domains.import_flow.PipelineRunner`；旧 `media_importer.pipeline.PipelineRunner` 仅作为兼容入口保留。

Phase 6E utils 已将 `PipelineError`、`PipelineSkipError`、`PIPELINE_STEPS` 和 `_extract_series_name` 迁移到 `media_importer/domains/import_flow/utils.py`；旧 `pipeline/utils.py` 保留兼容导出。

## Tests

- `tests/test_full_flow.py`
- `tests/test_pipeline_services.py`
- `tests/test_e2e_file_processing.py`
- `tests/test_task_operations.py`
- `tests/test_domain_entrypoints.py`
