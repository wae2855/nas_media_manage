# AI Navigation Map

> AI 修改项目前先读本文件。目标是快速定位代码、文档、测试和同步范围。

## Common Tasks

| 任务 | 先读 | 主要代码 | 必跑/优先测试 | 文档同步 |
|------|------|----------|---------------|----------|
| 启动任意需求 | [standards/requirement-management.md](standards/requirement-management.md), [tracking/requirements-board.md](../docs/tracking/requirements-board.md) | — | — | 注册需求到 Board，检查冲突 |
| 新增 API 端点 | [architecture/api.md](architecture/api.md), [standards/api.md](standards/api.md) | `media_importer/api/handler.py`, 对应 `*_handlers.py` | API 集成/前端相关测试 | `docs/INDEX.md`, API 文档 |
| 新增配置项 | [features/configuration.md](features/configuration.md), [architecture/configuration.md](architecture/configuration.md), [standards/configuration.md](standards/configuration.md) | `features/configuration/`, `features/configuration/application_service.py`, `core/config_loader.py`, `core/config_migrations.py`, `core/config_validator.py`, `api/config_handlers.py`, `webui/js/config.js` | 配置测试、UI 配置测试 | 配置 feature、架构和索引 |
| 修改任务状态 | [features/tasks.md](features/tasks.md), [architecture/task-lifecycle.md](architecture/task-lifecycle.md) | `features/tasks/`, `core/db/constants.py`, `core/task_manager.py`, `features/import_flow/`, `api/task_handlers.py`, `webui/js/tasks.js` | 任务、import-flow、回归测试 | lifecycle 文档、测试矩阵 |
| 修改入库流程 | [features/import-flow.md](features/import-flow.md), [architecture/import-pipeline.md](architecture/import-pipeline.md) | `features/import_flow/runner.py`, `features/import_flow/scan_service.py`, `features/import_flow/steps/`, `features/import_flow/services/`, `features/import_flow/services/classification_rules.py`, `features/import_flow/services/dedup_rules.py`, `features/import_flow/services/naming.py`, `features/import_flow/services/file_operations.py`, `features/source_files/`, `infrastructure/filesystem/` | import-flow services/feature smoke/recycle | import-flow/source-files 文档 |
| 修改刮削逻辑 | [features/scraping.md](features/scraping.md), [architecture/scraping.md](architecture/scraping.md) | `features/scraping/metadata_scraper.py`, `features/scraping/match_engine.py`, `features/scraping/match_models.py`, `features/scraping/dimension_manager.py`, `features/scraping/dimensions_service.py`, `features/scraping/llm_scraper.py`, `features/scraping/title_matcher.py`, `features/scraping/filename_cleaner.py`, `features/scraping/llm_match_assist.py`, `features/scraping/llm_client.py`, `features/scraping/metadata_scrape_flow.py`, `features/providers/` | match_engine/scrape 测试 | scraping 文档 |
| 新增 Provider | [features/providers.md](features/providers.md) | `features/providers/` | Provider/API 测试 | ADR 如影响架构 |
| 修改提示词 | [features/prompts.md](features/prompts.md), [features/scraping.md](features/scraping.md) | `features/prompts/application_service.py`, `features/prompts/prompt_builder.py`, `features/scraping/llm_scraper.py`, prompt/provider API handlers | prompt/scrape 测试 | prompts 文档 |
| 修改文件移动/删除 | [features/source-files.md](features/source-files.md), [features/import-flow.md](features/import-flow.md), [features/recycle.md](features/recycle.md), [standards/safety.md](standards/safety.md) | `features/source_files/`, `features/import_flow/services/file_operations.py`, `features/recycle/`, `infrastructure/filesystem/`, `core/safety.py` facade, `storage/file_mover.py` wrapper | recycle/safety/e2e/feature smoke | source-files/import-flow/recycle 文档和回归矩阵 |
| 修改源目录清理 | [features/source-cleaning.md](features/source-cleaning.md), [architecture/source-cleaner.md](architecture/source-cleaner.md) | `features/source_cleaning/`, `features/source_cleaning/application_service.py`, `api/source_cleaner_handlers.py`, `webui/js/config.js` | source cleaner/recycle/config/feature smoke | source-cleaning 文档 |
| 修改前端 | [product/frontend-redesign-todo.md](product/frontend-redesign-todo.md), [product/frontend-information-architecture.md](product/frontend-information-architecture.md), [architecture/frontend-api-dependency-map.md](architecture/frontend-api-dependency-map.md), [architecture/api.md](architecture/api.md) | `media_importer/webui/index.html`, `media_importer/webui/js/`, `media_importer/webui/css/` | Playwright 或相关 UI 测试 | API/产品/测试文档 |
| 发布 fnOS package | [architecture/deployment-fnos.md](architecture/deployment-fnos.md), [workflows/release.md](workflows/release.md), [decisions/0003-deploy-package-generation-strategy.md](decisions/0003-deploy-package-generation-strategy.md) | `deploy/build_fpk.sh`, root `media_importer/` | release smoke/build checks | deployment 文档 |

## Decision Flow

1. 判断任务类型，查上表。
2. 阅读对应模块文档和标准文档。
3. 检查是否需要 proposal、plan 或 ADR。
4. 修改代码。
5. 按影响范围运行测试。
6. 更新 `docs/INDEX.md` 和相关模块/架构文档。
7. 在最终说明中报告测试结果和文档更新。

## Legacy Documents

旧中文目录、历史方案和被替代计划已移入归档目录，不是当前事实入口。AI 只有在任务明确要求追溯历史或迁移 legacy 内容时才读取 archive。

当前架构事实优先看：

- `docs/architecture/`
- `docs/features/`
- `docs/standards/`
- `docs/workflows/`
- `docs/decisions/`
- `docs/testing/`

## Hard Rules

- 不直接删除或覆盖影视文件，必须走回收站安全规则。
- 不把 `deploy/` 当作开发源；是否同步 deploy 需要单独决策。
- `deploy/nas-media-importer/` 是生成 package workspace；应用代码事实以根目录 `media_importer/` 为准。
- `features/` 是当前业务事实源；旧 public imports 只作为临时 wrapper 或待归档对象。
- 不在架构事实文档中写未实施设想，未实施内容放 proposals/plans。
- 不把 legacy 中文文档当作当前事实来源；如发现冲突，以新文档和代码为准，并记录待迁移项。
- 大重构先有 plan，架构决策要写 ADR。
