# AI Navigation Map

> AI 修改项目前先读本文件。目标是快速定位代码、文档、测试和同步范围。

## Common Tasks

| 任务 | 先读 | 主要代码 | 必跑/优先测试 | 文档同步 |
|------|------|----------|---------------|----------|
| 新增 API 端点 | [architecture/api.md](architecture/api.md), [standards/api.md](standards/api.md) | `media_importer/api/handler.py`, 对应 `*_handlers.py` | API 集成/前端相关测试 | `docs/INDEX.md`, API 文档 |
| 新增配置项 | [architecture/configuration.md](architecture/configuration.md), [standards/configuration.md](standards/configuration.md) | `core/config_loader.py`, `core/config_migrations.py`, `core/config_validator.py`, `api/config_handlers.py`, `webui/js/config.js` | 配置测试、UI 配置测试 | 配置架构和索引 |
| 修改任务状态 | [architecture/task-lifecycle.md](architecture/task-lifecycle.md) | `core/db/constants.py`, `core/task_manager.py`, `pipeline/`, `api/task_handlers.py`, `webui/js/tasks.js` | 任务、pipeline、回归测试 | lifecycle 文档、测试矩阵 |
| 修改 pipeline 流程 | [modules/pipeline.md](modules/pipeline.md), [architecture/import-pipeline.md](architecture/import-pipeline.md) | `pipeline/runner.py`, `steps_file.py`, `steps_scrape.py`, `confirm.py` | full_flow/e2e/recycle | pipeline 文档 |
| 修改刮削逻辑 | [modules/scraper.md](modules/scraper.md), [architecture/scraping.md](architecture/scraping.md) | `scraper/metadata_scraper.py`, `llm_scraper.py`, `confidence_engine.py` | confidence/scrape 测试 | scraper 文档 |
| 新增 Provider | [modules/scraper-providers.md](modules/scraper-providers.md) | `scraper/providers/` | Provider/API 测试 | ADR 如影响架构 |
| 修改文件移动/删除 | [standards/safety.md](standards/safety.md) | `storage/file_mover.py`, `core/recycle/`, `core/safety.py` | recycle/safety/e2e | 安全文档和回归矩阵 |
| 修改源目录清理 | [architecture/source-cleaner.md](architecture/source-cleaner.md) | `storage/source_cleaner.py`, `api/source_cleaner_handlers.py`, `webui/js/config.js` | source cleaner/recycle/config 测试 | source-cleaner 文档 |
| 修改前端 | [modules/webui.md](modules/webui.md) | `webui/index.html`, `webui/js/`, `webui/css/` | Playwright 或相关 UI 测试 | API/模块文档 |

## Decision Flow

1. 判断任务类型，查上表。
2. 阅读对应模块文档和标准文档。
3. 检查是否需要 proposal、plan 或 ADR。
4. 修改代码。
5. 按影响范围运行测试。
6. 更新 `docs/INDEX.md` 和相关模块/架构文档。
7. 在最终说明中报告测试结果和文档更新。

## Hard Rules

- 不直接删除或覆盖影视文件，必须走回收站安全规则。
- 不把 `deploy/` 当作开发源；是否同步 deploy 需要单独决策。
- 不在架构事实文档中写未实施设想，未实施内容放 proposals/plans。
- 大重构先有 plan，架构决策要写 ADR。
