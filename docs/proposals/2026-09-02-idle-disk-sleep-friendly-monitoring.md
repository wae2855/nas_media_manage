---
title: "空闲状态硬盘休眠友好的后台监控"
type: proposal
date: 2026-09-02
status: approved
---

# 空闲状态硬盘休眠友好的后台监控

- **Requirement**: [REQ-20260902-013607](../tracking/requirements-board.md)
- **Plan**: [实施计划](../plans/2026-09-02-fix-idle-disk-sleep-friendly-monitoring-plan.md)

## 问题

后台自动整理没有任务时仍按来源轮询周期检查全部存储角色。目标片库会执行根目录写入探针和容量检查，本地回收会被递归遍历；首页自动刷新还会重复解析片库路径和扫描海报缓存。这会让启用自动休眠的 NAS 磁盘周期性被唤醒。

## 目标

- 空闲轮询只访问来源目录。
- 真正发现稳定候选后才检查支持目录，分类确定目标后只检查选中的片库。
- 完整配置检查、挂载身份、容量、写入及冲突安全不降级。
- 回收维护与首页缓存治理不再跟随高频轮询反复触盘。

## 方案概述

将目录检查拆成来源扫描、处理支持、单目标片库和完整配置四个作用域。watcher 只在阶段需要时逐步扩大检查范围；失败候选保留并在恢复后重试。回收过期维护节流为每日一次。首页以配置和任务快照作为缓存键，无变化时只查数据库和内存。

## 影响面

- `features/configuration/storage_readiness.py`
- `monitor/file_watcher.py`
- `features/import_flow/runner.py` 与文件步骤
- `features/tasks/dashboard_service.py`
- `api/thumbnail_handlers.py` 与缩略图缓存
- watcher、配置、首页及安全回归测试和事实文档

## 备选方案

- 只增大扫描周期：不能避免多个片库被同步唤醒，拒绝。
- 增加“休眠模式”开关：增加普通用户配置负担，拒绝。
- 完全取消实时门禁：会削弱挂载失效和空间不足保护，拒绝。
