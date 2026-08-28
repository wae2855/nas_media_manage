# Pending Acceptance

记录已完成但尚未由用户确认验收的事项。AI 在后续对话开始时应检查本文件；超过 24 小时或跨阶段未验收的事项需要主动提醒。

| Item | Completed at | Commit | Scope | Verification | User confirmation needed |
|------|--------------|--------|-------|--------------|--------------------------|

（当前无待验收事项。2026-08-22 停摆恢复后，用户授权：工程验收由 AI 以测试/回归结果自行判定，仅业务级决策需用户确认。历史 5 项停摆前待验收事项已批量豁免并转入 completed-items.md；其中前端全流程验收项并入前端方向重估，见 [backlog-reevaluation.md](backlog-reevaluation.md)。）

## Rules

- 新完成事项先进入本文件，不直接写入 completed。
- 工程验收（测试/回归/编译）由 AI 自行判定并记录结果；涉及业务取舍、产品方向、数据删除类操作仍需用户确认。
- 用户验收后，将摘要移动到 `completed-items.md` 并从本文件删除。
- 如果用户要求延后验收，在本文件记录新的提醒时间或阶段。
