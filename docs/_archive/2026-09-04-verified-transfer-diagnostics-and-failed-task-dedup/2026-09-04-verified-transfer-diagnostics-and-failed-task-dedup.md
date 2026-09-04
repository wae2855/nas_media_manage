---
title: "校验传输诊断与失败任务去重方案"
type: proposal
date: 2026-09-04
status: approved
confidence: high
requirement: REQ-20260904-162232
---

# 校验传输诊断与失败任务去重方案

- **Requirement**: [REQ-20260904-162232](../../tracking/requirements-board.md)
- **Plan**: [实施计划](2026-09-04-fix-verified-transfer-diagnostics-and-failed-task-dedup-plan.md)

## 问题

fnOS 0.3.28 中《北海鲸梦》EP04 两次在目标暂存阶段报 SHA-256 不一致。现有检查顺序可能把“来源在哈希期间变化”显示成目标校验错误；同一路径失败后，自动扫描还会创建新的失败任务记录。

## 目标

- 来源发生变化时明确提示等待上游稳定；来源稳定时才提示检查目标存储或读取。
- 对稳定来源下的瞬时目标校验异常只做一次干净重试，仍失败则保留来源并停止发布。
- 自动扫描不再为最新同路径失败任务重复建档，人工重试入口保持可用。

## 方案概述

先检查来源哈希后的文件快照，再比较摘要；文件包暂存层只对明确的目标摘要不一致清理本任务 `.copying` 并从零重试一次。任务去重层把最新同路径 `FAILED` 视为已存在并跳过自动新建，用户仍可在原任务上手动重试。

## 影响面

- `infrastructure/filesystem/safety.py`：错误分类顺序和文案。
- `features/import_flow/services/file_operations.py`：单次受限重试。
- `core/task_manager.py` / scan flow：失败任务自动扫描去重。
- 文件安全、任务、入库流程及回归文档与测试。

## 备选与取舍

- **把所有错误都提示为上游变化**：证据不足，可能掩盖磁盘或挂载异常，否决。
- **取消 SHA 校验**：可能发布损坏影片并触发来源处理，违反安全红线，否决。
- **无限自动重试**：会反复读取大文件并给 NAS 带来持续 I/O，否决。
- **失败任务永不再处理**：会失去恢复能力；采用自动扫描跳过、用户显式重试。
