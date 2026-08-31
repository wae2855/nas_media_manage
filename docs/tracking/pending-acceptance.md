# Pending Acceptance

记录已完成但尚未由用户确认验收的事项。AI 在后续对话开始时应检查本文件；超过 24 小时或跨阶段未验收的事项需要主动提醒。

| Item | Completed at | Commit | Scope | Verification | User confirmation needed |
|------|--------------|--------|-------|--------------|--------------------------|
| 目标片库不可删除硬边界返工（REQ-20260831-004019） | 2026-08-31 | `ea8cfcf` | 目录拓扑/挂载身份、启动恢复、任务删除/重命名、来源清理、确认替换与回收恢复 no-replace、链接写入门禁、fnOS 回环监听 | LOCAL：822 passed + 181 subtests；Ruff/compileall/JS/架构/文档/包内合同 PASS；0.3.11 FPK SHA256 `576d5c47856e9fae991ffe1a739162b5d040b77aac98cced36cebcc26a1c2c9c`；FNOS_UAT NOT_RUN | 在备份/隔离的真实 fnOS 上安装，确认桌面入口、目录重新授权、挂载掉线阻断、同名保留/保留两份/替换和回收恢复 |
| fnOS 动态目录清单与首次配置验收（REQ-20260830-180954） | 2026-08-31 | `ea8cfcf` | 首次空白、0～N 片库、全部目录统一入口、逐目录 ACL/readiness、中转切换门禁；补齐多片库暂存后的最终确认与原位失败反馈 | LOCAL PASS：822 + 181 subtests、真实浏览器 4、专项 69；JS/Ruff/文档/diff 检查通过；0.3.11 FPK SHA256 `576d5c47856e9fae991ffe1a739162b5d040b77aac98cced36cebcc26a1c2c9c`；FNOS_UAT NOT_RUN | 在真实 fnOS 确认暂存多个片库后无需重新选择即可关联；失败能看到具体未覆盖规则，成功后弹窗关闭并刷新存储检查；继续验证其他目录与开场检查 |

（2026-08-22 停摆恢复后，用户授权：工程验收由 AI 以测试/回归结果自行判定，仅业务级决策需用户确认。历史 5 项停摆前待验收事项已批量豁免并转入 completed-items.md；其中前端全流程验收项并入前端方向重估，见 [backlog-reevaluation.md](backlog-reevaluation.md)。）

## Rules

- 新完成事项先进入本文件，不直接写入 completed。
- 工程验收（测试/回归/编译）由 AI 自行判定并记录结果；涉及业务取舍、产品方向、数据删除类操作仍需用户确认。
- 用户验收后，将摘要移动到 `completed-items.md` 并从本文件删除。
- 如果用户要求延后验收，在本文件记录新的提醒时间或阶段。
