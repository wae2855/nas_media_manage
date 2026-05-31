# Module: Pipeline

## Code

- `media_importer/pipeline/runner.py`
- `media_importer/pipeline/steps.py`
- `media_importer/pipeline/steps_file.py`
- `media_importer/pipeline/steps_scrape.py`
- `media_importer/pipeline/confirm.py`
- `media_importer/pipeline/utils.py`

## Responsibility

任务处理编排，包括复制、刮削、验证、分类、去重、入库、确认、重分类和通知。

## Direction

后续将引入 `TaskContext`、`TaskLifecycle` 和 pipeline services，减少 step 内混合业务策略和基础设施调用。

## Tests

- `tests/test_full_flow.py`
- `tests/test_e2e_file_processing.py`
- `tests/test_task_operations.py`
