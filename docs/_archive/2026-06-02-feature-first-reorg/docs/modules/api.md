# Module: API

## Code

- `media_importer/api/handler.py`
- `media_importer/api/routes.py`
- `media_importer/api/*_handlers.py`
- `media_importer/api/utils.py`
- `media_importer/api/static_server.py`

## Responsibility

提供 HTTP API、静态文件服务、鉴权、JSON 响应和 Web UI 后端接口。

## Extension Points

- 新增端点：增加 handler 方法并在 `api/routes.py` 注册路由。
- 动态路径使用 `{name}` 参数，例如 `/api/tasks/{task_id}`。

## Related Docs

- [../architecture/api.md](../architecture/api.md)
- [../standards/api.md](../standards/api.md)

## Tests

- API 集成测试
- `tests/test_api_routes.py`
- 配置页/任务页 Playwright 测试
