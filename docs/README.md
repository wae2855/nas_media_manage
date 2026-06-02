# Documentation Home

本目录是项目知识入口。当前项目按 feature-first 架构重组：业务能力优先进入 `media_importer/features/` 与 `docs/features/`，旧技术分层文档逐步归档。

## Start Here

| 目标 | 入口 |
|------|------|
| 快速了解项目结构 | [INDEX.md](INDEX.md) |
| AI 要判断改哪里 | [ai-map.md](ai-map.md) |
| 了解产品目标和术语 | [product/overview.md](product/overview.md) |
| 查看前端重做待办 | [product/frontend-redesign-todo.md](product/frontend-redesign-todo.md) |
| 查看当前架构地图 | [architecture/overview.md](architecture/overview.md) |
| 查看业务功能说明 | [features/](features/) |
| 查看仓库结构和归档规则 | [architecture/repository-structure.md](architecture/repository-structure.md), [architecture/archive-policy.md](architecture/archive-policy.md) |
| 查看代码/文档/测试规范 | [standards/](standards/) |
| 按流程开发功能或重构 | [workflows/](workflows/) |
| 查看待验收和完成事项 | [tracking/pending-acceptance.md](tracking/pending-acceptance.md), [tracking/completed-items.md](tracking/completed-items.md) |
| 查看架构决策记录 | [decisions/](decisions/) |
| 查看测试策略和回归矩阵 | [testing/](testing/) |
| 查看旧文档状态 | [legacy.md](legacy.md) |

## Documentation Rules

- `architecture/` 描述当前事实，不放未实施设想。
- `features/` 连接业务功能、代码入口、配置、API、数据和测试。
- `modules/` 是迁移期辅助索引；新事实优先写入 `features/`。
- `standards/` 放长期规则，AGENTS.md 只摘要最高优先级规则。
- `workflows/` 放从想法到交付的闭环流程。
- `decisions/` 放 ADR，说明为什么做某个架构选择。
- `_archive/` 只保存历史，不作为当前事实引用。
- `架构/`、`方案/`、`规范/`、`测试/` 和 `系统架构总览.md` 是旧中文文档区，仅作 legacy 参考；后续统一移入 `_archive/`。

## Current Reorganization Status

当前文档体系正在从模块目录索引迁移到 feature-first 索引。旧中文文档、完成/废弃计划和历史测试脚本会统一归档；当前事实文档不得把归档内容作为依据。
