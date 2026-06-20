# Project Index

> 目的：把代码模块、文档、测试、变更影响范围连接起来。AI 修改项目时先查这里，再进入具体文档。

## Module Map

| 代码范围 | 职责 | 当前事实文档 | 架构文档 | 主要测试 |
|----------|------|----------|----------|----------|
| `media_importer/media_importer.py` | CLI 入口，启动 scan/serve/process | [architecture/overview.md](architecture/overview.md) | [architecture/overview.md](architecture/overview.md) | CLI/集成测试 |
| `media_importer/api/` | 原生 HTTP API、route table、静态文件、Mixin handlers | [architecture/api.md](architecture/api.md) | [architecture/api.md](architecture/api.md) | `tests/test_api_routes.py`、API 集成、UI 测试 |
| `media_importer/core/` | 配置、任务、DB、日志、指标和 legacy compatibility facade | [features/configuration.md](features/configuration.md), [features/tasks.md](features/tasks.md) | [architecture/configuration.md](architecture/configuration.md), [architecture/task-lifecycle.md](architecture/task-lifecycle.md) | core 单测 |
| `media_importer/core/db/` | SQLite connection/repo/migrations (真实实现,推荐 import 入口为 `media_importer.infrastructure.db` facade,见 Phase 5) | [architecture/data-flow.md](architecture/data-flow.md) | [architecture/data-flow.md](architecture/data-flow.md) | `tests/test_task_operations.py` |
| `media_importer/infrastructure/db/` | SQLite/repo infrastructure facade (Phase 5 推荐 import 入口) | [architecture/data-flow.md](architecture/data-flow.md) | [architecture/repository-structure.md](architecture/repository-structure.md) | `tests/test_feature_entrypoints.py`、`tests/test_architecture_guards.py` |
| `media_importer/features/configuration/` | 配置加载、迁移、校验、脱敏和 ConfigView 业务入口 | [features/configuration.md](features/configuration.md) | [architecture/configuration.md](architecture/configuration.md) | `tests/test_config_view.py`、`tests/test_config_consumers.py`、`tests/test_feature_entrypoints.py` |
| `media_importer/features/tasks/` | 任务管理、任务状态和生命周期业务入口 | [features/tasks.md](features/tasks.md) | [architecture/task-lifecycle.md](architecture/task-lifecycle.md) | `tests/test_task_context_lifecycle.py`、`tests/test_stage_lifecycle.py`、`tests/test_stage_db_migration.py`、`tests/test_task_operations.py`、`tests/test_feature_entrypoints.py` |
| `media_importer/features/recycle/` | 回收站移动、浏览、恢复、清理业务域 | [features/recycle.md](features/recycle.md) | [architecture/recycle.md](architecture/recycle.md) | `tests/test_feature_recycle.py`、`tests/test_recycle_safety.py` |
| `media_importer/core/recycle/` | 回收站 legacy import 入口，薄转发到 `features/recycle/` | [features/recycle.md](features/recycle.md) | [architecture/recycle.md](architecture/recycle.md) | `tests/test_feature_recycle.py` |
| `media_importer/features/import_flow/` | 入库流程业务域，持有 PipelineRunner、steps、确认（confirm/preview/reclassify）和 services 实现 | [features/import-flow.md](features/import-flow.md) | [architecture/import-pipeline.md](architecture/import-pipeline.md) | `tests/test_feature_import_flow.py`、`tests/test_import_flow_services.py`、`tests/test_classify_preview.py`、`tests/test_p0_confirm_workflow_fixes.py` |
| `media_importer/features/source_files/` | 源文件处理策略，持有成功入库、跳过、临时文件和伴生文件清理规则 | [features/source-files.md](features/source-files.md) | [architecture/storage-filesystem.md](architecture/storage-filesystem.md) | `tests/test_import_flow_services.py`、`tests/test_recycle_safety.py`、`tests/test_architecture_guards.py` |
| `media_importer/features/source_cleaning/` | 源目录清理业务域，持有清理器实现和记录入口 | [features/source-cleaning.md](features/source-cleaning.md) | [architecture/source-cleaner.md](architecture/source-cleaner.md) | `tests/test_feature_source_cleaning.py` |
| `media_importer/features/scraping/` | 刮削、LLM、三级匹配引擎、维度解析、提示词解析、场景策略、TMDB 和维度匹配业务入口 | [features/scraping.md](features/scraping.md), [features/ai-config.md](features/ai-config.md) | [architecture/scraping.md](architecture/scraping.md) | `tests/test_match_engine.py`、`tests/test_feature_entrypoints.py`、`tests/test_ai_config_runtime.py`、`tests/test_dimension_resolution.py`、`tests/test_match_engine_keyword_loop.py`、`tests/test_prompt_runtime.py`、`tests/test_ai_scene_strategy.py` |
| `media_importer/features/providers/` | 元数据 Provider 注册和工厂业务入口 | [features/providers.md](features/providers.md) | [architecture/scraping.md](architecture/scraping.md) | Provider/API 测试 |
| `media_importer/features/prompts/` | 提示词模板和默认提示词业务入口 | [features/prompts.md](features/prompts.md), [features/ai-config.md](features/ai-config.md) | [architecture/scraping.md](architecture/scraping.md) | `tests/test_prompt_defaults_unified.py` |
| `media_importer/scraper/` | 迁移期 compat re-export 集散点,保留一个版本周期(S-Phase 5);事实源已迁入 `features/scraping/` 与 `features/providers/` | [features/scraping.md](features/scraping.md) | [architecture/scraping.md](architecture/scraping.md) | `tests/test_architecture_guards.py::test_no_production_code_imports_scraper_package` |
| `media_importer/infrastructure/filesystem/` | 路径校验、权限检查、复制、安全移动/删除和指纹等基础文件系统能力 | [architecture/storage-filesystem.md](architecture/storage-filesystem.md) | [architecture/storage-filesystem.md](architecture/storage-filesystem.md) | `tests/test_recycle_safety.py`、`tests/test_architecture_guards.py` |
| `media_importer/storage/` | legacy compatibility wrappers for old file/scanner/classifier imports | [architecture/storage-filesystem.md](architecture/storage-filesystem.md) | [architecture/storage-filesystem.md](architecture/storage-filesystem.md) | 文件处理测试 |
| `media_importer/monitor/` | 文件监控、权限检查 | [architecture/notification-monitoring.md](architecture/notification-monitoring.md) | [architecture/notification-monitoring.md](architecture/notification-monitoring.md) | 权限/配置测试 |
| `media_importer/notify/` | Hermes 和 hook 通知 | [architecture/notification-monitoring.md](architecture/notification-monitoring.md) | [architecture/notification-monitoring.md](architecture/notification-monitoring.md) | 通知测试 |
| `media_importer/webui/` | 原生 HTML/CSS/JS 前端，后续单独重做 | [product/frontend-redesign-todo.md](product/frontend-redesign-todo.md), [product/frontend-information-architecture.md](product/frontend-information-architecture.md) | [architecture/api.md](architecture/api.md), [architecture/frontend-api-dependency-map.md](architecture/frontend-api-dependency-map.md) | Playwright UI 测试 |

## Change Impact Checklist

| 改动类型 | 必须同步 |
|----------|----------|
| 新增 API | `media_importer/api/routes.py`, `architecture/api.md`, `standards/api.md`, 本索引 |
| 新增配置项 | `architecture/configuration.md`, `standards/configuration.md`, 前端配置文档/测试 |
| 修改任务状态 | `features/tasks.md`, `architecture/task-lifecycle.md`, `testing/regression-matrix.md` |
| 修改文件删除/覆盖逻辑 | `features/source-files.md`, `standards/safety.md`, `architecture/storage-filesystem.md`, 回收站测试 |
| 新增 Provider | `features/providers.md`, `architecture/scraping.md`, Provider 测试 |
| **修改三级匹配/刮削字段** | **`standards/scrape-matching.md`, `standards/info-architecture.md`, `standards/ai-prompt-design.md`, `decisions/0007-information-responsibility-split.md`** |
| 修改前端页面 | `product/frontend-redesign-todo.md`, `product/frontend-information-architecture.md`, `architecture/frontend-api-dependency-map.md`, UI 测试 |
| 新增或迁移 feature | 对应 `docs/features/` 文档、feature smoke 测试、ADR/plan 状态 |
| 大架构重构 | 新增 ADR，更新 roadmap/plan 和相关架构文档 |
| 新增/变更需求 | `tracking/requirements-board.md`, `standards/requirement-management.md`, 相关 plan/ADR/测试链接 |

## Current Plans

- [去历史兼容化清理计划](plans/2026-06-13-refactor-remove-legacy-compatibility-plan.md) — 新产品模式下删除旧配置、旧 API、旧 UI、旧字段和旧 shim，收敛到当前事实源
- [去历史兼容化验收与回归测试计划](plans/2026-06-13-legacy-cleanup-acceptance-test-plan.md) — 自动化、API、Playwright 和组合场景验收，作为 scraper 整包迁移前置门槛
- [三级匹配策略重构](plans/2026-06-12-refactor-three-tier-matching-plan.md) — complete, 替代置信度公式体系，ADR-0005
- [AI 配置重设计完成计划](plans/2026-06-13-ai-config-redesign-completion-plan.md) — 后端契约修复完成，search_type 注入、ai_assist/ai_search 分离、media_type 兼容、confirm_reason 持久化、真实 dim_sources、二级关键词回搜、PromptResolver
- [Status+Stage 双层任务状态模型重构](plans/2026-06-09-task-status-stage-refactor.md) — Phase 1-4 开发完成，待验收
- [CANCELLED 任务取消能力](plans/2026-06-10-cancelled-task-feature.md) — 为排队任务增加取消能力，CANCELLED 状态完整实现
- [任务工作台交互与失败语义细化](plans/2026-06-10-task-workbench-interaction-refinement.md) — 卡片点击选中、详情编辑布局重构、孤儿 RUNNING 标记为 FAILED
- [任务卡片按钮矩阵收敛](plans/2026-06-10-task-card-button-matrix.md) — 统一"详情"为唯一详情入口；同步规范矩阵和编辑权限
- [AI-efficient architecture completion](plans/2026-06-03-refactor-ai-efficient-architecture-completion-plan.md) — complete, product full-flow acceptance deferred until frontend redesign
- [Feature-first 代码和文档结构重组](plans/2026-06-02-refactor-domain-first-code-and-docs-plan.md) — complete, pending user acceptance
- [AI 配置界面三区域改造+Phase 3](plans/2026-06-15-ai-config-restructure-plan.md) — complete, 627 tests pass, pending user acceptance
- [刮削信息职责拆分](plans/2026-06-16-scrape-info-responsibility-split-plan.md) — complete, 632 tests pass, 6 层信息架构 + 三级匹配行为契约落地, ADR-0007
- [字段传递断裂修复](plans/2026-06-16-fix-field-propagation-prompt.md) — complete, 正式流程 scrape.py 字段透传修复
- [待确认流程端到端整治](plans/2026-06-16-confirm-workflow-overhaul-plan.md) — P0 数据正确性 + P1 确认交互重构 + P2 决策路径优化，ADR-0007

## Behavior Standards (Fact Source)

修改刮削/匹配/信息展示相关代码前，必读：

| 标准 | 范围 |
|------|------|
| [standards/scrape-matching.md](standards/scrape-matching.md) | 三级匹配行为契约（决策树、字段定义、FAILED 状态） |
| [standards/info-architecture.md](standards/info-architecture.md) | 6 层信息职责模型、各视图密度分层、前后端字段契约 |
| [standards/ai-prompt-design.md](standards/ai-prompt-design.md) | Tier 2 AI 输入/输出 JSON 契约、is_valid 判定边界、提示词模板 |

## Archive

历史文档和已替代计划统一进入 [_archive/](./_archive/)。旧内容状态和替代入口见 [legacy.md](legacy.md)。
