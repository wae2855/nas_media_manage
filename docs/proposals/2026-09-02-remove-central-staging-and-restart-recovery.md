---
title: "取消中心中转与整任务重启方案"
type: proposal
date: 2026-09-02
status: approved
confidence: high
requirement: REQ-20260902-033000
---

# 取消中心中转与整任务重启方案

- **Requirement**: [REQ-20260902-033000](../tracking/requirements-board.md)
- **Discovery**: [任务异常退出与最少传输评审](../brainstorms/2026-09-02-task-exit-and-minimal-transfer-brainstorm.md)
- **ADR**: [ADR-0022](../decisions/0022-remove-central-staging-and-whole-task-restart.md)
- **Plan**: [实施计划（已归档）](../_archive/2026-09-02-remove-central-staging-and-whole-task-restart/2026-09-02-refactor-remove-central-staging-and-restart-recovery-plan.md)

## 目标

中心中转不再是产品配置、存储角色或恢复断点。影片身份、目标规则和重复决策确定后，来源直接写入目标侧任务私有暂存；未提交的任务中断后清理暂存并从来源重新整理，不续接旧步骤或旧大文件。

## 产品合同

- 配置页和 fnOS 授权只要求来源、回收、日志、海报缓存和目标片库，不再要求中转目录。
- 用户看到的流程固定为“识别 → 决策 → 入库 → 来源处理”，没有隐含的第二次大文件复制。
- 入库前中断：来源不变，目标没有正式文件，任务提示可重新整理。
- 完整入库后记录未完成：系统复核全部成员后自动恢复成功，不重复复制。
- 无法证明完整或安全回退：文件全部保留，任务明确提示人工检查。
- 重试等于整任务重来，不提供步骤续跑或旧临时文件断点。

## 实现边界

- 删除 `temp_dir`、`file_location=temp`、`FileCopier` 业务入口、旧中转清理和 fnOS 中转授权。
- 目标侧 `.copying` / `.bundle.tmp` 只属于当前任务，只能由持久清单、目标根和临时后缀共同证明后清理。
- 来源在目标文件包提交前保持只读；来源回收或永久删除继续走现有安全服务。
- 重启恢复仅访问数据库清单列出的有限路径，不遍历片库。

## 非目标

- 不兼容旧任务、旧 `temp_dir` 配置或历史中转文件。
- 不恢复业务步骤或跨重试续传大文件。
- 不改变目标片库禁止普通删除和禁止隐式覆盖的边界。
