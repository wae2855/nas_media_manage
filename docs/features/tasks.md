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
| `media_importer/features/tasks/file_lifecycle_service.py` | API-facing file lifecycle actions; currently owns same-directory task file rename and ignore flow cleanup/recycle decisions. |
| `media_importer/features/tasks/list_service.py` | API-facing task list pagination, status validation, and status-count payload assembly. |
| `media_importer/features/tasks/queue_service.py` | API-facing queue clear/retry/retry-all/pause/resume/status orchestration. |
| `media_importer/features/tasks/review_service.py` | API-facing manual review actions: confirm, reclassify, and confirm-all orchestration. |
| `media_importer/features/tasks/repository.py` | Task feature repo facade over task DB operations. |
| `media_importer/core/task_manager.py` | Task creation, querying, and updates. |
| `media_importer/core/task_lifecycle.py` | Centralized lifecycle transitions. |
| `media_importer/core/db/constants.py` | Task status constants (真实实现,通过 `media_importer.infrastructure.db` facade 访问)。 |
| `media_importer/core/db/task_repo.py` | Task repository operations (真实实现,通过 `media_importer.infrastructure.db` facade 访问)。 |
| `media_importer/api/task_handlers.py` | Task HTTP handlers. |
| `media_importer/features/import_flow/context.py` | Task-scoped import flow state. |

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
- Task rename and ignore are delegated to `media_importer.features.tasks.file_lifecycle_service`, including path-traversal filename rejection, temp cleanup boundaries, recycle handoff, and DB field updates.

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
- `tests/test_feature_task_file_lifecycle.py` covers task file rename behavior, filename safety checks, ignore cleanup, recycle handoff, and invalid status handling.
- `tests/test_feature_task_list.py` covers pagination, status validation, and active-count assembly.
- `tests/test_cleanup_orphaned_state.py` covers startup orphan RUNNING -> FAILED transition and AWAIT_REVIEW protection.

## Migration Notes

- New app/API/import-flow code should import from `media_importer.features.tasks`.
- New task repository usage should import from `media_importer.features.tasks.repository`.
- Use `media_importer.infrastructure.db` for shared raw SQLite/repo infrastructure.
- Detail/subtitles/stats API actions should use `media_importer.features.tasks.detail_service`; API handlers should not read task DB/subtitle DB directly.
- Queue/retry/clear API actions should use `media_importer.features.tasks.queue_service`; do not reintroduce status validation in API handlers.
- Confirm/reclassify/confirm-all API actions should use `media_importer.features.tasks.review_service`; API handlers should not call pipeline review methods directly.
- Rename/ignore API actions should use `media_importer.features.tasks.file_lifecycle_service`; API handlers should not perform filesystem rename/delete or recycle decisions directly.
- Any status change must update lifecycle docs, tests, API/frontend display logic, and regression matrix.
