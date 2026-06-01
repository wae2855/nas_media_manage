# Module: Import Flow Domain

## Code

- `media_importer/domains/import_flow/__init__.py`
- `media_importer/domains/import_flow/context.py`
- `media_importer/domains/import_flow/lifecycle.py`
- `media_importer/domains/import_flow/review.py`

## Responsibility

入库流程的业务域兼容入口。当前只做 proof slice，用于让 AI 和人按业务域定位入库流程核心概念。

当前 re-export：

- `TaskContext` from `media_importer.pipeline.context`
- `TaskLifecycle` constants/functions from `media_importer.core.task_lifecycle`
- `ReviewDecision` and `ReviewDecisionService` from `media_importer.pipeline.services.review`

## Boundary

这里不是新的实现所在地。Phase 6A 只验证新 domain 入口和旧 public imports 可以同时存在。

实现仍在：

- `media_importer/pipeline/context.py`
- `media_importer/core/task_lifecycle.py`
- `media_importer/pipeline/services/review.py`

## Extension Rules

- 新 domain 入口必须保持薄层，不复制实现。
- 旧路径必须继续可 import。
- 旧 patch 路径必须继续影响新 domain 入口。
- 每个 domain proof slice 都要有 compatibility test。

## Tests

- `tests/test_domain_import_flow_compatibility.py`
- `tests/test_task_context_lifecycle.py`
- `tests/test_pipeline_services.py`
