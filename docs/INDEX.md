# Project Index

> 目的：把代码模块、文档、测试、变更影响范围连接起来。AI 修改项目时先查这里，再进入具体文档。

## Module Map

| 代码范围 | 职责 | 模块文档 | 架构文档 | 主要测试 |
|----------|------|----------|----------|----------|
| `media_importer/media_importer.py` | CLI 入口，启动 scan/serve/process | [modules/app-entry.md](modules/app-entry.md) | [architecture/overview.md](architecture/overview.md) | CLI/集成测试 |
| `media_importer/api/` | 原生 HTTP API、route table、静态文件、Mixin handlers | [modules/api.md](modules/api.md) | [architecture/api.md](architecture/api.md) | `tests/test_api_routes.py`、API 集成、UI 测试 |
| `media_importer/core/` | 配置、任务、DB、日志、指标、安全基础设施 | [modules/core.md](modules/core.md) | [architecture/configuration.md](architecture/configuration.md) | core 单测 |
| `media_importer/core/db/` | SQLite connection/repo/migrations | [modules/core-db.md](modules/core-db.md) | [architecture/data-flow.md](architecture/data-flow.md) | `tests/test_task_operations.py` |
| `media_importer/infrastructure/db/` | SQLite/repo infrastructure facade | [architecture/data-flow.md](architecture/data-flow.md) | [architecture/repository-structure.md](architecture/repository-structure.md) | `tests/test_feature_entrypoints.py` |
| `media_importer/features/configuration/` | 配置加载、迁移、校验、脱敏和 ConfigView 业务入口 | [features/configuration.md](features/configuration.md) | [architecture/configuration.md](architecture/configuration.md) | `tests/test_config_view.py`、`tests/test_config_consumers.py` |
| `media_importer/features/tasks/` | 任务管理、任务状态和生命周期业务入口 | [features/tasks.md](features/tasks.md) | [architecture/task-lifecycle.md](architecture/task-lifecycle.md) | `tests/test_task_context_lifecycle.py`、`tests/test_task_operations.py` |
| `media_importer/features/recycle/` | 回收站移动、浏览、恢复、清理业务域 | [features/recycle.md](features/recycle.md) | [architecture/recycle.md](architecture/recycle.md) | `tests/test_feature_recycle.py`、`tests/test_recycle_safety.py` |
| `media_importer/core/recycle/` | 回收站旧 public import 兼容入口 | [modules/core-recycle.md](modules/core-recycle.md) | [architecture/recycle.md](architecture/recycle.md) | `tests/test_feature_recycle.py` |
| `media_importer/features/import_flow/` | 入库流程业务域，持有 PipelineRunner、steps、确认和 services 实现 | [features/import-flow.md](features/import-flow.md) | [architecture/import-pipeline.md](architecture/import-pipeline.md) | `tests/test_feature_import_flow.py`、`tests/test_pipeline_services.py` |
| `media_importer/features/source_cleaning/` | 源目录清理业务域，持有清理器实现和记录入口 | [features/source-cleaning.md](features/source-cleaning.md) | [architecture/source-cleaner.md](architecture/source-cleaner.md) | `tests/test_feature_source_cleaning.py` |
| `media_importer/pipeline/` | 入库流程旧兼容入口；新实现和新入口优先使用 `features/import_flow/` | [modules/pipeline.md](modules/pipeline.md) | [architecture/import-pipeline.md](architecture/import-pipeline.md) | `tests/test_feature_import_flow.py`, `tests/test_feature_entrypoints.py` |
| `media_importer/features/scraping/` | 刮削、LLM、置信度和匹配业务入口 | [features/scraping.md](features/scraping.md) | [architecture/scraping.md](architecture/scraping.md) | `tests/test_confidence_engine.py` |
| `media_importer/features/providers/` | 元数据 Provider 注册和工厂业务入口 | [features/providers.md](features/providers.md) | [architecture/scraping.md](architecture/scraping.md) | Provider/API 测试 |
| `media_importer/features/prompts/` | 提示词模板和默认提示词业务入口 | [features/prompts.md](features/prompts.md) | [architecture/scraping.md](architecture/scraping.md) | Prompt tests |
| `media_importer/scraper/` | LLM 刮削、Provider、置信度、维度映射实现位置 | [features/scraping.md](features/scraping.md) | [architecture/scraping.md](architecture/scraping.md) | `tests/test_confidence_engine.py` |
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
| 新增或迁移 feature | 对应 `docs/features/` 文档、feature smoke 测试、ADR/plan 状态 |
| 大架构重构 | 新增 ADR，更新 roadmap/plan 和相关架构文档 |

## Active Plans

- [Feature-first 代码和文档结构重组](plans/2026-06-02-refactor-domain-first-code-and-docs-plan.md)

## Archive

历史文档和已替代计划统一进入 [_archive/](./_archive/)。旧内容状态和替代入口见 [legacy.md](legacy.md)。
