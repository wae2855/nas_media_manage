# API Dependency Audit

本文件记录 Phase 4 API 薄化的当前盘点。目标是让 API handler 主要负责参数解析、错误包装和 JSON 响应，业务策略下沉到 feature service。

## Direct Dependency Inventory

| API Area | Current Direct Dependencies | Direction |
|----------|-----------------------------|-----------|
| `handler.py` | `features.tasks`, `core.metrics`, `core.logger`, `notify`, `monitor`, `core.db`, `storage.file_scanner` | Keep startup wiring for now; scan should move to feature/application service later. |
| `task_handlers.py` | `core.db`, `features.tasks`, `api.task_delete`, `core.safety` for path validation | Task delete proof slice moved to `features.tasks.delete_service`; path validation remains pending. |
| `task_delete.py` | `features.tasks.delete_task` | Thin API wrapper after Phase 4 proof slice. |
| `config_handlers.py` | `notify`, `monitor`, `core.db`, config save utilities | Needs configuration/application service for permission and task export actions. |
| `connectivity_handlers.py` | `features.scraping`, `features.configuration`, `core.metrics`, `core.safety` | Connectivity calls mostly feature-backed; path write check remains infrastructure/safety. |
| `dimension_handlers.py` | `core.db`, `features.scraping` | Dimension repository should become feature/infrastructure facade. |
| `provider_handlers.py` | `features.providers` | Acceptable direction. |
| `prompt_handlers.py` | prompt file operations and API utilities | Candidate for `features.prompts` service. |
| `source_cleaner_handlers.py` | `features.source_cleaning`, `monitor.permission_checker`, `core.db.task_repo` | Cleaner actions are feature-backed; task path listing and permission check remain pending. |
| `tmdb_handlers.py` | `features.scraping`, `features.providers` | Acceptable for current scraping/provider proof slice. |
| `recycle_handlers.py` | `features.recycle` | Acceptable direction. |

## Proof Slice

Task deletion now calls `media_importer.features.tasks.delete_task`, which owns temp cleanup, optional recycle behavior, and task record deletion. `media_importer/api/task_delete.py` now only adapts global API state to the service result and writes a JSON response.

## Next Candidates

- Move scan-source action from `api/handler.py` and CLI into an application/feature service.
- Move dimension API DB calls behind a dimension feature/repository facade.
- Move prompt file read/write behavior into `features/prompts`.
- Move config permission checks into configuration/infrastructure services.
