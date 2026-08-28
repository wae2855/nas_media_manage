# Coding Standards

## Toolchain（目标态，2026-08-22 定）

| 工具 | 用途 | 状态 |
|------|------|------|
| Python 3.12.13（pyenv 固定） | 运行时 | ✅ 已落地（`.python-version`） |
| `python -m compileall` | 语法检查 | ✅ 已落地 |
| pyright（`pyrightconfig.json`，standard 模式） | 类型检查 | ✅ 配置已存在；纳入日常验证由工具链引入轮次统一安排 |
| Ruff（format + lint） | Python 格式化与静态检查 | ✅ 已落地（`pyproject.toml` 配置；依赖在 requirements-dev.txt） |
| Prettier | 前端 css/js 格式化 | ⏳ 目标态，格式化存量放 Phase 4 统一执行 |

命令：
```bash
.venv/bin/ruff check media_importer tests        # lint（存量基线见下）
.venv/bin/ruff format media_importer tests       # 格式化
```

存量策略（2026-08-22 基线）：现存 600+ lint 问题不在 Phase 0 突击清理（避免与简洁化删码冲突）；**新改动的文件必须通过 `ruff check`**；全量格式化与清零在 Phase 4 收尾执行。

## Python

- 单个 Python 文件建议不超过 500 行。
- 超过 500 行应优先拆分；暂不拆分时必须在计划或评审说明中解释原因。
- 函数职责单一，避免在 handler 或 step 中混合过多业务策略。
- 同子包内相对导入，例如 `from .utils import ...`。
- 跨子包使用绝对导入，例如 `from media_importer.infrastructure.db import ...`、`from media_importer.features.scraping import ...` 等；不直接 import 旧路径 `media_importer.core.db` 或 `media_importer.scraper`（architecture guard 拦截）。
- 不添加无意义注释；复杂业务规则可写短注释或放文档。

## Frontend

- 原生 JS/CSS，无构建依赖。
- CSS 使用变量，例如 `var(--text-primary)`。
- JS 按功能拆分到 `api/config/tasks/path-rules/prompts/dimensions/app` 等模块。

## Refactor Rule

结构重构不应混入行为变更。必须行为变更时，单独记录在计划和提交说明中。
