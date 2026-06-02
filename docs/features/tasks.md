# Tasks Feature

任务能力负责扫描任务的创建、状态流转、重试、失败记录、人工确认状态和任务查询。

## Current Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/tasks/__init__.py` | Feature public API for `TaskManager`, lifecycle transitions, and task constants. |
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

## Tests

- Task manager and lifecycle tests.
- Import flow tests that assert state transitions.
- API task tests.

## Migration Notes

- New app/API/import-flow code should import from `media_importer.features.tasks`.
- New task repository usage should import from `media_importer.features.tasks.repository`.
- Use `media_importer.infrastructure.db` for shared raw SQLite/repo infrastructure.
- Any status change must update lifecycle docs, tests, API/frontend display logic, and regression matrix.
