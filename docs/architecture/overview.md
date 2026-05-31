# Architecture Overview

当前架构以轻量 NAS 部署为核心约束：Python + SQLite + 原生 HTTP API + 原生 JS/CSS 前端。

## Layers

```text
CLI/API/Watcher
    |
Pipeline / API handlers
    |
scraper / storage / notify / monitor
    |
core: config / db / recycle / safety / logger / metrics
```

## Current Source Layout

| 目录 | 层级 | 说明 |
|------|------|------|
| `media_importer/api/` | 入口层 | HTTP 路由、Mixin handler、静态文件服务 |
| `media_importer/pipeline/` | 编排层 | 任务处理主流程、确认、重分类 |
| `media_importer/scraper/` | 业务能力 | LLM、Provider、置信度、维度映射 |
| `media_importer/storage/` | 业务能力 | 文件扫描、复制、移动、分类、去重、源目录清理 |
| `media_importer/core/` | 基础设施 | DB、配置、安全、回收站、日志、指标 |
| `media_importer/monitor/` | 周边能力 | 文件监控、权限检查 |
| `media_importer/notify/` | 周边能力 | Hermes 和 hook 通知 |
| `media_importer/webui/` | 前端 | 原生 HTML/CSS/JS |

## Architecture Direction

当前阶段不重写详细事实文档。后续代码重构目标是让 `pipeline` 从“承载大量业务细节”逐步转为“编排 TaskContext、TaskLifecycle 和业务 services”。

详见：

- [AI 友好架构整体调整路线图](../plans/2026-05-31-refactor-ai-ready-architecture-roadmap.md)
- [业务边界显式化重构](../plans/2026-05-31-refactor-business-boundaries-plan.md)
