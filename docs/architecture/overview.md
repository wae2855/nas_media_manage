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
| `media_importer/domains/` | 业务域入口 | 兼容 proof slice，当前 re-export 已稳定实现 |
| `media_importer/pipeline/` | 编排层 | 任务处理主流程、确认、重分类 |
| `media_importer/scraper/` | 业务能力 | LLM、Provider、置信度、维度映射 |
| `media_importer/storage/` | 业务能力 | 文件扫描、复制、移动、分类、去重、源目录清理 |
| `media_importer/core/` | 基础设施 | DB、配置、安全、回收站、日志、指标 |
| `media_importer/monitor/` | 周边能力 | 文件监控、权限检查 |
| `media_importer/notify/` | 周边能力 | Hermes 和 hook 通知 |
| `media_importer/webui/` | 前端 | 原生 HTML/CSS/JS |

## Architecture Direction

当前阶段的核心收益来自业务边界显式化，而不是目录名变化。

已落地的稳定边界：

- `TaskContext`
- `TaskLifecycle`
- pipeline services
- `ConfigView`
- API route table

目录级 `domains/` 迁移采用兼容层 + proof slice 策略，不做一次性大迁移。旧 public imports 保持可用，详见 ADR-0002。
当前 domain 入口：

- `media_importer/domains/import_flow/`: 持有 `TaskContext`、`PipelineRunner`、steps、确认/重分类和入库流程 services 实现，并 re-export `TaskLifecycle`。
- `media_importer/domains/source_cleaning/`: 持有源目录清理实现，旧 `storage/source_cleaner.py` 保持兼容。
- `media_importer/domains/recycle/`: 持有回收站实现，旧 `core/recycle/*` 和 `core/safety.py` 保持兼容。

详见：

- [AI 友好架构整体调整路线图](../plans/2026-05-31-refactor-ai-ready-architecture-roadmap.md)
- [业务边界显式化重构](../plans/2026-05-31-refactor-business-boundaries-plan.md)
- [业务域目录迁移可行性评审](../plans/2026-06-01-domain-directory-migration-feasibility.md)
