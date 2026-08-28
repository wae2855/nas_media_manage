# Documentation Home

本目录是项目知识入口。项目按 feature-first 架构组织：业务能力在 `media_importer/features/` 与 `docs/features/`。

## Start Here（渐进式披露）

| 层 | 目标 | 入口 |
|----|------|------|
| L0 | AI 会话入口（命令+红线+路由） | [AGENTS.md](../AGENTS.md) |
| L1 | 文档目录导航（本文件） | 本文件 |
| L2 | **任务→代码→测试→文档映射（AI 先查这里）** | [ai-map.md](ai-map.md) |
| L3 | 具体事实文档 | 见下表 |

## Directory Map

| 目标 | 入口 |
|------|------|
| 了解产品目标和术语 | [product/](product/) |
| 当前架构事实 | [architecture/](architecture/) |
| 业务功能说明（代码入口/扩展点/测试） | [features/](features/) |
| 长期规范（代码/文档/安全/配置/测试） | [standards/](standards/) |
| 开发流程（需求→方案→计划→测试→验收→归档） | [workflows/](workflows/) |
| 架构决策记录（ADR） | [decisions/](decisions/) |
| 测试策略与回归矩阵 | [testing/](testing/) |
| 探索期发散记录 | [brainstorms/](brainstorms/) |
| 待评审方案 | [proposals/](proposals/) |
| 执行中的计划 | [plans/](plans/) |
| 需求看板 / 验收台账 / 待办重估 | [tracking/](tracking/) |
| 旧文档状态与迁移对照 | [legacy.md](legacy.md) |
| 归档（只作历史追溯） | [_archive/](_archive/README.md) |

## Documentation Rules

- `architecture/` 描述当前事实，不放未实施设想；设想放 `proposals/`/`plans/`。
- `features/` 连接业务功能、代码入口、配置、API、数据和测试。
- `standards/` 放长期规则，AGENTS.md 只摘要最高优先级规则。
- 变更影响矩阵唯一维护在 [ai-map.md §3](ai-map.md)；不在多文件重复。
- 文档不包含可机械生成的全量清单（文件/测试列表），只写规则和例外。
- plan/proposal/brainstorm 必须有 front-matter（见 [standards/documentation.md](standards/documentation.md)）。
- 每次文档变更跑 `python scripts/check_docs.py`。
- `_archive/` 只保存历史，当前文档不得引用归档内容作为事实。

## Current Status（2026-08-22 恢复）

- 项目停摆一个月后恢复，新方向：**功能简洁化**。
- 文档治理已完成（方案已归档至 `_archive/2026-08-22-plans-cleanup/`），摘要见 [tracking/completed-items.md](tracking/completed-items.md)。
- 下一步：待办重估（[tracking/backlog-reevaluation.md](tracking/backlog-reevaluation.md)）→ 全项目简洁化评估（REQ-20260822-000001）。
- 历史待办冻结待重估，不得直接执行。
