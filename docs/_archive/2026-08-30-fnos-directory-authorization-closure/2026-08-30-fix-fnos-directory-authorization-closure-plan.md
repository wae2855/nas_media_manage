---
title: "fix: fnOS 目录授权闭环"
type: plan
date: 2026-08-30
status: completed
brainstorm: docs/brainstorms/2026-08-30-fnos-first-run-multi-library-brainstorm.md
confidence: high
requirement: REQ-20260830-180954
---

# fnOS 目录授权闭环

把“保存目录路径”和“fnOS 为应用账号写入 ACL”合并为同一条首次使用流程；没有真实系统授权时，任何外部目录都不能被当作可用配置。

## Problem Statement

0.3.4 把来源、多个片库和回收目录移动到首次 Web 启动，但前端只查询 `trim.file.getSharedAccessibleFolders`，没有完成 `pickSharedFile` / `authorizeSharedFile` 授权动作。卸载重装后 YAML 可能保留旧路径，而 fnOS 应用授权记录已经清空，形成“界面有路径、应用账号无 ACL”的假配置。当前安装包测试还把目录字段不存在视为成功，却没有验证授权闭环。

## Target End State

- fnOS 管理员首次打开应用时，在现有“存储检查”胶卷阶段直接完成系统目录授权和角色分配。
- 来源、片库和回收目录只有位于 fnOS 已授权根下才能保存；配置值不再冒充授权事实。
- 卸载重装保留旧路径时，界面逐项显示“需要重新授权”，管理员不必重新输入路径。
- 多个片库可一次授权后继续命名、设默认和绑定规则；回收目录继续强制本地且可写。
- 普通浏览器保留手填能力，但明确标记为非 fnOS 降级路径；fnOS 环境不允许绕过系统授权。

## Target Outcome

用户感受到的是一个短而明确的安装收尾流程：先让 fnOS 真正授权，再告诉应用每个目录承担什么角色，最后统一检查。页面继续使用现有深色影院、胶卷轨道与金色状态语言，不新增第二套导航。

## Anti-goals

- 不把安装向导文本框恢复成“目录选择器”；它不能写 ACL。
- 不让应用以 root 运行，也不通过扩大系统用户组绕过 fnOS 授权。
- 不自动授权用户未确认的路径，不把 token 或授权结果写入 YAML。
- 不在回收目录使用远程挂载，不因挂载失效创建同名本地目录。
- 不引入前端框架、npm 运行依赖或来源/许可证不明确的 vendored SDK。

## Proposed Solution

1. 保留 `micro_app=true` 和 `trim.file.sharedAccess`，manifest 显式声明 `disable_authorization_path=false`。
2. 复用 fnOS 官方应用授权路由：管理员点击后打开原生目录选择器；新增独立回调页，校验 `state` 和同源 `postMessage`，然后刷新后端授权目录。移动端或 opener 不可用时保留“刷新授权状态”和返回提示。
3. 在“存储检查”顶部增加三段式授权面板：来源（单目录）、目标片库（多目录）、本地回收（单目录）。它是现有胶卷阶段的内嵌区域，不增加新页面。
4. 已保存但未授权的路径显示“重新授权”按钮，使用已知路径授权流程；新目录从系统选择器返回后再进入角色配置。
5. 服务端在 fnOS 授权 API 可用时，对来源、片库根和回收目录执行授权根 containment 校验；本地开发/普通浏览器仍走原有存在性、权限和存储身份校验。
6. readiness 同时展示“已授权/未授权”和真实读写结果；任一必需目录未授权、不可访问或不满足角色能力时继续 BLOCKED。

## Decision Rationale

fnOS 安装向导只收集静态字段，不能授予应用用户 ACL；恢复文本框会再次制造假成功。官方共享授权流程能够由管理员明确确认并让系统写 ACL，且现有包已具备 Scope、微应用宿主和后端查询能力，缺口集中在前端发起/回调及服务端保存门禁。使用官方路由流程可保持项目零依赖前端边界，也避免引入许可证未明确的 SDK 分发文件。

## Constraints and Boundaries

- 前端继续使用原生 HTML/CSS/JS；新样式进入 `cinema-config.css`，不新增 CSS 文件。
- 动态目录必须 `escapeHtml`；回调只接受同源消息并校验一次性 `state`。
- 授权动作只能由管理员显式点击触发；页面加载不能自动弹窗。
- 配置仍保存路径和角色，不保存 ACL、fnOS token 或用户身份。
- watcher、入库、清理和恢复继续受 storage readiness 门禁。

## Assumptions

| Assumption | Status | Evidence |
|---|---|---|
| fnOS 静态安装向导不能完成目录 ACL 授权 | Verified | 官方 wizard 字段合同与 0.3.4 真机安装行为 |
| `pickSharedFile` / 应用授权路由会由系统写入应用账号 ACL | Verified | fnOS 官方授权概览和 shared-access 文档 |
| 当前包具备调用授权能力的宿主条件 | Verified | `micro_app=true`、`trim.file.sharedAccess`、fnOS 1.2.0401 真机 |
| 卸载重装可能保留 YAML 但清空应用授权 | Verified | 0.3.4 真机：配置路径仍在，应用设置显示“暂无授权记录” |
| 授权根可以安全覆盖其下角色子目录 | Verified | 后端按规范化路径和 `commonpath` 做 containment；仍需实际权限测试 |

## Risk Analysis

- 弹窗/新标签回调在移动端不稳定：回调页提供明确完成状态，主页面保留刷新按钮；不依赖 `window.close()` 成功。
- 旧路径位于已授权父目录下：containment 识别为已授权，避免重复授权。
- 用户授权过宽目录：UI 提醒按最小目录授权，服务端只允许配置显式角色路径，不扫描授权根的其他内容。
- 授权后仍缺写权限或挂载离线：授权不是 readiness 的替代，继续实测读写、挂载身份和容量。
- 非管理员操作：展示“需要管理员完成授权”，不降级成手填绕过。

## Subjective Contract and Preview Gate

- 正向参考：现有“存储检查”状态卡、胶卷阶段导航和金色影院主题。
- 反向参考：独立设置首页、通用白色向导、路径文本框堆叠、授权完成但无状态反馈。
- 代表性 proof slice：先完成“来源目录”授权卡、回调和保存门禁，在 1440px 与 390px 截图中验证层级、文案和无横向溢出，再复用到多片库与回收。
- Rollout rule：来源授权的模拟回调、服务端 containment 和浏览器视觉检查通过后，才扩展至片库与回收。
- Rejection criteria：用户仍需复制路径、fnOS 下可保存未授权路径、授权后必须重开整个应用、移动端按钮溢出、出现第二套导航，任一项成立即退回修改。
- Preview reviewer：AI 先完成桌面/移动双端自评审；真实 fnOS 原生授权弹窗由用户最终验收。

## Phased Implementation

### Phase 1 — 授权契约与 proof slice

- [x] 将需求退回 `in_progress`，修订 ADR-0017/架构说明，明确 ACL 是独立系统事实。
- [x] 实现安全授权路由、回调页、一次性 state 和来源目录授权卡；补浏览器模拟回调测试。
- [x] 服务端增加授权根 containment 与来源保存门禁；完成来源 proof slice 的桌面/移动预览。

Exit：来源目录只能在授权后保存；回调后无需手工复制路径，双端无布局回归。

### Phase 2 — 多片库、回收与重装恢复

- [x] 把同一授权模式扩展到多个片库根和本地回收目录，保留角色专属校验。
- [x] 已配置但失去授权的路径提供逐项“重新授权”；授权状态进入 storage readiness。
- [x] fnOS 环境禁止未授权手填，非 fnOS 降级文案与行为保持可用。

Exit：三类目录的路径、ACL、角色和 readiness 形成闭环；旧路径可重新授权。

### Phase 3 — 打包、回归和候选包

- [x] 显式声明授权入口，修订安装向导文案、FPK validator、打包回归和发布文档。
- [x] 运行定向测试、架构护栏、非 UI 全量回归、JS/Shell/Python 检查和桌面/移动浏览器冒烟。
- [x] 构建下一版 FPK 并校验结构与 SHA-256；归档计划并转入真实 fnOS 验收。

## Completion Evidence

- 定向目录/保存/打包合同：32 passed；后续 fnOS 部分宿主信号用例补充后同组仍通过。
- 非 UI 回归：753 passed。
- UI 回归：44 passed，16 个需外部 UI 标志的用例按测试合同 skipped。
- 架构护栏：18 passed；文档检查 110 个活跃 Markdown 全部通过；Ruff、compileall、JS 语法与 diff whitespace 检查通过。
- Playwright proof：1440×1000 与 390×844 均无横向溢出、无控制台错误；成功回调后 `/vol1/new-source` 保留为草稿并立即显示已授权。
- 候选包：`0.3.5`，SHA-256 `d1d3d4fc6f549e21e82e74ad6fb7141e57f10b1f9d21f63867a52503f781bfeb`；manifest 与包内回调/前后端授权文件验证通过。
- 未执行：真实 fnOS 0.3.5 卸载重装及原生授权弹窗业务验收。

Exit：本地候选包可交付；不在本任务中擅自卸载、重装、推送或修改 fnOS 目录授权。

## Acceptance Criteria

- fnOS 首次使用可从应用内打开原生选择器，授权后路径立即出现在对应角色中。
- `GET /config/fnos-folders` 返回空列表时，fnOS 页面不得把旧路径标为可用；旧路径提供重新授权。
- 来源、每个启用片库根、回收目录必须位于至少一个已授权根内；不满足时服务端拒绝保存并给出中文修复指引。
- 片库至少支持五个授权根；回收目录远程或不可写时无法完成开场检查。
- 回调拒绝错误 origin/state；token 不进入前端、日志或配置。
- 全新安装与卸载重装状态均由测试覆盖；候选 FPK 显式保留授权设置入口。

## References

- [头脑风暴](../brainstorms/2026-08-30-fnos-first-run-multi-library-brainstorm.md)
- [提案](../proposals/2026-08-30-fnos-first-run-multi-library.md)
- [ADR-0017](../decisions/0017-fnos-first-run-directory-authorization.md)
- [前端标准](../standards/frontend.md)
- fnOS 官方：`/api/authorization/overview`、`/api/authorization/shared-access`、`/docs/core-concepts/wizard`
