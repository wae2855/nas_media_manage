# Requirements Board

活跃需求管理。已完成和废弃的需求不在此文件中保留。

## In Progress

| ID | Title | Type | Priority | Deps | Affects | Branch | Links | Created | Updated |
|----|-------|------|----------|------|---------|--------|-------|---------|---------|

## Pending Acceptance

| ID | Title | Type | Priority | Deps | Affects | Branch | Links | Created | Updated |
|----|-------|------|----------|------|---------|--------|-------|---------|---------|
| REQ-20260616-000001 | 待确认流程端到端整治 | bugfix+refactor | P0 | - | features/import_flow, api/task_handlers, webui/js/cinema-*, infrastructure/db | main | Plan: [plan](../plans/2026-06-16-confirm-workflow-overhaul-plan.md) \| ADR: [0007](../decisions/0007-confirm-workflow-preview-vs-import-split.md) \| Tests: [test_p0_confirm_workflow_fixes](../../tests/test_p0_confirm_workflow_fixes.py) | 2026-06-16 | 2026-06-20 |

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
