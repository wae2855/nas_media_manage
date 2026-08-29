# AI Navigation Map

> AI 修改项目前先读本文件（唯一导航入口）。目标：任务 → 代码 → 测试 → 文档同步，两跳定位。
> 原 `docs/INDEX.md` 已合并进本文件并删除。

## 1. Common Tasks（任务导航）

| 任务 | 先读 | 主要代码 | 必跑/优先测试 | 文档同步 |
|------|------|----------|---------------|----------|
| 启动任意需求 | [standards/requirement-management.md](standards/requirement-management.md), [tracking/requirements-board.md](tracking/requirements-board.md) | — | — | 注册需求到 Board，检查冲突 |
| 新增 API 端点 | [architecture/api.md](architecture/api.md), [standards/api.md](standards/api.md) | `media_importer/api/handler.py`, 对应 `*_handlers.py` | API 集成/前端相关测试 | 本文件 §2、API 文档 |
| 新增配置项 | [features/configuration.md](features/configuration.md), [architecture/configuration.md](architecture/configuration.md), [standards/configuration.md](standards/configuration.md) | `features/configuration/`, `core/config_loader.py`, `core/config_validator.py`, `api/config_handlers.py`, `webui/js/cinema-config.js` | 配置测试、UI 配置测试 | 配置 feature、架构文档 |
| 修改后端架构/任务状态 | [standards/backend.md](standards/backend.md), [features/tasks.md](features/tasks.md), [architecture/task-lifecycle.md](architecture/task-lifecycle.md) | **`features/tasks/transitions.py`（转换表唯一事实源）**, task_lifecycle_compat（兼容层）, `core/task_manager.py`, `core/db/task_repo.compare_and_update_task`（CAS）, `features/import_flow/` | [test_task_transitions](../tests/test_task_transitions.py), [test_task_concurrency_and_resume](../tests/test_task_concurrency_and_resume.py), [test_file_flow_matrix](../tests/test_file_flow_matrix.py) | lifecycle 文档、[testing/file-flow-matrix.md](testing/file-flow-matrix.md) |
| 修改入库流程 | [features/import-flow.md](features/import-flow.md), [architecture/import-pipeline.md](architecture/import-pipeline.md) | `features/import_flow/`（runner/steps/services）, `features/source_files/`, `infrastructure/filesystem/` | import-flow services/feature smoke/recycle | import-flow/source-files 文档 |
| 修改刮削逻辑 | [features/scraping.md](features/scraping.md), [standards/scrape-matching.md](standards/scrape-matching.md) | `features/scraping/`, `features/providers/` | match_engine/scrape 测试 | scraping 文档 |
| 新增 Provider | [features/providers.md](features/providers.md) | `features/providers/` | Provider/API 测试 | ADR 如影响架构 |
| 修改清理器提示词 | [standards/ai-prompt-design.md](standards/ai-prompt-design.md) | `features/source_cleaning/prompts.py`, `infrastructure/llm/` | source cleaning 测试 | ai-prompt-design 标准 |
| 修改文件移动/删除 | [features/source-files.md](features/source-files.md), [features/recycle.md](features/recycle.md), [standards/safety.md](standards/safety.md) | `features/source_files/`, `features/import_flow/services/file_operations.py`, `features/recycle/`, `infrastructure/filesystem/` | recycle/safety/e2e/feature smoke | source-files/recycle 文档和回归矩阵 |
| 修改源目录清理 | [features/source-cleaning.md](features/source-cleaning.md), [architecture/source-cleaner.md](architecture/source-cleaner.md) | `features/source_cleaning/`, `api/source_cleaner_handlers.py`, `webui/js/cinema-config.js` | source cleaner/recycle/config/feature smoke | source-cleaning 文档 |
| 修改前端 | [standards/frontend.md](standards/frontend.md), [architecture/api.md](architecture/api.md) | `media_importer/webui/` | Playwright 或相关 UI 测试 | API/产品/测试文档 |
| 发布 fnOS package | [architecture/deployment-fnos.md](architecture/deployment-fnos.md), [workflows/release.md](workflows/release.md), [decisions/0003-deploy-package-generation-strategy.md](decisions/0003-deploy-package-generation-strategy.md), [decisions/0011-fnos-install-runtime-config-ownership.md](decisions/0011-fnos-install-runtime-config-ownership.md) | `deploy/build_fpk.sh`, `deploy/fnos_config.py`, `scripts/validate_fpk.py`, 根 `media_importer/` | `tests/test_fnos_packaging.py` + FPK 内容验证 | deployment / release / testing 文档 |

## 2. Module Map（模块 → 文档 → 测试）

| 代码范围 | 职责 | 事实文档 | 主要测试 |
|----------|------|----------|----------|
| `media_importer/media_importer.py` | CLI 入口（scan/serve/process） | [architecture/overview.md](architecture/overview.md) | CLI/集成测试 |
| `media_importer/api/` | 原生 HTTP API、route table、静态文件 | [architecture/api.md](architecture/api.md) | `tests/test_api_routes.py`、API 集成、UI 测试 |
| `media_importer/core/` | 配置、任务、DB、日志、指标（legacy facade 迁移期） | [features/configuration.md](features/configuration.md), [features/tasks.md](features/tasks.md) | core 单测 |
| `media_importer/core/db/` | SQLite 真实实现（推荐 import 入口 `media_importer.infrastructure.db`） | [architecture/data-flow.md](architecture/data-flow.md) | `tests/test_task_operations.py` |
| `media_importer/infrastructure/` | DB facade、filesystem 基础能力（路径校验/复制/安全删除/指纹） | [architecture/storage-filesystem.md](architecture/storage-filesystem.md) | `tests/test_recycle_safety.py`, `tests/test_architecture_guards.py` |
| `media_importer/features/configuration/` | 配置加载、迁移、校验、脱敏、片库根边界、开场检查 | [features/configuration.md](features/configuration.md) | `tests/test_config_view.py`、`tests/test_library_root_boundary.py`、`tests/test_startup_readiness.py` |
| `media_importer/features/source_files/source_units.py` | 来源单元识别、快照与整组回收门禁 | [features/source-files.md](features/source-files.md), [decisions/0014-source-unit-lifecycle.md](decisions/0014-source-unit-lifecycle.md) | `tests/test_source_unit_lifecycle.py` |
| `media_importer/features/tasks/` | 任务管理、状态、生命周期 | [features/tasks.md](features/tasks.md) | `tests/test_task_*.py` 系列 |
| `media_importer/features/recycle/` | 回收站移动/浏览/恢复/清理 | [features/recycle.md](features/recycle.md) | `tests/test_recycle_safety.py`, `tests/test_recycle_list_payload.py` |
| `media_importer/features/import_flow/` | 入库流程：runner、steps、confirm、services | [features/import-flow.md](features/import-flow.md) | `tests/test_feature_import_flow.py` 等 |
| `media_importer/features/source_files/` | 源文件处理策略（成功/跳过/伴生清理） | [features/source-files.md](features/source-files.md) | `tests/test_import_flow_services.py` 等 |
| `media_importer/features/source_cleaning/` | 源目录清理业务域 | [features/source-cleaning.md](features/source-cleaning.md) | `tests/test_feature_source_cleaning.py` |
| `media_importer/features/scraping/` | 刮削、两级匹配、维度规则映射 | [features/scraping.md](features/scraping.md) | `tests/test_match_engine.py`, `tests/test_scrape_provider_first_e2e.py` 等 |
| `media_importer/features/providers/` | 元数据 Provider 注册和工厂 | [features/providers.md](features/providers.md) | Provider/API 测试 |
| `media_importer/monitor/` | 文件监控、权限检查 | [architecture/notification-monitoring.md](architecture/notification-monitoring.md) | 权限/配置测试 |
| `media_importer/notify/` | Hermes 和 hook 通知 | [architecture/notification-monitoring.md](architecture/notification-monitoring.md) | 通知测试 |
| `media_importer/webui/` | 原生 HTML/CSS/JS 前端（后续重做，待重估） | [product/frontend-information-architecture.md](product/frontend-information-architecture.md) | Playwright UI 测试 |

全量文件清单用命令获取：`find media_importer -name "*.py"`、`ls tests/`。文档只维护职责映射。

## 3. Change Impact Matrix（变更影响矩阵·唯一事实源）

| 改动类型 | 必须同步 |
|----------|----------|
| 新增 API | `media_importer/api/routes.py`, `architecture/api.md`, `standards/api.md`, 本文件 §2 |
| 新增配置项 | `architecture/configuration.md`, `standards/configuration.md`, 前端配置文档/测试 |
| 修改任务状态 | `features/tasks.md`, `architecture/task-lifecycle.md`, `testing/regression-matrix.md` |
| 修改文件删除/覆盖逻辑 | `features/source-files.md`, `standards/safety.md`, `architecture/storage-filesystem.md`, 回收站测试 |
| 新增 Provider | `features/providers.md`, `architecture/scraping.md`, Provider 测试 |
| 修改三级匹配/刮削字段 | `standards/scrape-matching.md`, `standards/info-architecture.md`, `standards/ai-prompt-design.md`, [decisions/0007](decisions/0007-information-responsibility-split.md) |
| 修改前端页面 | `product/frontend-information-architecture.md`, UI 测试 |
| 新增或迁移 feature | 对应 `docs/features/` 文档、feature smoke 测试、ADR/plan 状态 |
| 大架构重构 | 新增 ADR，更新相关架构文档 |
| 新增/变更需求 | `tracking/requirements-board.md`, [standards/requirement-management.md](standards/requirement-management.md) |

## 4. Behavior Standards（行为契约，改刮削/匹配前必读）

| 标准 | 范围 |
|------|------|
| [standards/scrape-matching.md](standards/scrape-matching.md) | 三级匹配行为契约（决策树、字段定义、FAILED 状态） |
| [standards/info-architecture.md](standards/info-architecture.md) | 6 层信息职责模型、视图密度分层、前后端字段契约 |
| [standards/ai-prompt-design.md](standards/ai-prompt-design.md) | Tier 2 AI 输入/输出 JSON 契约、is_valid 判定边界、提示词模板 |

## 5. Active Plans（活跃计划）

- [存储安全与配置界面简化重构](plans/2026-08-28-storage-safe-configuration-redesign-plan.md)
- [配置依赖、来源单元与开场检查](plans/2026-08-28-feat-configuration-dependency-and-readiness-plan.md)

简洁化路线图 Phase 0-4 已完成归档（`_archive/2026-08-27-simplification-complete/`），REQ-000003/000004 已关闭。

现行依据文档：
- 前端：[standards/frontend.md](standards/frontend.md)
- 后端：[standards/backend.md](standards/backend.md)
- 刮削契约：[standards/scrape-matching.md](standards/scrape-matching.md)
- 架构决策：[decisions/](decisions/)（ADR-0010 为刮削边界现行依据）

## 6. Decision Flow（AI 执行流程）

1. 判断任务类型，查 §1。
2. 阅读对应模块文档和标准文档。
3. 按 [workflows/ai-agent-workflow.md](workflows/ai-agent-workflow.md) 和轻量开发流程（[workflows/feature-development.md](workflows/feature-development.md)）判断是否需要 proposal/plan/ADR。
4. 修改代码。
5. 按影响范围运行测试（§3 + [testing/regression-matrix.md](testing/regression-matrix.md)）。
6. 更新本文件和相关模块/架构文档。
7. 文档变更跑 `python scripts/check_docs.py`。
8. 在最终说明中报告测试结果和文档更新。

## 7. Hard Rules

- 不直接删除或覆盖影视文件，必须走回收站安全规则（[standards/safety.md](standards/safety.md)）。
- 不把 `deploy/` 当作开发源；`deploy/nas-media-importer/` 是生成 package workspace，发布走 `deploy/build_fpk.sh` 从根源码重建。
- `features/` 是当前业务事实源；旧兼容层（`storage/`、`core/recycle/`、`scraper/`、`core/safety.py`）均已删除，guard 拦截复活。
- 不在架构事实文档中写未实施设想；未实施内容放 proposals/plans。
- 归档内容不作当前事实；冲突以新文档和代码为准。
- 大重构先有 plan，架构决策写 ADR。
- 停摆恢复期（2026-08）：历史待办一律先查 [tracking/backlog-reevaluation.md](tracking/backlog-reevaluation.md) 重估状态，不得直接执行。
