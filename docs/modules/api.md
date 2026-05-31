# Module: API

## Code

- `media_importer/api/handler.py`
- `media_importer/api/*_handlers.py`
- `media_importer/api/utils.py`
- `media_importer/api/static_server.py`

## Responsibility

提供 HTTP API、静态文件服务、鉴权、JSON 响应和 Web UI 后端接口。

## Extension Points

- 新增端点：增加 handler 方法并注册路由。
- 后续 route table 落地后，新增端点应通过 `api/routes.py` 注册。

## Related Docs

- [../architecture/api.md](../architecture/api.md)
- [../standards/api.md](../standards/api.md)

## Tests

- API 集成测试
- 配置页/任务页 Playwright 测试
