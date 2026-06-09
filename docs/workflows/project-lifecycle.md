# Project Lifecycle Workflow

本流程适用于 bug、新需求、重构、文档治理和前端工作。目标是让每项工作从发现到验收再到规范沉淀形成闭环。

需求注册、并行隔离、状态门禁、废弃回退等规则见 [requirement-management.md](../standards/requirement-management.md)。

## Lifecycle

1. Discovery: 记录问题、目标、约束、用户关注点和可选方向。
2. Proposal: 写清方案、边界、影响范围、风险和不做什么。
3. Decision: 涉及架构、数据模型、安全、部署或长期规范时新增 ADR。
4. Plan: 在 `docs/plans/` 建立当前计划，只保留活跃或待执行计划。
5. Implementation: 按计划改代码、文档和测试。
6. Verification: 运行单元、集成、回归、UI/E2E 或明确说明为什么暂缓。
7. Documentation Update: 同步 `docs/features/`、`docs/architecture/`、`docs/testing/`、`docs/INDEX.md` 和 `AGENTS.md`。
8. Pending Acceptance: 完成但未用户验收时写入 `docs/tracking/pending-acceptance.md`。
9. User Acceptance: 用户确认后移入 `docs/tracking/completed-items.md`。
10. Standards Backfill: 如果形成可复用规则，更新 `docs/standards/` 或 `AGENTS.md` 导航。
11. Archive: 完成、废弃或被替代的 plan/proposal 移入 `docs/_archive/`。

## Acceptance Reminder Rule

- 默认超过 24 小时或跨工作阶段仍未验收，AI 在后续对话开始时提醒。
- 用户明确延后时，更新 pending acceptance 的提醒时间或阶段。
- 验收前不要把事项写入 completed。

## Document Ownership by Work Type

| Work type | Required documents |
|-----------|--------------------|
| Bug | issue/root cause, plan if non-trivial, tests, known failures update, pending acceptance, completed summary after acceptance |
| Feature | brainstorm/proposal, ADR if needed, plan, feature doc, architecture/API/config docs, tests, acceptance record |
| Refactor | baseline, plan, ADR if boundary changes, repository/feature docs, regression result, archive update |
| Documentation | changed docs list, link scan, archive update, maintenance notes |
| Frontend | product workflow, information architecture, API dependency map, design acceptance notes, UI test plan |
