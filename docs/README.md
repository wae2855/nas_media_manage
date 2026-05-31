# Documentation Home

本目录是项目知识入口。后续代码重构会持续更新这里；当前阶段先建立导航、规范和工作流骨架，避免在代码大改前把实现细节写死。

## Start Here

| 目标 | 入口 |
|------|------|
| 快速了解项目结构 | [INDEX.md](INDEX.md) |
| AI 要判断改哪里 | [ai-map.md](ai-map.md) |
| 了解产品目标和术语 | [product/overview.md](product/overview.md) |
| 查看当前架构地图 | [architecture/overview.md](architecture/overview.md) |
| 查看代码模块说明 | [modules/](modules/) |
| 查看代码/文档/测试规范 | [standards/](standards/) |
| 按流程开发功能或重构 | [workflows/](workflows/) |
| 查看架构决策记录 | [decisions/](decisions/) |
| 查看测试策略和回归矩阵 | [testing/](testing/) |

## Documentation Rules

- `architecture/` 描述当前事实，不放未实施设想。
- `modules/` 连接代码目录、扩展点、测试入口。
- `standards/` 放长期规则，AGENTS.md 只摘要最高优先级规则。
- `workflows/` 放从想法到交付的闭环流程。
- `decisions/` 放 ADR，说明为什么做某个架构选择。
- `_archive/` 只保存历史，不作为当前事实引用。

## Current Reorganization Status

当前处于文档体系重构第一阶段：先建立框架和规范。详细架构事实会在后续 `TaskContext`、`TaskLifecycle`、pipeline services 等代码重构稳定后逐步补全。
