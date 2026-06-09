# Requirements Board

活跃需求管理。已完成和废弃的需求不在此文件中保留。

## In Progress

| ID | Title | Type | Priority | Deps | Affects | Branch | Links | Created | Updated |
|----|-------|------|----------|------|---------|--------|-------|---------|---------|

## Pending Acceptance

| ID | Title | Type | Priority | Deps | Affects | Branch | Links | Created | Updated |
|----|-------|------|----------|------|---------|--------|-------|---------|---------|
| REQ-20260608-230001 | 前端功能迁移收尾 A1-A7 | frontend | P1 | - | webui/js/, webui/partials/ | main | Plan: [migration-plan](../plans/2026-06-06-frontend-function-migration-plan.md) | 2026-06-08 | 2026-06-08 |
| REQ-20260608-BC001 | 前端 B/C 类功能增强与优化 | frontend | P1 | A1-A7 | webui/js/, webui/css/, webui/index.html | main | Plan: [bc-enhancement-plan](../plans/2026-06-08-frontend-bc-enhancement-plan.md) | 2026-06-08 | 2026-06-08 |

## Planned

| ID | Title | Type | Priority | Deps | Affects | Branch | Links | Created | Updated |
|----|-------|------|----------|------|---------|--------|-------|---------|---------|

## Draft

| ID | Title | Type | Priority | Deps | Affects | Branch | Links | Created | Updated |
|----|-------|------|----------|------|---------|--------|-------|---------|---------|

## Rules

- ID 格式：`REQ-YYYYMMDD-HHmmSS`，AI 创建时自动生成。
- 状态变更时同步更新 Updated 字段并移至对应分组。
- `accepted` → 移至 [completed-items.md](completed-items.md)。
- `discarded` → 移至 [discarded-items.md](discarded-items.md)。
- AI 每次对话开始扫描本文件。
- 超 24 小时未验收的需求，AI 主动提醒。
- 完整规范见 [requirement-management.md](../standards/requirement-management.md)。
