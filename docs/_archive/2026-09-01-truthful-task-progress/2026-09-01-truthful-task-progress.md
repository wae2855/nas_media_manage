---
title: "真实任务阶段与大文件传输进度"
type: proposal
date: 2026-09-01
status: approved
confidence: high
requirement: REQ-20260901-010051
---

# 真实任务阶段与大文件传输进度提案

## 问题（现状与痛点）

后端已经保存 `current_step`、`step_name`、`percentage`、`bytes_copied` 和 `total_bytes`，来源复制到中转也有逐块回调，但任务列表 API 不返回步骤和字节字段，任务卡与详情只显示“处理中”，任务页也不自动刷新。

真实 fnOS 证据显示：一个 17.4 GB 云盘文件已经写满中转 `.copying` 文件后，任务仍长时间停留在 `copy / 30%`。原因是安全复制还在执行源文件和目标文件的 SHA-256 完整性校验，但校验没有独立状态。中转位于 `/vol3`、片库分布在其他卷，入库会频繁进入无进度回调的跨盘安全复制；整组来源回收也可能在任务已显示成功后继续运行。

## 目标（可验证）

- 运行任务显示普通用户可理解的当前环节，而不是只有“处理中”。
- 复制到中转、跨盘写入片库等长耗时传输显示当前文件字节百分比和已完成/总容量。
- 恢复前缀校验、源摘要校验、目标摘要校验和安全发布均有诚实阶段提示；不能把“文件已写完”误报为“环节已完成”。
- 刮削、分类等不可计算字节百分比的环节显示阶段和已运行时间，不伪造剩余时间。
- 任务页仅在可见且有运行任务时自动刷新；桌面与 320～430px 手机均无溢出或操作抖动。
- 进度持久化节流，避免每 1 MB 一次 SQLite commit。

## 方案概述

1. 保留 `status + stage` 状态机，使用现有 `step_name/current_step/percentage/bytes_copied/total_bytes` 表达当前进度，不新增业务终态。
2. 扩充步骤名称为 `copy_resume_check`、`copy_transfer`、`copy_verify_source`、`copy_verify_target`、`copy_publish`、`scrape`、`classify`、`import_transfer`、`import_verify_*`、`source_cleanup` 等内部阶段；前端集中映射为中文。
3. `verified_copy` 增加结构化进度回调，覆盖续传检查、复制、校验和发布；`safe_move` 在 EXDEV 跨盘回退时透传回调。摘要计算仍保留 SHA-256 和 no-replace 发布，不降低安全边界。
4. 任务进度更新以时间、百分比、字节增量和阶段变化节流；阶段变化与完成必须立即持久化。
5. 任务列表 API 返回进度字段；卡片展示当前阶段、阶段进度和流程位置，详情增加时间线；运行任务存在时以轻量定时刷新列表。
6. 入库复制和来源整组回收接入同一进度通道；来源处理完成前不把整体任务表现为完全结束，或明确展示“入库完成，正在处理来源”。

## 影响面

- 后端：`infrastructure/filesystem`、`features/import_flow`、`features/source_files`、`features/recycle`、task repository/API。
- 前端：任务工具、列表、详情、页面刷新与 `cinema-pages.css`。
- 测试：安全复制、跨盘回退、进度节流、API 合同、任务 UI 与移动端。
- 文档：任务生命周期、入库流程、API、前端信息架构、文件流矩阵。

## 备选方案

- **只显示现有 overall percentage**：改动小，但复制完成后的校验仍会卡住，跨盘入库没有进度，而且 20～30 的步骤权重不是时间比例，会误导用户，否决。
- **移除重复校验提升速度**：会削弱云盘和跨盘文件完整性保障，违反数据安全边界，否决。
- **引入 WebSocket/SSE**：当前原生 HTTP 轮询足以覆盖 2～3 秒级体验，引入新长连接协议扩大部署复杂度，暂不采用。
