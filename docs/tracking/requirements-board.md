# Requirements Board

活跃需求管理。已完成和废弃的需求不在此文件中保留。

## In Progress

| ID | Title | Type | Priority | Deps | Affects | Branch | Links | Created | Updated |
|----|-------|------|----------|------|---------|--------|-------|---------|---------|
| REQ-20260830-030818 | 配置开始页增加开发者支持卡 | feature | P2 | 无 | webui, tests, docs | main | Plan: [开发者支持卡](../plans/2026-08-30-feat-developer-support-card-plan.md) | 2026-08-30 | 2026-08-30 |
## Pending Acceptance

| ID | Title | Type | Priority | Deps | Affects | Branch | Links | Created | Updated |
|----|-------|------|----------|------|---------|--------|-------|---------|---------|
| REQ-20260831-004019 | 目标片库不可删除硬边界返工 | bugfix | P0 | REQ-20260828-151346 | configuration, import_flow, tasks, source_cleaning, source_files, recycle, deploy, tests, docs | main | Plan: [硬边界返工](../plans/2026-08-31-fix-target-library-hard-boundary-plan.md) \| ADR: [0018](../decisions/0018-target-library-additive-conflict-boundary.md) | 2026-08-31 | LOCAL_COMPLETE：片库只新增、确认替换双重 SHA-256/no-replace、本地回收、链接与挂载身份门禁、fnOS 回环监听；0.3.10 待真机验收 |
| REQ-20260830-180954 | fnOS 首次启动目录授权、多片库与离线依赖 | feature | P0 | REQ-20260828-151346 | configuration, import_flow, storage, webui, deploy, api, tests, docs | main | Proposal: [方案](../proposals/2026-08-30-fnos-first-run-multi-library.md) \| Plan: [暂存与确认返工（已归档）](../_archive/2026-08-31-fnos-library-migration-confirmation-flow/2026-08-31-fix-library-migration-confirmation-flow-plan.md) \| ADR: [0017](../decisions/0017-fnos-first-run-directory-authorization.md) | 2026-08-30 | LOCAL_COMPLETE：暂存后可直接确认关联，提交中/失败/成功均有原位反馈；非 UI 822、UI 4、专项 69 通过；FPK 未重建，待 fnOS 继续验收 |
| REQ-20260830-144111 | 首页语义与全站双端体验优化 | frontend | P0 | REQ-20260828-151346 | tasks, api, webui, tests, docs | main | Proposal: [方案](../proposals/2026-08-30-dashboard-responsive-experience.md) \| Plan: [实施计划](../plans/2026-08-30-feat-dashboard-responsive-experience-plan.md) | 2026-08-30 | 2026-08-30 |
| REQ-20260830-124001 | 配置开始页增加四步流程海报 | feature | P2 | 无 | webui, tests, docs | main | Plan: [四步流程海报](../plans/2026-08-30-feat-start-page-process-timeline-plan.md) | 2026-08-30 | 2026-08-30 |
| REQ-20260828-151346 | 存储安全与配置界面简化重构 | refactor | P0 | REQ-20260822-000003 已关闭 | configuration, filesystem, import_flow, recycle, tasks, monitor, webui, deploy, docs | main | Proposal: [方案](../proposals/2026-08-28-storage-safe-configuration-redesign.md) \| Plan: [底座](../plans/2026-08-28-storage-safe-configuration-redesign-plan.md), [依赖整合](../plans/2026-08-28-feat-configuration-dependency-and-readiness-plan.md), [fnOS 包就绪（已归档）](../_archive/2026-08-30-fnos-package-readiness/2026-08-30-fix-fnos-package-readiness-plan.md) \| ADR: [0011](../decisions/0011-fnos-install-runtime-config-ownership.md), [0012](../decisions/0012-storage-role-topology.md), [0013](../decisions/0013-verified-transfer-recovery.md), [0014](../decisions/0014-source-unit-lifecycle.md), [0015](../decisions/0015-library-root-relative-rules.md) | 2026-08-28 | 2026-08-30 |

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
