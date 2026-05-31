# Documentation Standards

## Document Types

- `architecture/`: 当前事实。
- `modules/`: 模块职责、入口、扩展点、测试。
- `standards/`: 长期规范。
- `workflows/`: 工作闭环流程。
- `decisions/`: ADR 决策日志。
- `plans/`: 已批准或执行中的计划。
- `proposals/`: 待评审方案。
- `_archive/`: 历史备份，不作为当前事实引用。

## Status Labels

- `📋 待评审`
- `🔄 进行中`
- `✅ 已实施`
- `🗄️ 已归档`

## Size Rule

文档建议不超过 500 行。超过时优先拆分，保持单文档职责清晰。

## Required Sections for Module Docs

- Code
- Responsibility
- Extension Points
- Related Docs
- Tests

## Archive Rule

历史文档先归档，再迁移，不在同一变更中直接删除重要内容。
