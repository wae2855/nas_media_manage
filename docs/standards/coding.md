# Coding Standards

## Python

- 单个 Python 文件建议不超过 500 行。
- 超过 500 行应优先拆分；暂不拆分时必须在计划或评审说明中解释原因。
- 函数职责单一，避免在 handler 或 step 中混合过多业务策略。
- 同子包内相对导入，例如 `from .utils import ...`。
- 跨子包使用绝对导入，例如 `from media_importer.infrastructure.db import ...`、`from media_importer.features.scraping import ...` 等;不直接 import 旧路径 `media_importer.core.db` 或 `media_importer.scraper` (architecture guard 拦截)。
- 不添加无意义注释；复杂业务规则可写短注释或放文档。

## Frontend

- 原生 JS/CSS，无构建依赖。
- CSS 使用变量，例如 `var(--text-primary)`。
- JS 按功能拆分到 `api/config/tasks/path-rules/prompts/dimensions/app` 等模块。

## Refactor Rule

结构重构不应混入行为变更。必须行为变更时，单独记录在计划和提交说明中。
