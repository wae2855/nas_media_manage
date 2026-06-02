# Project Index

> 目的：把代码模块、文档、测试、变更影响范围连接起来。AI 修改项目时先查这里，再进入具体文档。

## Module Map

| 代码范围 | 职责 | 模块文档 | 架构文档 | 主要测试 |
|----------|------|----------|----------|----------|
| `media_importer/media_importer.py` | CLI 入口，启动 scan/serve/process | [modules/app-entry.md](modules/app-entry.md) | [architecture/overview.md](architecture/overview.md) | CLI/集成测试 |
| `media_importer/api/` | 原生 HTTP API、route table、静态文件、Mixin handlers | [modules/api.md](modules/api.md) | [architecture/api.md](architecture/api.md) | `tests/test_api_routes.py`、API 集成、UI 测试 |
| `media_importer/core/` | 配置、任务、DB、日志、指标、安全基础设施 | [modules/core.md](modules/core.md) | [architecture/configuration.md](architecture/configuration.md) | core 单测 |
| `media_importer/core/db/` | SQLite connection/repo/migrations | [modules/core-db.md](modules/core-db.md) | [architecture/data-flow.md](architecture/data-flow.md) | `tests/test_sqlite_refactor.py` |
| `media_importer/domains/recycle/` | 回收站移动、浏览、恢复、清理业务域 | [modules/recycle-domain.md](modules/recycle-domain.md) | [architecture/recycle.md](architecture/recycle.md) | `tests/test_domain_recycle_compatibility.py`、`tests/test_recycle_and_safety.py` |
| `media_importer/core/recycle/` | 回收站旧 public import 兼容入口 | [modules/core-recycle.md](modules/core-recycle.md) | [architecture/recycle.md](architecture/recycle.md) | `tests/test_domain_recycle_compatibility.py` |
| `media_importer/domains/import_flow/` | 入库流程业务域，持有 PipelineRunner、steps、确认和 services 实现 | [modules/import-flow-domain.md](modules/import-flow-domain.md) | [architecture/import-pipeline.md](architecture/import-pipeline.md) | `tests/test_domain_import_flow_compatibility.py`、`tests/test_pipeline_services.py` |
| `media_importer/domains/source_cleaning/` | 源目录清理业务域，持有清理器实现和记录入口 | [modules/source-cleaning-domain.md](modules/source-cleaning-domain.md) | [architecture/source-cleaner.md](architecture/source-cleaner.md) | `tests/test_domain_source_cleaning_compatibility.py` |
| `media_importer/pipeline/` | 扫描后任务处理、确认、重分类、入库编排 | [modules/pipeline.md](modules/pipeline.md) | [architecture/import-pipeline.md](architecture/import-pipeline.md) | `tests/test_full_flow.py` |
| `media_importer/scraper/` | LLM 刮削、Provider、置信度、维度映射 | [modules/scraper.md](modules/scraper.md) | [architecture/scraping.md](architecture/scraping.md) | `tests/test_confidence_engine.py` |
| `media_importer/scraper/providers/` | 元数据源 Provider 抽象与 TMDB 实现 | [modules/scraper-providers.md](modules/scraper-providers.md) | [architecture/scraping.md](architecture/scraping.md) | Provider/API 测试 |
| `media_importer/storage/` | 扫描、复制、移动、去重、分类、源目录清理 | [modules/storage.md](modules/storage.md) | [architecture/storage-filesystem.md](architecture/storage-filesystem.md) | 文件处理测试 |
| `media_importer/monitor/` | 文件监控、权限检查 | [modules/monitor.md](modules/monitor.md) | [architecture/notification-monitoring.md](architecture/notification-monitoring.md) | 权限/配置测试 |
| `media_importer/notify/` | Hermes 和 hook 通知 | [modules/notify.md](modules/notify.md) | [architecture/notification-monitoring.md](architecture/notification-monitoring.md) | 通知测试 |
| `media_importer/webui/` | 原生 HTML/CSS/JS 前端 | [modules/webui.md](modules/webui.md) | [architecture/api.md](architecture/api.md) | Playwright UI 测试 |

## Change Impact Checklist

| 改动类型 | 必须同步 |
|----------|----------|
| 新增 API | `media_importer/api/routes.py`, `architecture/api.md`, `modules/api.md`, `standards/api.md`, 本索引 |
| 新增配置项 | `architecture/configuration.md`, `standards/configuration.md`, 前端配置文档/测试 |
| 修改任务状态 | `architecture/task-lifecycle.md`, `modules/pipeline.md`, `testing/regression-matrix.md` |
| 修改文件删除/覆盖逻辑 | `standards/safety.md`, `architecture/storage-filesystem.md`, 回收站测试 |
| 新增 Provider | `modules/scraper-providers.md`, `architecture/scraping.md`, Provider 测试 |
| 修改前端页面 | `modules/webui.md`, API 文档，UI 测试 |
| 新增业务域兼容入口 | 对应 domain 模块文档、兼容测试、ADR/plan 状态 |
| 大架构重构 | 新增 ADR，更新 roadmap/plan 和相关架构文档 |

## Active Plans

- [AI 友好架构整体调整路线图](plans/2026-05-31-refactor-ai-ready-architecture-roadmap.md)
- [业务边界显式化重构](plans/2026-05-31-refactor-business-boundaries-plan.md)
- [业务域目录迁移可行性评审](plans/2026-06-01-domain-directory-migration-feasibility.md)
- [deploy package 同步策略](plans/2026-06-02-deploy-package-sync-strategy.md)

## Archive

重构前文档备份在 [_archive/2026-05-31-pre-docs-reorg/](./_archive/2026-05-31-pre-docs-reorg/)。

旧中文目录仍保留在当前仓库中，但不作为当前事实入口；状态和替代入口见 [legacy.md](legacy.md)。
