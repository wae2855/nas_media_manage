# Task Lifecycle

## Status + Stage Dual Model

任务状态采用双层模型：**status（终态）** + **stage（处理环节）**。

### Status（任务终态）

| status | 含义 |
|--------|------|
| `PENDING` | 处理中（尚未到达终态），由 stage 细化 |
| `SUCCESS` | 入库成功 |
| `FAILED` | 处理失败 |
| `SKIPPED` | 跳过/忽略 |
| `CANCELLED` | 用户取消 |

### Stage（处理环节，仅 status=PENDING 时有意义）

| stage | 含义 | 对应旧状态 |
|-------|------|-----------|
| `QUEUED` | 排队等待 | 原 `PENDING`（初始态） |
| `RUNNING` | 流水线处理中 | 原 `PROCESSING` |
| `AWAIT_REVIEW` | 等待人工操作 | 合并原 `CONFIRMING` + `NEEDS_REVIEW` |
| `DONE` | 已到达终态 | status 非 PENDING 时 stage=DONE |

**终态规则**：SUCCESS/FAILED/SKIPPED/CANCELLED 的 stage 固定为 `DONE`，前端过滤时只需检查 status。

## Current File Locations

`file_location` 用于追踪文件当前位置，典型值：

- `source`
- `temp`
- `import`
- `recycle`

## Direction

`media_importer/features/tasks/` 是任务状态、`TaskManager` 和生命周期 helper 的业务入口。`media_importer/core/task_lifecycle.py` 是当前集中状态转换和文件位置规则的实现文件。

当前已集中：

- processing 开始（status=PENDING, stage=RUNNING）；
- temp ready；
- confirming（status=PENDING, stage=AWAIT_REVIEW）；
- needs review（status=PENDING, stage=AWAIT_REVIEW，与 confirming 相同 stage）；
- failed（status=FAILED, stage=DONE）；
- skipped（status=SKIPPED, stage=DONE）；
- imported（status=SUCCESS, stage=DONE）；
- retry reset（status=PENDING, stage=QUEUED）。

当前 import-flow step 继续接收原始 task dict；跨步骤更新通过 `TaskContext` 和 `TaskLifecycle` 集中表达。

## Transition Table

| 函数 | 目标 status | 目标 stage | 文件位置 | 典型调用方 |
|------|------------|-----------|----------|------------|
| `start_processing()` | `PENDING` | `RUNNING` | 保持原值 | runner 开始处理任务 |
| `mark_processing_step()` | `PENDING` | `RUNNING` | 保持原值 | step 进度更新 |
| `mark_temp_ready()` | 保持原值 | 保持原值 | `temp` | copy 完成后 |
| `mark_confirming()` | `PENDING` | `AWAIT_REVIEW` | `temp` | 低置信度进入人工确认 |
| `mark_confirmed()` | 保持原值 | 保持原值 | 保持原值 | 用户确认任务 |
| `mark_needs_review()` | `PENDING` | `AWAIT_REVIEW` | `temp` | 数据来源门控拦截 |
| `mark_failed()` | `FAILED` | `DONE` | 默认 `source` | import-flow/API 失败分支 |
| `mark_skipped()` | `SKIPPED` | `DONE` | 默认 `source` | 去重跳过或用户忽略 |
| `mark_imported()` | `SUCCESS` | `DONE` | `import` | 入库成功 |
| `reset_for_retry()` | `PENDING` | `QUEUED` | `source` | 重试失败任务 |

## Update Rule

新增状态或文件位置时必须同步：

- `media_importer/core/db/constants.py`
- `media_importer/core/task_lifecycle.py`
- `media_importer/features/tasks/`
- `media_importer/core/task_manager.py`
- `media_importer/features/import_flow/`
- `media_importer/api/task_handlers.py`
- `media_importer/webui/js/cinema-tasks.js`
- `docs/testing/regression-matrix.md`
- `tests/test_task_context_lifecycle.py`
- `tests/test_stage_lifecycle.py`（新增 stage 专项测试）