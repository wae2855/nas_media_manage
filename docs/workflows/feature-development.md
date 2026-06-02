# Feature Development Workflow

1. Brainstorm：明确问题、目标、方案候选。
2. Proposal：写 `docs/proposals/<feature>.md` 中的待评审方案。
3. ADR：涉及架构选择时写 `docs/decisions/`。
4. Plan：写 `docs/plans/<date>-feat-xxx.md`。
5. Implementation：按计划实现。
6. Test：单元 -> 集成 -> UI/回归。
7. Documentation：更新 `docs/features/`、architecture、standards、testing、INDEX。
8. Review：代码和文档一起评审。
9. Commit：提交说明包含测试结果。
10. Pending Acceptance：写入 `docs/tracking/pending-acceptance.md`。
11. User Acceptance：用户确认后写入 `docs/tracking/completed-items.md`。
12. Standards Backfill：可复用规则更新到 `docs/standards/` 或 `AGENTS.md`。
13. Archive：完成或被替代的 plan/proposal 移入 `docs/_archive/`。

完整闭环见 [project-lifecycle.md](project-lifecycle.md)。
