# Tasks Feature

任务能力负责扫描任务的创建、状态流转、重试、失败记录、人工确认状态和任务查询。

## Current Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/tasks/__init__.py` | Feature public API for `TaskManager`, lifecycle transitions, and task constants. |
| `media_importer/features/tasks/list_service.py` | API-facing task list pagination, status validation, and status-count payload assembly. |
| `media_importer/features/tasks/queue_service.py` | API-facing queue clear/retry/retry-all/pause/resume/status orchestration. |
| `media_importer/features/tasks/review_service.py` | API-facing manual review actions: confirm, reclassify, and confirm-all orchestration. |
| `media_importer/features/tasks/repository.py` | Task feature repo facade over task DB operations. |
| `media_importer/core/task_manager.py` | Task creation, querying, and updates. |
| `media_importer/core/task_lifecycle.py` | Centralized lifecycle transitions. |
| `media_importer/core/db/constants.py` | Task status constants. |
| `media_importer/core/db/task_repo.py` | Task repository operations. |
| `media_importer/api/task_handlers.py` | Task HTTP handlers. |
| `media_importer/features/import_flow/context.py` | Task-scoped import flow state. |

## Related Areas

- Database: `tasks` table and JSON fields.
- Frontend: task list/detail, retry, confirm, progress, status filters.
- Import flow: every processing step should use lifecycle helpers for state changes.
- Public task DB helpers for feature/API consumers are exposed through `media_importer.features.tasks.repository`.
- `/api/tasks` list payloads are assembled through `media_importer.features.tasks.list_service`.
- Queue operations from `api/task_handlers.py` are delegated to `media_importer.features.tasks.queue_service`.
- Manual review actions from `api/task_handlers.py` are delegated to `media_importer.features.tasks.review_service`.

## Tests

- Task manager and lifecycle tests.
- Import flow tests that assert state transitions.
- `tests/test_feature_task_queue.py` covers queue service behavior without starting real background workers.
- `tests/test_feature_task_review.py` covers manual review action behavior with fake pipeline/task manager objects.
- API task tests.

## Migration Notes

- New app/API/import-flow code should import from `media_importer.features.tasks`.
- New task repository usage should import from `media_importer.features.tasks.repository`.
- Use `media_importer.infrastructure.db` for shared raw SQLite/repo infrastructure.
- Queue/retry/clear API actions should use `media_importer.features.tasks.queue_service`; do not reintroduce status validation in API handlers.
- Confirm/reclassify/confirm-all API actions should use `media_importer.features.tasks.review_service`; API handlers should not call pipeline review methods directly.
- Any status change must update lifecycle docs, tests, API/frontend display logic, and regression matrix.
