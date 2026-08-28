# Architecture Overview

当前架构以轻量 NAS 部署为核心约束：Python + SQLite + 原生 HTTP API + 原生 JS/CSS 前端。

## Target Layers

```text
app entrypoints: CLI / API / watcher
    |
features: import_flow / scraping / configuration / tasks / source_cleaning / recycle / providers / prompts
    |
infrastructure: sqlite / filesystem / provider clients / llm adapters / logger / metrics
    |
shared: tiny cross-feature constants and helpers
```

## Current Source Layout

| 目录 | 层级 | 说明 |
|------|------|------|
| `media_importer/api/` | 入口层 | HTTP 路由、Mixin handler、静态文件服务 |
| `media_importer/features/` | 业务事实源 | feature-first 业务能力入口 |
| `media_importer/scraper/` | 待迁移业务能力 | LLM、Provider、匹配引擎、维度映射，目标是 `features/scraping` 与 `features/providers` |
| `media_importer/infrastructure/` | 基础能力 | 文件系统（复制/安全删除/指纹）与 DB facade；`storage/` 兼容层已删除 |
| `media_importer/core/` | 待拆分基础设施 | DB、配置、任务、安全、日志、指标，目标是 feature-owned repos + infrastructure |
| `media_importer/monitor/` | 待迁移周边能力 | 文件监控、权限检查 |
| `media_importer/notify/` | 待迁移周边能力 | Hermes 和 hook 通知 |
| `media_importer/webui/` | 前端 | 原生 HTML/CSS/JS |

## Architecture Direction

当前阶段采用 ADR-0004 的 feature-first 激进重组。项目未上线，不以旧 import、旧 patch 路径、旧测试脚本和历史数据兼容为主要约束。

已落地的稳定边界：

- `features/import_flow/`: `TaskContext`、`PipelineRunner`、steps、确认/重分类和入库流程 services。
- `features/source_cleaning/`: 源目录清理实现。
- `features/recycle/`: 回收站移动、浏览、恢复、清理实现。
- `ConfigView`
- API route table

迁移规则：

- 新业务入口优先放入 `features/`。
- API/CLI 只做请求解析、响应包装和用例调用，不承载复杂业务策略。
- 旧技术目录如果只是转发到 feature，可在测试和文档完成后归档；旧 `pipeline/` 包装层已归档。
- 当前事实文档不得引用归档内容作为依据。

详见 [ADR-0004](../decisions/0004-feature-first-architecture-restructure.md)。
