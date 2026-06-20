# Task Lifecycle

## Status + Stage Dual Model

任务状态采用双层模型：**status（终态）** + **stage（处理环节）**。

### Status（任务终态）

| status | 含义 |
|--------|------|
| `PENDING` | 处理中（尚未到达终态），由 stage 细化 |
| `SUCCESS` | 入库成功 |
| `FAILED` | 处理失败，包含服务中断或重启导致的孤儿 RUNNING 任务 |
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
- cancelled（status=CANCELLED, stage=DONE）；
- retry reset（status=PENDING, stage=QUEUED）。

当前 import-flow step 继续接收原始 task dict；跨步骤更新通过 `TaskContext` 和 `TaskLifecycle` 集中表达。

## Transition Table

| 函数 | 目标 status | 目标 stage | 文件位置 | 典型调用方 |
|------|------------|-----------|----------|------------|
| `start_processing()` | `PENDING` | `RUNNING` | 保持原值 | runner 开始处理任务 |
| `mark_processing_step()` | `PENDING` | `RUNNING` | 保持原值 | step 进度更新 |
| `mark_temp_ready()` | 保持原值 | 保持原值 | `temp` | copy 完成后 |
| `mark_confirming()` | `PENDING` | `AWAIT_REVIEW` | `temp` | 三级匹配进入用户确认 |
| `mark_confirmed()` | 保持原值 | 保持原值 | 保持原值 | 用户确认任务 |
| `mark_needs_review()` | `PENDING` | `AWAIT_REVIEW` | `temp` | 匹配疑虑需要人工确认 |
| `mark_failed()` | `FAILED` | `DONE` | 默认 `source` | import-flow/API 失败分支 |
| `mark_skipped()` | `SKIPPED` | `DONE` | 默认 `source` | 去重跳过或用户忽略 |
| `mark_cancelled()` | `CANCELLED` | `DONE` | 默认 `source` | 用户取消排队任务 |
| `mark_imported()` | `SUCCESS` | `DONE` | `import` | 入库成功 |
| `reset_for_retry()` | `PENDING` | `QUEUED` | `source` | 重试失败、跳过或已取消任务 |

## Orphan RUNNING Cleanup

服务启动时调用 `_cleanup_orphaned_state` 清理两类异常状态：

1. 旧 `PROCESSING` 或当前 `PENDING/RUNNING` 任务被识别为孤儿（服务中断/重启遗留），清理 temp 目录下的临时视频和字幕后，通过 `mark_failed()` 标记为 `FAILED/DONE`：

   ```text
   status=FAILED
   stage=DONE
   error_message=服务中断或重启导致任务未完成，请重试
   file_location=source
   video_path=""
   current_step=0
   percentage=0
   ```

   任务在“失败”筛选中可见，用户可手动重试。

2. `PENDING/AWAIT_REVIEW` 任务的 temp 文件被登记为活跃文件，清理时保留，避免误删等待人工确认的视频。

孤儿任务不应自动重置为 `PENDING/QUEUED`，因为自动恢复会掩盖服务中断事实，并可能在反复崩溃时形成隐性循环。

## Frontend Modal Edit Permission Matrix

任务详情模态框中文件名和分类维度的可编辑性、保存按钮的可见性、错误反馈位置都按状态严格区分，保证用户只能在合理窗口内变更任务输入、且失败原因能精准定位到对应字段：

| Status / Stage | 文件名输入框可编辑 | 分类维度输入框可编辑 | "保存文件名"按钮 | "保存分类"按钮 | 错误反馈区 | 状态提示 |
|----------------|-------------------|---------------------|-----------------|----------------|-----------|---------|
| `PENDING / QUEUED` | ✗ | ✗ | ✗（隐藏） | ✗（隐藏） | 不可见 | 排队中 — 只读，不可编辑 |
| `PENDING / RUNNING` | ✗ | ✗ | ✗（隐藏） | ✗（隐藏） | 不可见 | 处理中 — 不可编辑 |
| `PENDING / AWAIT_REVIEW` | ✓ | ✓ | ✓ | ✓ | 两个错误区独立可见 | 待确认 — 可修改文件名和维度后确认入库 |
| `FAILED / DONE` | ✗ | ✗ | ✗（隐藏） | ✗（隐藏） | 不可见 | 失败 — 只读，可重试 |
| `SKIPPED / DONE` | ✗ | ✗ | ✗（隐藏） | ✗（隐藏） | 不可见 | 已跳过 — 只读 |
| `CANCELLED / DONE` | ✗ | ✗ | ✗（隐藏） | ✗（隐藏） | 不可见 | 已取消 — 只读，可重新投入 |
| `SUCCESS / DONE` | ✗ | ✗ | ✗（隐藏） | ✗（隐藏） | 不可见 | 已完成 — 只读 |

### 按钮独立性原则

- "保存文件名"和"保存分类"是两个**完全独立**的按钮，分别触发自己的 API 调用（`/tasks/{id}/rename` 与 `/tasks/{id}/reclassify`），互不阻塞。
- 用户只改了其中一个字段时，只需点击对应的保存按钮；另一个按钮可隐藏也可点击保存（幂等无变化），但不会强制要求两个都保存。
- 任一保存按钮失败时，错误信息显示在该按钮**紧邻的错误区**（`#filename-error-area` / `#dims-error-area`），同时通过全局 Toast 提示，不影响另一个按钮的可操作性。
- 两个按钮的"保存中..."状态独立，按钮被禁用但不影响另一个按钮的可用性。

### 前端实现要点

- `getTaskEditPermission(task)` 函数（`cinema-tasks.js`）集中表达上述矩阵，模态框渲染时读取权限决定输入框和按钮的可见性。
- `handleSaveFilename` 与 `handleSaveDims` 是两个独立处理函数，分别封装各自的请求、错误反馈和刷新逻辑。
- 文件名输入字段 `#task-rename-input` 仅在 `PENDING/AWAIT_REVIEW` 时渲染。
- 分类维度表单 `[data-task-dim]` 仅在 `PENDING/AWAIT_REVIEW` 时渲染为可编辑态。
- 保存按钮按权限独立渲染为"保存文件名"、"保存分类"，与对应错误反馈区紧邻显示。
- 保存成功后关闭模态框、刷新任务列表和仪表盘计数，保证用户看到最新状态。

## Update Rule

新增状态或文件位置时必须同步：

- `media_importer/core/db/constants.py`（真实实现，通过 `media_importer.infrastructure.db` facade 访问）
- `media_importer/core/task_lifecycle.py`
- `media_importer/features/tasks/`
- `media_importer/core/task_manager.py`
- `media_importer/features/import_flow/`
- `media_importer/api/task_handlers.py`
- `media_importer/webui/js/cinema-tasks.js`
- `docs/testing/regression-matrix.md`
- `tests/test_task_context_lifecycle.py`
- `tests/test_stage_lifecycle.py`（新增 stage 专项测试）