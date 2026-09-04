# Tasks Feature

任务能力负责扫描任务的创建、状态流转、重试、失败记录、人工确认状态和任务查询。

## Status + Stage Model

任务状态采用双层模型：

- **status**（终态）：`PENDING` / `SUCCESS` / `FAILED` / `SKIPPED` / `CANCELLED`
- **stage**（处理环节，仅 status=PENDING 时有意义）：`QUEUED` / `RUNNING` / `AWAIT_REVIEW` / `DONE`

旧状态映射：`PROCESSING` → `PENDING+RUNNING`，`CONFIRMING` / `NEEDS_REVIEW` → `PENDING+AWAIT_REVIEW`。

详细转换表见 [architecture/task-lifecycle.md](../architecture/task-lifecycle.md)。

## Current Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/tasks/__init__.py` | Feature public API for `TaskManager`, lifecycle transitions, and task constants. |
| `media_importer/features/tasks/cancel_service.py` | API-facing cancel action for queued tasks, mapping TaskManager results to API responses. |
| `media_importer/features/tasks/detail_service.py` | API-facing task detail, subtitles, and status-count query payloads. |
| `media_importer/features/tasks/dashboard_service.py` | Read-only dashboard business summary, recent activities/movies, and thumbnail-cache maintenance orchestration. |
| `media_importer/features/tasks/file_lifecycle_service.py` | API-facing file lifecycle actions; currently owns same-directory task file rename and ignore flow cleanup/recycle decisions. |
| `media_importer/features/tasks/list_service.py` | API-facing task list pagination, status validation, and status-count payload assembly. |
| `media_importer/features/tasks/organization_service.py` | 已完成兜底结果识别，以及关联“重新整理”任务的创建门禁。 |
| `media_importer/features/tasks/disposition_service.py` | 状态感知的“结束处理”：协作停止、来源保留/回收/受控永久删除及目标片库保护。 |
| `media_importer/features/tasks/delete_service.py` | 只删除已结束任务的数据库记录；文件处置必须走 disposition service。 |
| `media_importer/features/tasks/queue_service.py` | API-facing queue clear/retry/retry-all/pause/resume/status orchestration. |
| `media_importer/features/tasks/review_service.py` | API-facing manual review actions: confirm, reclassify, and confirm-all orchestration. |
| `media_importer/features/tasks/series_batch_service.py` | 保守识别同一可信父目录、同标准化剧名且季集号唯一的待确认电视剧批次。 |
| `media_importer/features/tasks/repository.py` | Task feature repo facade over task DB operations. |
| `media_importer/core/task_manager.py` | Task creation, querying, and updates. |
| `media_importer/core/task_lifecycle.py` | Centralized lifecycle transitions. |
| `media_importer/core/db/constants.py` | Task status constants (真实实现,通过 `media_importer.infrastructure.db` facade 访问)。 |
| `media_importer/core/db/task_repo.py` | Task repository operations (真实实现,通过 `media_importer.infrastructure.db` facade 访问)。 |
| `media_importer/api/task_handlers.py` | Task HTTP handlers. |
| `media_importer/features/import_flow/context.py` | Task-scoped import flow state. |
| `media_importer/features/import_flow/concurrency.py` | 任务有效并发解析与 Pipeline 级共享槽位，统一约束队列、重试、单文件和确认入口。 |

## Related Areas

- Database: `tasks` table and JSON fields.
- Frontend: task list/detail, retry, confirm, progress, status filters.
- Import flow: every processing step should use lifecycle helpers for state changes.
- Public task DB helpers for feature/API consumers are exposed through `media_importer.features.tasks.repository`.
- `/api/tasks` list payloads are assembled through `media_importer.features.tasks.list_service`.
- Task detail, subtitles, and stats payloads are assembled through `media_importer.features.tasks.detail_service`.
- Queue operations from `api/task_handlers.py` are delegated to `media_importer.features.tasks.queue_service`.
- Cancel actions from `api/task_handlers.py` are delegated to `media_importer.features.tasks.cancel_service`; V1 only allows `PENDING/QUEUED` tasks to become `CANCELLED/DONE`.
- Manual review actions from `api/task_handlers.py` are delegated to `media_importer.features.tasks.review_service`.
- `PENDING/AWAIT_REVIEW` 中 `dedup_result.status=awaiting_user` 表示目标片库冲突。该任务必须逐项处理；批量确认返回排除数量，不能代替用户做覆盖决定。
- Task rename and ignore are delegated to `media_importer.features.tasks.file_lifecycle_service`, including path-traversal filename rejection, source recycle handoff, and DB field updates。已入库文件受保护，通用任务重命名拒绝 `file_location=import`。
- `POST /api/tasks/{id}/dispose` 承担“结束处理”。排队任务直接取消，待确认/失败任务结束为跳过，运行任务先持久化停止请求并在安全检查点完成；来源去向必须明确选择保留、本地回收或已启用的永久删除。
- `cancel_requested/stop_requested_at/requested_source_disposition` 表示协作停止请求；`outcome_code/source_disposition/source_disposition_message` 表示业务结果。它们不能和 `status/stage` 混用。
- 单任务来源处置只处理数据库登记的视频和字幕，不递归猜测同目录文件；重新整理任务和任何落入片库根的路径固定拒绝文件处置。
- 任务删除只允许已结束任务且只删除记录；来源与片库文件均不改动。活动任务必须先“结束处理”，不能把删除记录当成取消或文件删除。
- 首页状态、今日入库、最近业务活动和最近影片由 `media_importer.features.tasks.dashboard_service` 聚合；前端不得从原始日志或图片 mtime 推断这些口径。
- 首页摘要每 15 秒仍读取 SQLite 业务快照，但最近影片仅在快照键变化时重新验证海报文件；海报缓存裁剪最多每 24 小时一次。配置中的片库根已在保存时规范化，摘要刷新不得为边界判断再次 `realpath` 或遍历目标片库。
- `/api/tasks` 列表直接返回 `current_step/total_steps/step_name/percentage/bytes_copied/total_bytes/source_cleanup_status`。任务卡只对 `PENDING/RUNNING` 显示当前中文阶段；只有真实字节阶段显示阶段百分比，固定流程权重不能当作耗时比例。
- 文件阶段同时返回当前成员名称、类型、序号和总数；详情字幕表显示来源文件、语言、计划文件名、当前状态和最终路径。`und` 必须显示“未识别”，不能伪装成中文或空值。
- 等待确认任务可用类型、语言、年份搜索最多 20 个 Provider 候选；选择候选后先按 Provider ID 验证，再把最小人工作品绑定持久化并重新排队。任务取得共享并发槽后才获取详情、重算维度/分类/标准文件名/冲突并继续；冲突或兜底会再次停在 `AWAIT_REVIEW`。
- 重新整理任务的来源已在目标片库内，是上述自动排队的安全例外：手动刮削只刷新预览，必须由用户确认后走专用片库内移动，禁止进入普通来源复制流程。
- 电视剧候选应用前先调用同剧批次预览。同一实际父目录、标准化剧名一致、季集号有效且唯一的 `PENDING/AWAIT_REVIEW` 和 `PENDING/QUEUED` 任务可继承；运行中任务只显示、不改写。电影、跨目录、未决片库冲突和已人工选择其他 Provider 的任务排除。用户可逐项取消，提交时服务端再次校验任务 ID。批量套用只共享 Provider 作品身份，每集独立保留季集号并在真正运行时生成自己的标准文件名。
- 确认接口快速返回并由服务进程内后台 worker 继续；关闭浏览器或前端弹窗不取消任务。同一任务有进程内重复 worker 门禁；文件包提交窗口另由持久化清单在服务重启后恢复。
- 正常任务未匹配正式规则时必须进入 `PENDING/AWAIT_REVIEW`，只有用户明确接受待整理区后才能继续。成功入库后仍是 `SUCCESS/DONE`，用 `organization_status=FALLBACK_PENDING` 表达后续可整理，不能再显示成“需确认”或重新打开原任务。
- `POST /api/tasks/{id}/reorganize` 只对 `SUCCESS/DONE + FALLBACK_PENDING` 创建一条 `task_kind=REORGANIZE` 的关联新任务。新任务允许改维度和手动刮削，但必须匹配正式规则才能确认；完成后原任务与新任务都保持独立审计记录。兜底、重新整理和片库冲突任务全部排除批量确认。
- 任务页存在运行项时每 2.5 秒静默刷新；页面隐藏、离开任务页、打开弹窗或批量选择时暂停。静默刷新按任务 ID 对账，仅替换数据发生变化的卡片并复用相同封面节点，不重建整个列表；已经“加载更多”的页面继续保留，不能退回单页或清空选择。
- 重试是整任务重来：清空刮削、维度、规则、冲突、进度和文件包日志，从原始来源重新排队。服务重启只允许“提交前安全回退为失败”“完整提交复核为成功”“歧义现场保留待人工检查”三种结果；完整提交恢复会保留来源，不在重启阶段补做来源清理。
- 自动扫描发现同一路径的最新任务已经 `FAILED` 时跳过新建并刷新发现时间，避免重复失败记录和重复大文件 I/O；恢复处理必须由用户在原失败任务上显式执行“重新识别/重试”，该入口仍复用原任务记录。
- 任务页“批量重新识别”只对选中的 `FAILED` 与 `PENDING/AWAIT_REVIEW` 生效，逐项复用单任务重试状态机；其他状态不发送。该操作用于让旧待确认任务使用当前版本规则重跑，不代表自动确认或入库。
- 正常批处理、自动扫描后的处理、单文件处理、单任务/批量重新识别及人工确认共享同一进程内任务槽位。`task_queue.max_concurrent=1|2` 是实际生效上限；队列 worker 取得槽位后才领取任务，避免等待任务提前显示为运行中。同一 Pipeline 同时只允许一个 `run_all` 调度循环，重复触发直接忽略。

## Tests

- `tests/test_task_context_lifecycle.py` — legacy lifecycle transition contract tests.
- `tests/test_stage_lifecycle.py` — stage transition unit tests for status+stage dual model.
- `tests/test_migration_confirm_reason_drop.py` — DB migration tests.
- `tests/test_classify_preview.py` — classify-preview API unit and integration tests.
- Task manager and lifecycle tests.
- `tests/test_feature_task_detail.py` covers detail, subtitles, and stats feature responses.
- Import flow tests that assert state transitions.
- `tests/test_feature_task_queue.py` covers queue service behavior without starting real background workers.
- `tests/test_feature_task_cancel.py` covers cancel lifecycle, TaskManager cancel rules, API service responses, retry from CANCELLED, and CANCELLED list filtering.
- `tests/test_feature_task_review.py` covers manual review action behavior with fake pipeline/task manager objects.
- `tests/test_series_batch_scrape_apply.py` 与 `tests/test_manual_provider_binding.py` 覆盖《北海鲸梦》混合状态 5 集分组、危险任务排除、后端任务 ID 复核、绑定重启持久化、运行中不改写、精确 Provider 消费、季集号保留及标准文件名。
- `tests/test_task_concurrency_limit.py` 覆盖并发 1–2、历史异常值钳制、第三个任务不提前领取、重复批处理抑制和确认入口共享槽位。
- `tests/test_feature_task_file_lifecycle.py` covers task file rename behavior, filename safety checks, ignore cleanup, recycle handoff, and invalid status handling.
- `tests/test_feature_task_list.py` covers pagination, status validation, and active-count assembly.
- `tests/test_cleanup_orphaned_state.py` covers startup orphan RUNNING -> FAILED transition and AWAIT_REVIEW protection.
- `tests/test_dashboard_summary.py` covers dashboard status counts, real running progress, local-day success count, activity bounds, recent-movie dedupe, unchanged-snapshot reuse, daily thumbnail maintenance throttling, and thumbnail-cache safety limits.
- `tests/test_target_library_conflict_safety.py` / `tests/test_target_library_conflict_ui.py` 覆盖冲突零写入、三种决策、安全替换、配置收敛和桌面/手机合同。
- `tests/test_task_organization.py` / `tests/test_task_organization_ui.py` 覆盖历史兜底补标、关联任务幂等创建、影片字幕整包移动、冲突零覆盖、重启恢复和前端状态边界。
- `tests/test_task_disposition.py` / `tests/test_task_disposition_ui.py` 覆盖各状态退出、精确来源成员、协作停止、提交点保护、只删记录和普通人可理解的前端动作。
- `tests/test_task_organization_browser_ui.py` 使用真实本地 HTTP 服务与 Chromium，从用户界面完成“历史兜底 → 创建重新整理 → 手动刮削 → 正式规则入库”、移动端详情、影片字幕整包移动、同名冲突保留、明确确认兜底及提交后重启恢复的端到端验收；同时拦截页面脚本错误和服务端 5xx。

## Migration Notes

- New app/API/import-flow code should import from `media_importer.features.tasks`.
- New task repository usage should import from `media_importer.features.tasks.repository`.
- Use `media_importer.infrastructure.db` for shared raw SQLite/repo infrastructure.
- Detail/subtitles/stats API actions should use `media_importer.features.tasks.detail_service`; API handlers should not read task DB/subtitle DB directly.
- Queue/retry/clear API actions should use `media_importer.features.tasks.queue_service`; do not reintroduce status validation in API handlers.
- Confirm/reclassify/confirm-all API actions should use `media_importer.features.tasks.review_service`; API handlers should not call pipeline review methods directly.
- Rename/ignore API actions should use `media_importer.features.tasks.file_lifecycle_service`; API handlers should not perform filesystem rename/delete or recycle decisions directly.
- Any status change must update lifecycle docs, tests, API/frontend display logic, and regression matrix.
