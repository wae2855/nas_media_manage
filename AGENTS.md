# 影音库AI智能整理 - AI Agent Guide

本文件是 AI 执行入口，只保留最高优先级规则和导航。详细规范见 `docs/standards/`，开发流程见 `docs/workflows/`。

## 0. Start Here

| 目标 | 入口 |
|------|------|
| 文档总入口 | [docs/README.md](docs/README.md) |
| 代码/文档/测试索引 | [docs/INDEX.md](docs/INDEX.md) |
| AI 任务导航 | [docs/ai-map.md](docs/ai-map.md) |
| 代码规范 | [docs/standards/coding.md](docs/standards/coding.md) |
| 架构规范 | [docs/standards/architecture.md](docs/standards/architecture.md) |
| 文档规范 | [docs/standards/documentation.md](docs/standards/documentation.md) |
| 测试规范 | [docs/standards/testing.md](docs/standards/testing.md) |
| 安全规范 | [docs/standards/safety.md](docs/standards/safety.md) |
| 功能开发流程 | [docs/workflows/feature-development.md](docs/workflows/feature-development.md) |
| 重构流程 | [docs/workflows/refactor-development.md](docs/workflows/refactor-development.md) |
| 旧文档说明 | [docs/legacy.md](docs/legacy.md) |

## 1. Project Summary

自动扫描源目录视频文件，通过 AI + TMDB/Provider 刮削元数据，按规则分类入库。运行在飞牛 fnOS NAS 上，提供原生 Web UI 管理任务、配置、维度、提示词、回收站和源目录清理。

技术栈：

- Python 3
- SQLite + JSON 字段
- 原生 HTTP API
- 原生 HTML/CSS/JS
- YAML 配置 + 自动迁移

## 2. Commands

```bash
# 安装依赖
pip install -r requirements.txt

# 启动开发服务，端口默认 9855
PYTHONPATH="${PWD}" python3 -m media_importer.media_importer -c config/config.yaml serve -p 9855 --host 0.0.0.0

# 或用封装脚本
./start.sh [config] [host] [port]

# 全部测试，包含需要本地服务的 UI 测试
pytest tests/

# 单个测试文件
pytest tests/test_sqlite_refactor.py

# 非 UI 测试
pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py
```

测试前注意：

- 项目没有 `pyproject.toml`，没有统一 lint/formatter/typecheck 配置。
- UI 测试依赖 Playwright 模块、浏览器二进制和本地运行服务。
- 许多测试可能已有历史失败，改动前先看 `.pytest_cache/v/cache/lastfailed`。

## 3. Source Layout

```text
media_importer/
├── media_importer.py          # CLI 入口
├── api/                       # HTTP API 和静态文件服务
├── core/                      # 配置、DB、任务、安全、回收站、日志、指标
├── domains/                   # 业务域入口，渐进承载稳定业务实现
├── pipeline/                  # 任务处理编排、确认、重分类
├── scraper/                   # LLM、Provider、置信度、维度映射
├── storage/                   # 文件扫描、复制、移动、分类、去重、源目录清理
├── monitor/                   # 文件监控、权限检查
├── notify/                    # Hermes 和 hook 通知
└── webui/                     # 原生前端
```

`deploy/` 内有部署副本，不是默认开发源。不要自动同步或修改 deploy，除非任务明确要求。

## 4. Highest Priority Safety Rules

- 删除或覆盖影视文件必须走回收站，禁止直接 `os.remove()` 删除源文件或入库文件。
- 临时文件只在明确属于 `temp_dir` 或 `.tmp` / `.copying` 边界时可直接删除。
- 文件操作必须限制在允许目录内，避免路径穿越和误删。
- 敏感配置项返回前端前必须脱敏为 `***`。
- 不要回滚用户已有改动；在 dirty worktree 中只处理本任务相关文件。

完整安全规则见 [docs/standards/safety.md](docs/standards/safety.md)。

## 5. Change Impact Rules

| 改动类型 | 必须同步 |
|----------|----------|
| 新增 API | `docs/architecture/api.md`, `docs/modules/api.md`, `docs/standards/api.md`, `docs/INDEX.md` |
| 新增配置项 | loader/migration/validator/API/frontend/docs/tests |
| 修改任务状态 | DB constants/task manager/pipeline/API/frontend/docs/tests |
| 修改文件删除/覆盖逻辑 | safety/recycle 文档和回收站测试 |
| 新增 Provider | Provider 文档、配置、API、测试 |
| 大架构重构 | plan + ADR + 相关 architecture/modules 文档 |

详细映射见 [docs/INDEX.md](docs/INDEX.md) 和 [docs/ai-map.md](docs/ai-map.md)。

旧中文目录 `docs/架构/`、`docs/方案/`、`docs/规范/`、`docs/测试/` 和 `docs/系统架构总览.md` 仅作为 legacy 参考，不作为当前架构事实来源。除非任务明确要求整理旧文档，否则 AI 修改代码前应优先读取 `docs/architecture/`、`docs/modules/`、`docs/standards/`、`docs/workflows/` 和 `docs/decisions/`。

## 6. Coding Rules

- Python 文件建议不超过 500 行。
- 文档建议不超过 500 行。
- API handler 不承载复杂业务策略。
- pipeline 长期目标是调用 services，而不是混合所有业务细节。
- 同子包内相对导入；跨子包使用 `media_importer.xxx` 绝对导入。
- 不添加无意义注释；复杂规则优先写入文档。
- CSS 使用变量体系，不硬编码颜色。
- 前端 JS 按功能模块拆分。

完整规则见 [docs/standards/coding.md](docs/standards/coding.md)。

## 7. Workflow Rules

新功能：

1. Brainstorm
2. Proposal
3. ADR if architecture decision is needed
4. Plan
5. Implementation
6. Unit -> Integration -> UI/Regression tests
7. Documentation update
8. Review and commit

重构：

1. 确认 baseline commit
2. 明确目标和非目标
3. 分阶段保持可运行
4. 结构重构和行为变更分开
5. 每阶段同步文档和测试

完整流程见 [docs/workflows/](docs/workflows/)。

## 8. Current Refactor Direction

当前大方向是 AI 友好架构重构：

- 先建立文档导航、规范、工作流和 ADR。
- 再做 `TaskContext`、`TaskLifecycle`。
- 再抽 pipeline services。
- 再做 config facade 和 API route table。
- 最后用兼容 proof slice 渐进引入 `domains/`，再按业务域迁移稳定实现，不一次性移动旧 public imports。

路线图见 [docs/plans/2026-05-31-refactor-ai-ready-architecture-roadmap.md](docs/plans/2026-05-31-refactor-ai-ready-architecture-roadmap.md)。
