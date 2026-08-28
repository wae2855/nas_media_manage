# AI Agent Workflow

AI 接到任务后：

1. 读 `AGENTS.md`。
2. 查 `docs/tracking/backlog-reevaluation.md`：任务相关历史待办是否已冻结待重估（停摆恢复期）。
3. 查 `docs/ai-map.md` §1 判断修改范围（任务→代码→测试→文档映射）。
4. 判断变更级别（小改/中改/大改），按 [feature-development.md](feature-development.md) 分级要求决定是否需要 proposal/plan/ADR。
5. 修改代码或文档。
6. 按影响范围运行测试（`docs/ai-map.md` §3 + [../testing/regression-matrix.md](../testing/regression-matrix.md)）。
7. 更新 `docs/ai-map.md` 和相关模块/架构文档。
8. 文档变更跑 `python scripts/check_docs.py`（断链/行数/front-matter）。
9. 最终回复说明变更、测试结果和未完成风险。
