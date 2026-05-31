# API Standards

## Response Format

统一 JSON 响应：

```json
{"code": 0, "status": "success", "message": "", "data": {}}
```

## Rules

- 新端点必须同步接口文档和 `docs/INDEX.md`。
- 需要鉴权的 `/api/` 端点必须遵守现有 API key 机制。
- handler 只处理请求/响应和调用业务服务。
- 不在 handler 中堆叠复杂业务策略。

## Current Routing

当前路由集中在 `media_importer/api/handler.py`。后续计划引入 route table。
