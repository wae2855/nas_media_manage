# API Standards

## Response Format

统一 JSON 响应：

```json
{"code": 0, "status": "success", "message": "", "data": {}}
```

## Rules

- 新端点必须注册到 `media_importer/api/routes.py`，并同步接口文档和 `docs/ai-map.md`。
- 需要鉴权的 `/api/` 端点必须遵守现有 API key 机制。
- handler 只处理请求/响应和调用业务服务。
- 不在 handler 中堆叠复杂业务策略。

## Sensitive Fields

以下字段在 API 返回前必须脱敏为 `***`：

- `api_key`（所有配置段）
- 任何以 `_key`、`_secret`、`_token` 结尾的字段

## Config Sections

| 配置段 | 说明 | 对应 ConfigView |
|--------|------|-----------------|
| `ai_assist` | AI 辅助模型配置（标题清洗、匹配辅助、维度映射） | `AiAssistConfig` |
| `ai_search` | AI 联网搜索增强配置（维度补全） | `AiSearchConfig` |
| `llm` | 旧 LLM 配置（向后兼容，新配置优先） | `LLMConfig` |

## Prompt Defaults

- `GET /api/config/prompt-defaults` 返回各场景默认提示词
- 用户配置提示词为空字符串时，运行时使用默认值
- "恢复默认" 操作将提示词重置为空字符串

## Routing

API 路由集中在 `media_importer/api/routes.py`。

新增端点流程：

1. 在对应 `api/*_handlers.py` 增加 handler 方法。
2. 在 `api/routes.py` 注册 method、pattern、handler_name。
3. 在 `tests/test_api_routes.py` 增加匹配测试。
4. 更新接口文档、前端调用和必要的集成测试。
