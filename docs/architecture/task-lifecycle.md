# Task Lifecycle

## Current Statuses

当前任务状态仍由 DB 常量、TaskManager、pipeline、API、前端共同使用。

常见状态：

- `PENDING`
- `PROCESSING`
- `CONFIRMING`
- `FAILED`
- `SKIPPED`
- `SUCCESS`
- `NEEDS_REVIEW`

## Current File Locations

`file_location` 用于追踪文件当前位置，典型值：

- `source`
- `temp`
- `import`
- `recycle`

## Direction

已新增 `media_importer/core/task_lifecycle.py`，用于集中状态转换和文件位置规则。

当前已集中：

- processing 开始；
- temp ready；
- confirming；
- needs review；
- failed；
- skipped；
- imported；
- retry reset。

当前仍保持兼容：pipeline step 继续接收原始 task dict，后续服务化重构再逐步扩大使用范围。

## Transition Table

| 函数 | 目标状态 | 文件位置 | 典型调用方 |
|------|----------|----------|------------|
| `start_processing()` | `PROCESSING` | 保持原值 | runner 开始处理任务 |
| `mark_processing_step()` | `PROCESSING` | 保持原值 | step 进度更新 |
| `mark_temp_ready()` | 保持原值 | `temp` | copy 完成后 |
| `mark_confirming()` | `CONFIRMING` | `temp` | 低置信度进入人工确认 |
| `mark_confirmed()` | 保持原值 | 保持原值 | 用户确认任务 |
| `mark_needs_review()` | `NEEDS_REVIEW` | `temp` | 数据来源门控拦截 |
| `mark_failed()` | `FAILED` | 默认 `source` | pipeline/API 失败分支 |
| `mark_skipped()` | `SKIPPED` | 默认 `source` | 去重跳过或用户忽略 |
| `mark_imported()` | `SUCCESS` | `import` | 入库成功 |
| `reset_for_retry()` | `PENDING` | `source` | 重试失败任务 |

## Update Rule

新增状态或文件位置时必须同步：

- `media_importer/core/db/constants.py`
- `media_importer/core/task_lifecycle.py`
- `media_importer/core/task_manager.py`
- `media_importer/features/import_flow/`
- `media_importer/api/task_handlers.py`
- `media_importer/webui/js/tasks.js`
- `docs/testing/regression-matrix.md`
- `tests/test_task_context_lifecycle.py`
