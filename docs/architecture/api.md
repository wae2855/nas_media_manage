# API Architecture

## Current Pattern

- 原生 `BaseHTTPRequestHandler`。
- `api/handler.py` 负责路由分发和 server 启动。
- 业务 handler 按 Mixin 拆分在 `api/*_handlers.py`。
- JSON 响应格式统一为 `{code, status, message, data}`。

## Entry Points

- `media_importer/api/handler.py`
- `media_importer/api/utils.py`
- `media_importer/api/task_handlers.py`
- `media_importer/api/config_handlers.py`
- `media_importer/api/provider_handlers.py`
- `media_importer/api/recycle_handlers.py`
- `media_importer/api/source_cleaner_handlers.py`

## Direction

后续会逐步引入 route table，让新增 API 不再扩展长 `if/elif` 分支。迁移前不改变现有路径和响应格式。

## Standards

见 [../standards/api.md](../standards/api.md)。
