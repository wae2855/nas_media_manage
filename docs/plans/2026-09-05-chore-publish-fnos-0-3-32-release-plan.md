---
title: "chore: 发布 fnOS 0.3.32 GitHub Release"
type: plan
date: 2026-09-05
status: in_progress
confidence: high
requirement: REQ-20260905-200250
---

# 发布 fnOS 0.3.32 GitHub Release

将已入库影片人工调整位置、季集业务化展示与上架元数据加固作为 `0.3.32` 候选版本发布到公开 GitHub Releases。

## Target End State

- `main` 包含本轮实现、完整文档、根 `VERSION=0.3.32` 与候选发布台账。
- 从该精确源码构建并验证 `nas-media-importer.fpk` 和 `.sha256`。
- GitHub 创建 `v0.3.32` prerelease，标签指向发布提交并包含两个可匿名下载资产。
- 发布说明明确 `LOCAL_BUILD PASS`、`FNOS_UAT NOT_RUN`，不覆盖已验证的 0.3.31 Latest。

## Implementation Tasks

- [x] 核对公开仓库、GitHub 认证、远端 `main`、当前 Release 与发布台账。
- [x] 完成本轮业务代码、文档、自我评审和开发环境非沙盒 1176 项全量回归。
- [ ] 提升唯一版本事实源至 0.3.32，并提交、推送发布源码。
- [ ] 从精确源码生成 FPK，验证结构、版本、依赖、指纹和 SHA-256。
- [ ] 提交并推送生成包工作区及候选台账，确保远端 `main` 与本地一致。
- [ ] 创建 `v0.3.32` prerelease，上传 FPK 与 SHA-256。
- [ ] 匿名回下载并复核大小、哈希、包内容和标签提交。
- [ ] 记录最终发布证据并归档计划。

## Acceptance Criteria

- 全量测试、Ruff、compileall、JS、文档和 diff 检查无已知失败。
- `scripts/validate_fpk.py build/nas-media-importer.fpk --version 0.3.32` 通过。
- 本地、发布台账、GitHub 资产与匿名回下载 FPK 的 SHA-256 完全一致。
- `v0.3.32` 标签指向最终发布提交，Release 非草稿且为 prerelease。
- GitHub `main` 与本地 `HEAD` 一致；不提交凭据、本机配置、数据库、日志或下载缓存。

## Release Notes Scope

- 电视剧季集显示改为“第 N 季 / 第 N 集”，不再暴露 `season` / `episode` 技术字段。
- 已完成影片可创建独立“人工调整”任务，安全调整片库位置并保留审计历史。
- 影片和字幕作为文件包一起移动，冲突不覆盖；失败调整回到待确认。
- 存储重新检查增加忙碌态、超时与明确终态提示。
- fnOS manifest 补齐 `oneway`、GitHub 联系地址和固定端口冲突预检。

## Boundaries

- 本轮授权包括提交、推送、构建与 GitHub Release，不包括安装到用户 fnOS 或真实影片移动。
- 0.3.32 在真机确认前保持 candidate/prerelease；0.3.31 继续作为最近验收正常版本。
- 只使用仓库发布脚本生成 package workspace，不手工同步其中的应用源码。
