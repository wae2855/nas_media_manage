---
title: "chore: 发布 fnOS 0.3.31 GitHub Release"
type: plan
date: 2026-09-04
status: complete
confidence: high
---

# 发布 fnOS 0.3.31 GitHub Release

- **Requirement**: [REQ-20260904-234308](../tracking/requirements-board.md)

将已经通过本地构建门禁的 `0.3.31` 候选 FPK 发布到公开 GitHub Releases，使 README 中的安装入口真实可用。

## Problem Statement

公开仓库目前没有任何 GitHub Release，用户无法按 README 从 Releases 下载 `.fpk`。仓库已有 `0.3.31` 候选包、SHA-256 和发布账本记录，但尚未形成远端标签、Release 页面和可匿名下载资产。

## Target End State

- GitHub 存在指向当前公开 `main` 的 `v0.3.31` Release。
- Release 同时包含 `nas-media-importer.fpk` 与 `nas-media-importer.fpk.sha256`。
- 包内版本、发布账本、文件哈希和 Release 标签一致。
- 匿名用户可访问 Release 页面并下载两个资产。

## Scope and Non-Goals

- 只发布已登记且源码指纹一致的 `0.3.31` 候选包，不修改业务代码或复用其他版本号。
- Release 明确标记为候选版，不把本地构建描述为 fnOS 真机验收通过。
- 不把 `.fpk` 提交进 Git，不修改发布账本中的 `candidate` 状态。
- 不创建 `latest verified` 或宣称所有 fnOS 机型兼容。

## Proposed Solution

复用发布账本中 SHA-256 完全匹配的现有 `0.3.31` 构建产物。先运行发布专项测试、包内容校验、源码指纹和校验文件验证，再创建 `v0.3.31` prerelease 并上传 FPK 与校验文件，最后通过 GitHub API 和匿名 HTTP 下载复核大小及哈希。

## Implementation Tasks

- [x] 注册发布需求，并确认工作树、版本、候选账本和远端 Release 状态。
- [x] 运行发布专项测试、文档检查、包内容校验、源码指纹和 SHA-256 门禁。
- [x] 编写准确的候选版发布说明，创建 `v0.3.31` prerelease 并上传两个资产。
- [x] 匿名下载远端资产，复核 HTTP、文件大小和 SHA-256 与本地候选一致。
- [x] 更新需求与计划证据，提交、推送并复核公开 Release 页面。

## Acceptance Criteria

- `gh release view v0.3.31` 返回 prerelease，标签目标等于发布时的 `main`。
- Release 资产名称精确为 `nas-media-importer.fpk` 和 `nas-media-importer.fpk.sha256`。
- 匿名下载的 FPK SHA-256 等于发布账本中的 `bb9a9a71d4d9d955a973af76931afbea4e4282ebfdc32f096c62f4d4f70c3c3d`。
- `scripts/validate_fpk.py --version 0.3.31`、发布专项测试和文档检查通过。
- 发布说明清楚区分 `LOCAL_BUILD PASS` 与 `FNOS_UAT NOT_RUN`。

## Decision Rationale

`0.3.31` 的发布输入指纹仍与当前源码一致，包哈希也已登记，因此重新递增版本或制造另一个包没有收益。使用 prerelease 能向用户提供安装验证入口，同时保持“尚待 fnOS 真机验收”的事实边界。

## Constraints and Boundaries

- 根 `VERSION` 和发布账本是版本事实源；GitHub 标签不能覆盖它们。
- 远端资产必须来自忽略的 `build/` 目录，不能加入 Git 历史。
- 上传前后都以 SHA-256 验证具体字节，不以文件名或上传成功提示代替。

## Assumptions

| Assumption | Status | Evidence |
|------------|--------|----------|
| `0.3.31` 对应当前发布输入 | Verified | `release_ledger.py preflight` 返回 `mode=rebuild` 且源码指纹一致 |
| 本地 FPK 是账本登记的候选 | Verified | 包校验通过且 SHA-256 与账本记录一致 |
| GitHub 尚无同名 Release | Verified | `gh release list` 返回空数组 |
| 候选版允许公开供用户真机验证 | Verified | 用户明确要求补齐 Releases 安装包，README 已说明候选与真机验收边界 |

## Risk Analysis

- 上传错误或损坏包：上传前校验，发布后匿名重新下载并比对哈希。
- 标签与最终文档提交错位：先完成发布准备提交，再以该 `main` 创建标签；收尾证据可后续普通提交。
- 用户误认为已真机验证：使用 prerelease，并在标题和说明显式标注候选版及 `FNOS_UAT NOT_RUN`。

## Validation Evidence

- 发布专项测试：47 项通过；文档检查：143 个活跃 Markdown 通过。
- 本地与匿名回下载 FPK 均为 11,818,856 字节，SHA-256 均为 `bb9a9a71d4d9d955a973af76931afbea4e4282ebfdc32f096c62f4d4f70c3c3d`，逐字节比较一致。
- 匿名回下载包重新通过 `validate_fpk.py --version 0.3.31`，包含 21 个外层条目和 275 个应用条目。
- `v0.3.31` 标签与发布时 `main` 同指向提交 `82012d4`；Release 为非草稿 prerelease，两个资产均处于 uploaded 状态。
- Release 页面：[fnOS 0.3.31 候选版](https://github.com/wae2855/nas_media_manage/releases/tag/v0.3.31)。
