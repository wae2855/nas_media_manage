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

- `GET /api/health` 的 `data.version` 是当前运行服务的真实版本，来自包内 `VERSION`；前端不得从静态文件或构建猜测版本。
- `GET /api/config/startup-readiness` 必须只读，并绑定当前配置 revision。
- Provider 维度映射必须通过专用合同读写：`GET/PUT /api/dimensions/{name}/mappings/{provider}`。PUT 必须携带 GET 返回的 `content_hash`，哈希过期返回 409，禁止后写静默覆盖前写。
- `POST /api/dimensions/{name}/mappings/{provider}/preview` 只执行纯映射试算，不保存、不刮削外网、不触发入库。`GET /api/providers/{type}/dimension-capabilities` 只返回标准字段和数据形态，不返回密钥。
- 配置检查的自动运行项必须同时核对 `automatic_allowed` 和当前 watcher 线程；配置中 `enabled=true` 不能单独构成 PASS。
- `GET /api/watcher/status` 必须区分配置意图与实际运行状态，并返回服务端计算的阻断原因。
- `GET /api/config/fnos-folders` 只返回授权目录能力和路径；禁止返回、记录或持久化 `TRIM_API_TOKEN`。非 fnOS 环境用 `available=false` 表达降级，不用 500 冒充应用故障。
- 外部能力仅在业务模式需要时探测；未启用的 LLM 返回 `SKIPPED`，不能误报失败。
- 任一关键目录、TMDB 或必需 LLM 为 `BLOCKED` 时，总状态必须为 `BLOCKED`。
- `GET /api/dashboard/summary` 必须从任务业务事实聚合状态、今日入库、最近活动和最近影片；不得用原始日志或图片文件时间替代业务时间。
- 首页摘要不得返回服务器绝对路径；最近活动最多 5 条，最近影片最多 12 部。
- 目标片库冲突必须以结构化 `dedup_result` 返回；`POST /tasks/{id}/confirm` 只接受受限 `conflict_action`，未决冲突不得由普通确认或 `confirm-all` 绕过。
- 手动刮削搜索最多返回 20 条，类型和语言必须显式校验；候选必须用 Provider ID 通过 `scrape-apply` 应用完整详情。应用候选只刷新资料/维度/入库预览，禁止在同一请求内自动确认或启动文件处理。
- 电视剧关联套用必须先提供可取消选择的预览，并在 `scrape-apply` 时服务端重新验证 `related_task_ids`；前端传入 ID 不能绕过同目录、同剧名、唯一季集号、状态和冲突门禁。逐任务失败必须结构化返回，不能伪装为全部成功。
- 通用任务删除和重命名不得操作 `file_location=import`；客户端即使提交文件动作也必须由服务端返回 400，不能只依赖前端隐藏按钮。
- `POST /api/tasks/{id}/dispose` 的 `source_disposition` 仅允许 `keep|local_recycle|permanent_delete`。运行中返回 202 表示等待安全停止；视频文件包提交后返回 409 并继续安全收尾。
- `POST /api/tasks/{id}/delete` 只删除已结束任务的记录且不得产生文件副作用。活动任务返回 400 并引导先调用 dispose。
- 冲突确认选择 `keep_existing` 时可附带 `source_disposition`；其他冲突动作携带该字段必须返回 400。
- 兜底入库确认必须显式提交 `fallback_acknowledged=true`；`confirm-all` 不得代替用户接受兜底。`POST /api/tasks/{id}/reorganize` 只能从已完成且仍标记 `FALLBACK_PENDING` 的父任务幂等创建关联新任务，禁止修改或复活父任务。

新增端点流程：

1. 在对应 `api/*_handlers.py` 增加 handler 方法。
2. 在 `api/routes.py` 注册 method、pattern、handler_name。
3. 在 `tests/test_api_routes.py` 增加匹配测试。
4. 更新接口文档、前端调用和必要的集成测试。
