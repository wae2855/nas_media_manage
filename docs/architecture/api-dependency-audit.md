# API Dependency Audit

本文件记录 Phase 4 API 薄化的当前盘点。目标是让 API handler 主要负责参数解析、错误包装和 JSON 响应，业务策略下沉到 feature service。

## Direct Dependency Inventory

| API Area | Current Direct Dependencies | Direction |
|----------|-----------------------------|-----------|
| `handler.py` | `features.tasks`, `features.import_flow`, `core.metrics`, `core.logger`, `notify`, `monitor`, `core.db` | Startup scan now uses feature import-flow entry; remaining startup wiring still needs application-service cleanup. |
| `task_handlers.py` | `core.db`, `features.tasks`, `api.task_delete`, `core.safety` for path validation | Task delete, task list, queue actions, manual review actions, and task rename now use `features.tasks`; ignore/run-file still need file lifecycle/application services. |
| `task_delete.py` | `features.tasks.delete_task` | Thin API wrapper after Phase 4 proof slice. |
| `config_handlers.py` | `features.configuration`, `features.tasks`, config save utilities | UI config payloads, section save splitting, permission/path payload assembly, watcher status, runtime refresh, and task list payloads now route through feature services. |
| `connectivity_handlers.py` | `features.scraping`, `features.configuration`, `core.metrics`, `core.safety` | Connectivity calls mostly feature-backed; path write check remains infrastructure/safety. |
| `dimension_handlers.py` | `features.scraping` | Dimension CRUD and tier checks now route through `features.scraping.dimensions_service`; handler no longer imports dimension DB functions directly. |
| `provider_handlers.py` | `features.providers` | Acceptable direction. |
| `prompt_handlers.py` | `features.prompts`, API utilities | Global prompt file load/save/reset now routes through `features.prompts.application_service`. |
| `source_cleaner_handlers.py` | `features.source_cleaning`, `monitor.permission_checker` | Task path listing, status shaping, records access, and execute orchestration now route through `features.source_cleaning.application_service`; permission check remains infrastructure-bound. |
| `tmdb_handlers.py` | `features.scraping`, `features.providers` | Acceptable for current scraping/provider proof slice. |
| `recycle_handlers.py` | `features.recycle` | Acceptable direction. |

## Proof Slice

Task deletion now calls `media_importer.features.tasks.delete_task`, which owns temp cleanup, optional recycle behavior, and task record deletion. `media_importer/api/task_delete.py` now only adapts global API state to the service result and writes a JSON response.

Task queue actions now call `media_importer.features.tasks.queue_service`, which owns status validation for clear, retry/retry-all orchestration, pause/resume metrics updates, and queue status payload assembly. `media_importer/api/task_handlers.py` still owns HTTP adaptation and retains more complex file lifecycle actions for a later service migration.

Task manual review actions now call `media_importer.features.tasks.review_service`, which owns confirm, reclassify, and confirm-all orchestration over the pipeline/task manager. File lifecycle actions remain in the handler until they are moved behind a safety-focused service.

Task rename now calls `media_importer.features.tasks.file_lifecycle_service`, which owns same-directory file rename, filename-only validation, and DB path field updates. This service rejects path-bearing filenames before filesystem operations.

Startup scan in `api/handler.py` now imports `scan_source_dir` from `media_importer.features.import_flow`, instead of directly calling `storage.file_scanner`.

## Next Candidates

- Move task ignore/run-file actions behind task/import-flow feature services.
- Continue thinning provider/config global orchestration after prompt file operations were moved into `features/prompts`.
- Move config permission checks into configuration/infrastructure services.
