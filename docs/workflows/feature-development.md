# Feature Development Workflow

轻量开发闭环。分级决定文档要求，避免过度流程化。

## 分级文档要求（详见 [../standards/documentation.md](../standards/documentation.md) 模板）

| 级别 | 判定标准 | 需求注册 | proposal | ADR | plan | 测试计划 |
|------|----------|---------|----------|-----|------|----------|
| 小改 | bugfix、参数/文案调整、单文件修复 | ✅ 看板一行 | ❌ | ❌ | ❌（看板 Links 记录即可） | 必跑既有回归 |
| 中改 | 新功能点、行为变更、跨 2-3 文件 | ✅ | ✅ | 仅架构级 | ✅ | ✅ plan 内必备章节 |
| 大改 | 跨 feature、架构级、破坏性变更 | ✅ | ✅ | ✅ | ✅ | ✅ 独立章节 |

## 流程（中改及以上）

1. **注册需求**：`docs/tracking/requirements-board.md` 加一行（REQ-ID 格式见 [../standards/requirement-management.md](../standards/requirement-management.md)）。
2. **方案**：`docs/proposals/` 一页纸（问题/目标/方案概述/影响面/备选）。小任务可省略。
3. **ADR**（仅架构级）：`docs/decisions/` 按模板。
4. **计划**：`docs/plans/` 按 plan 模板，必须含 front-matter 和测试计划章节，无测试计划不得 approved。
5. **实施 + 测试**：按计划任务分解执行；每步跑对应测试。
6. **文档同步**：按 [../ai-map.md §3](../ai-map.md) 变更影响矩阵同步；跑 `python scripts/check_docs.py`。
7. **提交**：commit 说明含测试结果。
8. **待验收**：写入 `docs/tracking/pending-acceptance.md`。
9. **验收归档**：用户确认后移入 `completed-items.md`；plan/proposal 移入 `docs/_archive/<日期-主题>/`，归档 README 注明依据。
10. **规范回填**：沉淀出的长期规则更新到 `docs/standards/`。

## 硬规则

- plan 完成后必须归档，不得长期滞留 `docs/plans/`。
- 状态枚举只用 `draft | approved | in-progress | complete | superseded`。
- 重构不混行为变更；必须混合时在 plan 和 commit 中单独说明。
