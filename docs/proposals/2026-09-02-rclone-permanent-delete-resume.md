---
title: "rclone 来源永久删除与安全续做方案"
type: proposal
date: 2026-09-02
status: approved
confidence: high
requirement: REQ-20260902-222141
---

# rclone 来源永久删除与安全续做方案

- **Requirement**: [REQ-20260902-222141](../tracking/requirements-board.md)
- **ADR**: [ADR-0019](../decisions/0019-source-disposal-with-guarded-permanent-delete.md)
- **Plan**: [实施记录（已归档）](../_archive/2026-09-02-rclone-permanent-delete-resume/2026-09-02-fix-rclone-permanent-delete-resume-plan.md)

## 真机缺陷

fnOS `0.3.24` 的来源目录位于 `fuse.rclone`。程序已把整组来源安全重命名到任务隔离区，但在真实删除前仍用本地文件系统的 inode 稳定性复核成员；rclone 的虚拟 inode 在 rename 后可能变化，因此删除被阻断。恢复失败又继续检查已经被隔离的旧路径，导致详情只剩下“来源目录不存在”，掩盖了真正原因。

## 产品结果

- 本地盘继续使用 device + inode 强身份校验。
- 已识别的远程挂载使用挂载身份、隔离区边界和文件树快照校验，不依赖跨 rename 稳定 inode。
- 删除只发生在当前任务的 `.nas-media-delete-<id>.deleting` 隔离区内；未知文件、链接、特殊文件、挂载变化或路径越界一律停止。
- 旧版活动账本可在升级后安全续做，不要求再次复制大文件。
- 续做失败立即停下并展示原始原因，不再被后续“路径不存在”覆盖。

## 非目标

- 本次不直接操作用户 fnOS 中现存的隔离目录。
- 不清理由旧版本遗留且来源未知的 `.write_test_*` 文件。
- 不改变目标片库禁止普通删除、覆盖必须回收的安全边界。
