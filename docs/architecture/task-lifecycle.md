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

运行中的细分进度不扩展 status/stage，而由 `current_step`、`step_name`、`percentage`、`bytes_copied`、`total_bytes` 表达。文件阶段使用 `import_*`、`source_cleanup_*` 区分传输、源/目标 SHA-256 校验和安全发布；非字节阶段只表示流程位置，不伪装为文件百分比。

`organization_status` 是成功结果的后续整理状态，不是第二套任务终态：`FALLBACK_PENDING` 表示已成功入库到待整理区，`ORGANIZED` 表示关联新任务已按正式规则整理。两者都不得把原 `SUCCESS/DONE` 任务重新变回活动态。

## Current File Locations

`file_location` 用于追踪文件当前位置，典型值：

- `source`
- `import`
- `recycle`

## Direction

`media_importer/features/tasks/` 是任务状态、`TaskManager` 和生命周期 helper 的业务入口。`media_importer/core/task_lifecycle.py` 是当前集中状态转换和文件位置规则的实现文件。

当前已集中：

- processing 开始（status=PENDING, stage=RUNNING）；
- confirming（status=PENDING, stage=AWAIT_REVIEW）；
- needs review（status=PENDING, stage=AWAIT_REVIEW，与 confirming 相同 stage）；
- failed（status=FAILED, stage=DONE）；
- skipped（status=SKIPPED, stage=DONE）；
- imported（status=SUCCESS, stage=DONE）；
- cancelled（status=CANCELLED, stage=DONE）；
- retry reset（status=PENDING, stage=QUEUED）。

当前 import-flow step 继续接收原始 task dict；跨步骤更新通过 `TaskContext` 和 `TaskLifecycle` 集中表达。

## Source Task Creation Idempotency

普通来源任务在进入状态机前先执行原子“创建或复用”：真实路径相同的所有 `PENDING` 阶段与 `FAILED/DONE` 复用现有任务；来源未变化的 `SUCCESS/SKIPPED/CANCELLED` 也不重新进入状态机。文件大小明确变化时允许创建新的 `PENDING/QUEUED` 审计任务，仅修改时间变化只更新来源证据。该门禁不改变任何既有状态，也不自动重试失败任务。

手动单文件请求只有成功创建新任务后才启动 worker；复用时返回既有任务 ID、状态与原因。来源任务创建锁只保证当前 fnOS 单进程实例，未来多实例部署需要数据库租约或等价约束。

## Transition Table

| 函数 | 目标 status | 目标 stage | 文件位置 | 典型调用方 |
|------|------------|-----------|----------|------------|
| `start_processing()` | `PENDING` | `RUNNING` | 保持原值 | runner 开始处理任务 |
| `mark_processing_step()` | `PENDING` | `RUNNING` | 保持原值 | step 进度更新 |
| `mark_confirming()` | `PENDING` | `AWAIT_REVIEW` | 通常 `source` | 刮削核对或目标片库冲突进入用户确认；此时尚未传输大文件 |
| `mark_confirmed()` | 保持原值 | 保持原值 | 保持原值 | 用户确认任务 |
| `mark_needs_review()` | `PENDING` | `AWAIT_REVIEW` | `source` | 匹配疑虑需要人工确认；此时尚未传输大文件 |
| `manual_bind_queue` | `PENDING` | `QUEUED` | `source` | 人工选定 Provider 后持久化作品绑定并重新排队；不增加重试次数 |
| `mark_failed()` | `FAILED` | `DONE` | 默认 `source` | import-flow/API 失败分支 |
| `mark_skipped()` | `SKIPPED` | `DONE` | 默认 `source` | 用户保留片库现有文件或忽略任务 |
| `mark_cancelled()` | `CANCELLED` | `DONE` | 默认 `source` | 用户取消排队任务 |
| `mark_imported()` | `SUCCESS` | `DONE` | `import` | 入库成功 |
| `reset_for_retry()` | `PENDING` | `QUEUED` | `source` | 重试失败、跳过或已取消任务 |

协作式停止不新增 status：运行中先写 `cancel_requested=1` 与 `requested_source_disposition`，worker 在提交点之前的安全检查点回退任务暂存，然后以 `CANCELLED/DONE + outcome_code=USER_STOPPED` 结束。视频文件包已经提交后不再接受停止，继续完成来源收尾和成功落库。

`source_disposition` 独立记录 `kept/recycled/deleted/missing/failed`。删除任务记录不修改该事实，也不产生文件操作。

人工 Provider 绑定在任务取得并发槽后消费。电视剧只继承作品身份，每个任务的季集号仍来自自身文件；成功加载详情后清空绑定。运行中任务禁止中途改写，冲突或兜底仍返回 `AWAIT_REVIEW`。

`mark_imported()` 只能在片库新文件安全发布、来源策略已完成或已明确记录为 `WAITING/BLOCKED/FAILED/SKIPPED` 后调用。来源处理期间任务保持 `PENDING/RUNNING`，同时保留 `import_success=1` 与 `import_video_path`；来源处理异常不得把已发布片库文件回滚、删除或重复入库。

## Orphan RUNNING Cleanup

服务启动时调用 `_cleanup_orphaned_state` 清理两类异常状态：

0. 先读取 `bundle_state/bundle_manifest/bundle_committed` 恢复中断文件包：

   - 视频最终文件尚未发布：普通入库只清理本任务创建且指纹吻合的目标临时成员并保留来源；重新整理任务把成员退回原片库位置；任务标记为可从头重试的失败；
   - 视频最终文件已发布且视频/全部字幕均与清单一致：只补齐任务和字幕成功状态，不再次写入片库，也不在重启后补做来源删除；
   - `task_kind=REORGANIZE` 时，清单来源允许位于已配置片库：提交前中断只退回原待整理位置，提交后只修复父子任务和字幕记录，不重复移动或删除任何片库文件；
   - 提交标记存在但成员缺失、指纹变化或路径越界：保留片库现场，标记 `RECOVERY_REQUIRED`，禁止自动删除、覆盖或反复恢复；
   - 已正常 `SUCCESS/import_success=1` 的 `COMMITTED` 日志只用于审计，启动时直接跳过。

1. 没有文件包清单的 `PENDING/RUNNING` 任务被识别为孤儿（服务中断/重启遗留）。系统不猜测已完成步骤、不扫描片库，也不触碰来源或正式片库文件，只通过 `mark_failed()` 标记为 `FAILED/DONE`：

   ```text
   status=FAILED
   stage=DONE
   error_message=服务中断或重启导致任务未完成，请重试
   file_location=source
   video_path=<原始来源路径>
   current_step=0
   percentage=0
   ```

   任务在“失败”筛选中可见，用户可手动重试。

   只有持久文件包清单完整且全部正式成员路径、大小和 SHA-256 一致时，才允许修复为 `SUCCESS/DONE/import`；单独的 `import_success` 或现存路径不构成成功证据。

2. `PENDING/AWAIT_REVIEW` 任务始终引用来源文件，尚未开始大文件传输。

孤儿任务不应自动重置为 `PENDING/QUEUED`，因为自动恢复会掩盖服务中断事实，并可能在反复崩溃时形成隐性循环。

## Frontend Modal Edit Permission Matrix

任务详情模态框中文件名和分类维度的可编辑性、保存按钮的可见性、错误反馈位置都按状态严格区分，保证用户只能在合理窗口内变更任务输入、且失败原因能精准定位到对应字段：

目标片库冲突是 `AWAIT_REVIEW` 的受限子状态：详情不展示普通“确认入库”，而是展示现有/待入库文件对比以及保留现有、保留两份、替换现有三个动作。替换必须二次确认；冲突任务不进入批量确认。

兜底确认也是受限子状态：普通入库任务必须显式接受“放入待整理区”；重新整理任务仍匹配兜底时不展示确认按钮。已完成兜底任务只读，界面仅可创建独立关联的 `REORGANIZE` 任务。

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
