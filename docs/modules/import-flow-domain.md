# Module: Import Flow Domain

## Code

- `media_importer/domains/import_flow/__init__.py`
- `media_importer/domains/import_flow/context.py`
- `media_importer/domains/import_flow/runner.py`
- `media_importer/domains/import_flow/steps/`
- `media_importer/domains/import_flow/steps/file.py`
- `media_importer/domains/import_flow/steps/scrape.py`
- `media_importer/domains/import_flow/confirm.py`
- `media_importer/domains/import_flow/lifecycle.py`
- `media_importer/domains/import_flow/review.py`
- `media_importer/domains/import_flow/services/`
- `media_importer/pipeline/confirm.py` compatibility alias
- `media_importer/pipeline/runner.py` compatibility alias
- `media_importer/pipeline/steps.py` compatibility alias
- `media_importer/pipeline/steps_file.py` compatibility alias
- `media_importer/pipeline/steps_scrape.py` compatibility alias
- `media_importer/pipeline/services/` compatibility aliases

## Responsibility

入库流程的业务域入口，用于让 AI 和人按业务域定位入库流程核心概念和业务服务。

当前持有：

- `TaskContext` from `media_importer.domains.import_flow.context`
- `PipelineRunner` from `media_importer.domains.import_flow.runner`
- `StepsMixin`, `FileStepsMixin`, `ScrapeStepsMixin` from `media_importer.domains.import_flow.steps`
- `ConfirmMixin` from `media_importer.domains.import_flow.confirm`
- `TaskLifecycle` constants/functions from `media_importer.core.task_lifecycle`
- `ClassificationService`, `DedupService`, `ImportService`, `SourceCleanupService`, `ReviewDecisionService` from `media_importer.domains.import_flow.services`

## Boundary

Phase 6D services 阶段后，这里已经持有 pipeline services 实现。

实现仍在旧目录之外的部分：

- `media_importer/core/task_lifecycle.py`

兼容路径：

- `media_importer/pipeline/context.py`
- `media_importer/pipeline/runner.py`
- `media_importer/pipeline/steps.py`
- `media_importer/pipeline/steps_file.py`
- `media_importer/pipeline/steps_scrape.py`
- `media_importer/pipeline/confirm.py`
- `media_importer/pipeline/services/`

## Extension Rules

- 新 domain 入口必须保持薄层，不复制实现。
- 旧路径必须继续可 import。
- 旧 patch 路径必须继续影响新 domain 入口。
- 每个 domain proof slice 都要有 compatibility test。
- `media_importer.pipeline.PipelineRunner` 必须继续可用，CLI/API 启动路径依赖它。
- `media_importer.pipeline` 公共入口和旧 `pipeline/steps*` 路径必须继续可用，直到单独决策删除兼容层。

## Tests

- `tests/test_domain_import_flow_compatibility.py`
- `tests/test_task_context_lifecycle.py`
- `tests/test_pipeline_services.py`
