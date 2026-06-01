# API Architecture

## Current Pattern

- 原生 `BaseHTTPRequestHandler`。
- `api/routes.py` 负责 API route table。
- `api/handler.py` 负责请求解析、鉴权、路由调用、静态文件 fallback 和 server 启动。
- 业务 handler 按 Mixin 拆分在 `api/*_handlers.py`。
- JSON 响应格式统一为 `{code, status, message, data}`。

## Entry Points

- `media_importer/api/handler.py`
- `media_importer/api/routes.py`
- `media_importer/api/utils.py`
- `media_importer/api/task_handlers.py`
- `media_importer/api/config_handlers.py`
- `media_importer/api/provider_handlers.py`
- `media_importer/api/recycle_handlers.py`
- `media_importer/api/source_cleaner_handlers.py`

## Route Table

新增 API 端点优先注册到 `media_importer/api/routes.py`：

- `method`: HTTP method。
- `pattern`: 支持 `/api/tasks/{task_id}` 风格路径参数。
- `handler_name`: `APIHandler` 或 Mixin 上的方法名。
- `pass_query` / `pass_body`: 是否传入 query/body。
- `body_before_params`: 兼容 provider handler 的旧签名。
- `pass_self`: 兼容 source cleaner/recycle handler 的旧签名。

`handler.py` 不再扩展长 `if/elif` API 分支；未匹配 API 返回 404，非 API GET 继续走静态文件 fallback。

## Standards

见 [../standards/api.md](../standards/api.md)。
