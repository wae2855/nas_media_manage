---
title: "旧片库规则未覆盖提示返工"
type: plan
date: 2026-08-31
status: complete
confidence: high
requirement: REQ-20260830-180954
---

# 旧片库规则未覆盖提示返工

> 后续真机评审已否决“按路径覆盖后自动关联”的产品方向；当前事实以[规则显式选择片库](../2026-08-31-explicit-rule-library-assignment/2026-08-31-fix-explicit-rule-library-assignment-plan.md)为准。本文件仅保留当时的阶段性证据。

- **Requirement**: [REQ-20260830-180954](../../tracking/requirements-board.md)
- **Status**: complete

## 问题与目标

真实 fnOS 验收中，用户暂存 5 个片库根后只看到“第 7 条旧规则不在已选择的任何片库根目录下”，无法判断遗漏的是哪类影片、哪个路径以及下一步该选什么。

本次只改进迁移前的解释和失败反馈：直接展示规则用途、旧路径和“继续添加包含该路径的片库根”动作说明。服务端仍逐条执行真实路径包含校验，任一规则未覆盖时整次保存回滚；不移动、覆盖或删除任何片库文件。

## 任务

- [x] 服务端迁移错误包含规则用途、实际路径和下一步动作，同时保持原子拒绝。
- [x] 存储检查暂存区及确认弹窗提前展示尚未覆盖的旧规则，动态响应已暂存片库根。
- [x] 补充真实 7 条旧规则场景、桌面与 390px 移动端回归。
- [x] 同步配置与前端事实文档，运行专项测试、JS/Python 检查及文档检查。
- [x] 自评审通过后将需求恢复为待验收并归档本计划。

## 完成证据

- `LOCAL_NON_UI PASS`：配置迁移、原子保存、多片库、配置视图及真实场景 91 项通过。
- `LOCAL_UI PASS`：存储目录与迁移交互 4 项通过；真实 7 条旧规则下，5 个根明确显示遗漏 `/vol3/1000/remote/movie`，补选第 6 个根后切换为“已覆盖全部旧入库路径”。
- `RESPONSIVE PASS`：1440px 与 390px 均无横向溢出；390px 下 `scrollWidth=clientWidth=390`，两个迁移动作可见，页面脚本错误为 0。
- `STATIC PASS`：Ruff、compileall、两份 JS 语法检查、`git diff --check` 与 112 个活跃文档检查通过。
- Chromium 首次在 macOS 沙箱内因 MachPort 权限无法启动；同一用例在受控沙箱外 4/4 通过，未产生业务断言失败。
- `FNOS_UAT NOT_RUN`：本轮尚未提交、构建 FPK 或安装到真实 fnOS。

## 验收标准

- 错误不再只显示“第 N 条”，而是同时显示可理解的规则用途和旧路径。
- 用户点确认前就能看到尚未覆盖的路径；全部覆盖后显示“已覆盖全部旧规则”。
- 前端提示仅作引导，服务端真实路径校验仍是最终安全边界。
- 失败不会写入部分 `library_roots`，不会改写旧绝对规则，更不会触碰影片文件。
- 桌面和 390px 宽度无横向溢出，动态内容经过 `escapeHtml`。

## 非目标

- 不自动猜测或创建片库根。
- 不自动删除、停用或改写用户的旧规则。
- 不改变影片冲突、替换或回收逻辑。

## 测试计划

- `tests/test_library_root_boundary.py`
- `tests/test_config_atomic_save.py`
- `tests/test_storage_directory_buttons_ui.py`
- `node --check media_importer/webui/js/cinema-directory-loader.js`
- `node --check media_importer/webui/js/cinema-fnos-directories.js`
- `.venv/bin/ruff check media_importer/features/configuration/library_paths.py tests/test_library_root_boundary.py`
- `python scripts/check_docs.py`
