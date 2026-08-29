# Requirements Board

活跃需求管理。已完成和废弃的需求不在此文件中保留。

## In Progress

| ID | Title | Type | Priority | Deps | Affects | Branch | Links | Created | Updated |
|----|-------|------|----------|------|---------|--------|-------|---------|---------|
## Pending Acceptance

| ID | Title | Type | Priority | Deps | Affects | Branch | Links | Created | Updated |
|----|-------|------|----------|------|---------|--------|-------|---------|---------|
| REQ-20260828-151346 | 存储安全与配置界面简化重构 | refactor | P0 | REQ-20260822-000003 已关闭 | configuration, filesystem, import_flow, recycle, tasks, monitor, webui, deploy, docs | main | Proposal: [方案](../proposals/2026-08-28-storage-safe-configuration-redesign.md) \| Plan: [底座](../plans/2026-08-28-storage-safe-configuration-redesign-plan.md), [依赖整合](../plans/2026-08-28-feat-configuration-dependency-and-readiness-plan.md) \| ADR: [0011](../decisions/0011-fnos-install-runtime-config-ownership.md), [0012](../decisions/0012-storage-role-topology.md), [0013](../decisions/0013-verified-transfer-recovery.md), [0014](../decisions/0014-source-unit-lifecycle.md), [0015](../decisions/0015-library-root-relative-rules.md) | 2026-08-28 | 2026-08-28 |

## Planned

| ID | Title | Type | Priority | Deps | Affects | Branch | Links | Created | Updated |
|----|-------|------|----------|------|---------|--------|-------|---------|---------|

## Draft

| ID | Title | Type | Priority | Deps | Affects | Branch | Links | Created | Updated |
|----|-------|------|----------|------|---------|--------|-------|---------|---------|
| REQ-20260822-000005 | 授权系统接入 | feature | P2 | 简洁化完成后 | api, deploy, webui | main | 用户 2026-08-22 声明：未来计划，暂不启动 | 2026-08-22 | 2026-08-22 |

## Rules

- ID 格式：`REQ-YYYYMMDD-HHmmSS`，AI 创建时自动生成。
- 状态变更时同步更新 Updated 字段并移至对应分组。
- `accepted` → 移至 [completed-items.md](completed-items.md)。
- `discarded` → 移至 [discarded-items.md](discarded-items.md)。
- AI 每次对话开始扫描本文件。
- 超 24 小时未验收的需求，AI 主动提醒。
- 完整规范见 [requirement-management.md](../standards/requirement-management.md)。
