# API Standards

## Response Format

统一 JSON 响应：

```json
{"code": 0, "status": "success", "message": "", "data": {}}
```

## Rules

- 新端点必须注册到 `media_importer/api/routes.py`，并同步接口文档和 `docs/INDEX.md`。
- 需要鉴权的 `/api/` 端点必须遵守现有 API key 机制。
- handler 只处理请求/响应和调用业务服务。
- 不在 handler 中堆叠复杂业务策略。

## Routing

API 路由集中在 `media_importer/api/routes.py`。

新增端点流程：

1. 在对应 `api/*_handlers.py` 增加 handler 方法。
2. 在 `api/routes.py` 注册 method、pattern、handler_name。
3. 在 `tests/test_api_routes.py` 增加匹配测试。
4. 更新接口文档、前端调用和必要的集成测试。
