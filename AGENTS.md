# 影音库AI智能整理 — AI Agent 入口

本文件只保留最高优先级信息：环境命令、安全红线、导航路由。完整规范见 `docs/standards/`，流程见 `docs/workflows/`。

## 1. Start Here（导航路由）

| 目标 | 入口 |
|------|------|
| **任务→代码→测试→文档映射（先查这里）** | [docs/ai-map.md](docs/ai-map.md) |
| 文档总入口 | [docs/README.md](docs/README.md) |
| 前端/后端/代码规范 | [docs/standards/frontend.md](docs/standards/frontend.md), [docs/standards/backend.md](docs/standards/backend.md), [docs/standards/](docs/standards/) |
| 开发/重构/发布流程 | [docs/workflows/](docs/workflows/) |
| 需求看板与待办重估 | [docs/tracking/requirements-board.md](docs/tracking/requirements-board.md), [docs/tracking/backlog-reevaluation.md](docs/tracking/backlog-reevaluation.md) |
| 架构决策（ADR） | [docs/decisions/](docs/decisions/) |
| 测试策略与回归矩阵 | [docs/testing/](docs/testing/) |

## 2. Project Summary

自动扫描源目录视频文件，通过 AI + TMDB/Provider 刮削元数据，按规则分类入库。运行在飞牛 fnOS NAS 上，提供原生 Web UI。

技术栈：Python 3.12 + SQLite + 原生 HTTP API + 原生 HTML/CSS/JS + YAML 配置。

## 3. Commands

```bash
# 初始化环境
pyenv install 3.12.13 -s && pyenv local 3.12.13
./scripts/bootstrap_python_env.sh && source .venv/bin/activate

# 启动开发服务（端口 9855）
PYTHONPATH="${PWD}" python -m media_importer.media_importer -c config/config.yaml serve -p 9855 --host 0.0.0.0
# 或 ./start.sh [config] [host] [port]

# 全部测试（含需要本地服务的 UI 测试）
python -m pytest tests/

# 非 UI 测试
python -m pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py

# 架构护栏
python -m pytest tests/test_architecture_guards.py

# 编译检查
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer tests

# Python lint（新改动文件必须通过；存量基线 Phase 4 清零）
.venv/bin/ruff check <改动文件>

# 文档检查（断链/行数/front-matter）
python scripts/check_docs.py
```

注意事项：
- 优先用项目 `.venv/`（`.python-version` 固定 3.12.13）。
- UI 测试依赖 Playwright 模块、浏览器二进制和本地运行服务。
- 改动前先看 `.pytest_cache/v/cache/lastfailed`（可能有历史失败）。

## 4. Source Layout

```text
media_importer/
├── media_importer.py          # CLI 入口
├── api/                       # HTTP API（入口层，不载业务策略）
├── core/                      # 配置/DB/任务/日志（迁移期兼容层）
├── features/                  # 业务事实源（import_flow/scraping/tasks/...）
├── infrastructure/            # DB/文件系统基础能力
├── monitor/ notify/           # legacy/待迁移
└── webui/                     # 原生前端
```

依赖方向：api/CLI → features → infrastructure。`features/` 是业务事实源。

## 5. Safety Rules（红线）

- 删除或覆盖影视文件必须走回收站，禁止直接 `os.remove()` 删除源文件或入库文件。
- 临时文件只在明确属于 `temp_dir` 或 `.tmp`/`.copying` 边界时可直接删除。
- 文件操作必须限制在允许目录内，防路径穿越和误删。
- 敏感配置项返回前端前必须脱敏为 `***`。
- 不回滚用户已有改动；dirty worktree 中只处理本任务相关文件。
- 完整规则见 [docs/standards/safety.md](docs/standards/safety.md)。

## 6. Change Impact

改动必须同步的文档矩阵见 [docs/ai-map.md §3](docs/ai-map.md)（唯一事实源）。关键提醒：

| 改动类型 | 必须同步 |
|----------|----------|
| 新增 API | routes.py + architecture/api.md + standards/api.md + ai-map §2 |
| 新增配置项 | loader/migration/validator/API/frontend/docs/tests |
| 修改任务状态 | DB constants/task manager/import-flow/API/frontend/docs/tests |
| 修改文件删除/覆盖逻辑 | safety 文档 + 回收站测试 |

## 7. Development Workflow（轻量流程）

按变更级别准备文档（详见 [docs/workflows/feature-development.md](docs/workflows/feature-development.md)）：

| 级别 | 需求注册 | 方案(proposal) | ADR | 计划(plan) | 测试计划 |
|------|---------|------|-----|------|----------|
| 小改（bugfix） | ✅ 看板一行 | ❌ | ❌ | ❌ 可省 | 必跑既有回归 |
| 中改（功能/行为变更） | ✅ | ✅ | 仅架构级 | ✅ | ✅ plan 内章节 |
| 大改（跨feature/架构） | ✅ | ✅ | ✅ | ✅ | ✅ 独立章节 |

流程：注册需求 → 方案 → [ADR] → 计划 → 实施+测试 → 验收 → 归档（plan 必须归档，不得滞留）。
模板见 [docs/standards/documentation.md](docs/standards/documentation.md)。

## 8. Current Status（2026-08-22 恢复）

- 项目停摆一个月后恢复，新方向：**功能简洁化**。
- 简洁化 Phase 0-4 与二轮文档治理已完成（2026-08-27）；前端/后端规范见 standards/frontend.md、standards/backend.md。
- 当前执行：**简洁化路线图**（[plan（已归档）](docs/_archive/2026-08-27-simplification-complete/2026-08-22-simplification-roadmap.md)，Phase 0-4）；移除 Hermes 与 AI 刮削（[ADR-0010](docs/decisions/0010-remove-ai-scraping.md)）；状态机重构（REQ-20260822-000004）。
- 业务决策已拍板：前端只做减法；保留 watcher/源清理器/模拟器/维度/手动处理；公开发布 fpk。详见需求看板。
- feature-first 重构已落地（ADR-0004），scraper 迁移已完成（ADR-0008）。
