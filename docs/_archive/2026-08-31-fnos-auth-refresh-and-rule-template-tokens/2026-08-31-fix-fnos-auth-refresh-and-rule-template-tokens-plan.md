---
title: "fix: fnOS 授权即时刷新与规则模板变量助手"
type: plan
date: 2026-08-31
status: completed
confidence: high
requirement: REQ-20260831-224737
---

# fnOS 授权即时刷新与规则模板变量助手

- **Requirement**: REQ-20260831-224737
- **Proposal**: [方案](../proposals/2026-08-31-fnos-auth-refresh-and-rule-template-tokens.md)
- **Status**: completed

修复已有片库重新授权后存储列表不自动刷新的断链，并在规则编辑弹窗中提供与后端合同一致、可点击插入的模板变量。

## Problem Statement

已有目标片库通过 fnOS 系统弹窗重新授权后，前端只刷新授权面板，没有重新加载配置与 storage readiness；Toast 还在内部同步结束后才显示“正在重新检查”，用户只能手工点击“重新检查”才看到结果。

规则编辑弹窗要求用户手写 `{title_cn}`、`{year}` 等变量，但界面没有就地提示或插入能力。变量散落在后端渲染器和维度配置中，普通用户无法记忆，也容易拼错。

## Target End State

- fnOS 授权确认后立即出现持续可见的同步状态，前端自动等待授权可见并重新加载存储卡；成功、超时和失败都有明确结论。
- 规则编辑弹窗的入库路径输入框下方提供默认折叠的变量助手；展开后显示核心变量与当前已启用维度变量，点击后插入光标位置并保持输入焦点。
- 用户不需要记住占位符，界面也不暴露后端不能稳定提供的变量。
- 修复进入新的 `0.3.15` fnOS 验证包。

### Target outcome

授权动作看起来是一个连续、可等待、会自动完成的操作；规则模板编辑像使用场记标签组合路径，而不是背诵代码。

### Anti-goals

- 不在授权后静默等待，也不无限轮询 fnOS。
- 不以自动刷新为由自动修改片库路径或规则。
- 不把文件命名专用的 `{ext}`、`{quality}` 等未经路径合同确认的变量混入路径助手。
- 不用大块说明文字继续拉长规则弹窗。

## Scope and Non-Goals

### In scope

- 已有片库重新授权、新增片库授权和其他目录授权完成后的统一同步提示与 readiness 刷新。
- 有界退避轮询、按钮忙碌状态、成功/超时/失败提示。
- 核心路径变量：`{title_cn}`、`{title_en}`、`{year}`、`{media_type}`、`{season}`、`{episode}`。
- 动态生成当前启用维度的 `{dimension.<name>}` 变量。
- 点击变量在当前光标或选区插入，支持键盘操作和移动端换行布局。
- 浏览器回归、静态合同、文档与 `0.3.15` FPK。

### Non-goals

- 不修改后端模板渲染语义、路径安全边界或规则匹配顺序。
- 不新增自由表达式、条件语法或用户自定义变量。
- 不重做整个规则编辑弹窗。

## Proposed Solution

1. 将 fnOS 授权完成流拆成“等待能力可见 → 刷新配置/readiness → 展示结论”；立即设置 storage grid `aria-busy` 和持久提示，采用短间隔递增轮询并在上限后降级为可手工重试。
2. 不论授权目录是否已经存在于 `library_roots`，授权完成后都调用统一刷新；只有真正的新路径才继续打开片库命名确认弹窗。
3. 在规则模板输入框下方渲染默认折叠的变量助手；展开后显示两组紧凑按钮：核心作品变量和当前启用的分类维度变量。按钮 `data-rule-template-token` 保存真实 token，标题和辅助文案解释含义。
4. 插入函数使用 `selectionStart/selectionEnd` 替换当前选区，恢复光标与焦点，并派发 `input` 事件。

## Decision Rationale

- `loadDirectoryConfig()` 已是配置、授权与 readiness 的唯一前端刷新入口，修复应补齐调用而不是局部改卡片状态。
- fnOS 授权传播可能晚于回调，短暂退避轮询比固定 1 秒或要求用户手工刷新更可靠。
- 核心变量来自 `render_template()` 的稳定 scrape 字段；维度变量由现有 `/dimensions/enabled` 结果生成，避免两套变量清单漂移。

## Constraints and Boundaries

- 授权刷新是只读状态同步，不能保存或重写现有片库配置。
- 轮询必须有上限，页面切换或失败后必须恢复按钮状态。
- 变量按钮使用 `<button type="button">`，具备可读标签与 `aria-label`。
- 目标片库删除与覆盖硬边界不变。

## Assumptions

| Assumption | Status | Evidence |
|---|---|---|
| 手工“重新检查”能显示新权限 | Verified | 用户真机现象证明 readiness API 可返回最新状态 |
| 已有片库授权后缺少整体刷新调用 | Verified | `_completeFnosAuthorization()` 仅对新路径进入保存流，已有路径只渲染授权面板 |
| 核心变量由路径渲染器支持 | Verified | `classification_rules.render_template()` 从 scrape result 读取核心字段 |
| 动态维度变量受支持 | Verified | 渲染器显式支持 `{dimension.<name>}`，前端已有启用维度数据 |

## Risk Analysis

| Risk | Mitigation |
|---|---|
| fnOS 权限传播超过本地轮询上限 | 清楚提示“同步较慢”，恢复可操作按钮并保留手工重新检查 |
| 重复回调触发并发刷新 | 复用 state 去重，并增加单一 in-flight promise |
| Token 插入破坏选中内容或光标 | 测试空值、末尾、光标中间和选区替换 |
| 维度名称异常导致 HTML 注入 | token、标签和 aria 文案全部 escape；事件从 dataset 读取 |

## Design Contract

- 正向参考：现有规则条件 chip、黑金按钮、弹窗字段的细边框与紧凑排版。
- 反向参考：在输入框下堆叠长篇变量说明，或使用与当前产品不一致的彩色标签云。
- 结构预览：`入库路径模板 → 输入框 → 默认折叠的变量摘要 → 展开后的常用变量标签行 → 分类维度标签行（按需） → 一句点击插入提示`。
- 代表性 proof slice：打开一条规则，将光标放在 `电影/` 后点击“年份”，输入框变为 `电影/{year}`；随后模拟已有片库授权回调，界面显示同步中并自动刷新为最新状态。
- Rollout rule：桌面 1280px 与移动 390px proof slice、授权延迟/成功/超时测试通过后才构建 FPK。
- Rejection criteria：授权后仍需手工刷新；同步中无持续提示；token 只能追加到末尾；按钮提供未支持变量；移动端横向溢出。
- Required previews：规则弹窗桌面/移动截图、存储授权同步状态截图。

## Implementation Tasks

- [x] 注册需求与简短方案，记录授权刷新根因和变量合同。
- [x] 实现 fnOS 授权同步忙碌状态、有界轮询与自动刷新。
- [x] 实现规则模板核心/维度变量按钮与光标插入。
- [x] 增加授权回调、变量插入、无溢出和回归测试。
- [x] 修复既有非片库目录授权失效时仍显示“更改位置”的误导：改为“重新授权”并绑定当前路径。
- [x] 输入框即时移除开头 `/`；补充 `{resolution}` 常用变量及 ffprobe 分辨率等级渲染。
- [x] 更新配置与 fnOS 文档，完成静态、浏览器和架构检查。
- [x] 生成并验证 `0.3.15` FPK，登记 SHA-256 与 FNOS_UAT 状态。

## Execution Evidence

- 配置、安全、打包前置回归：109 passed；多片库浏览器回归：24 passed；架构护栏：18 passed；最终 FPK 合同：12 passed。
- 规则变量助手在 1280px 与 390px 真实 Chromium 中验证默认折叠、展开、光标插入、选区替换和无横向溢出。
- `0.3.15` FPK：`c16105b30f034bfa32dc85f3eb9f46d9fd809e0d80e113b432a92b7b3576a51f`；LOCAL_BUILD PASS，FNOS_UAT NOT_RUN。

## Acceptance Criteria

1. 已有片库重新授权成功后，无需点击“重新检查”，存储卡自动更新。
2. 授权开始同步后 100ms 内出现持续状态，按钮在同步期间不可重复触发。
3. 权限延迟可见时自动重试；超出上限后给出普通用户可理解的操作提示并恢复按钮。
4. 变量助手默认折叠，展开后至少显示七个核心变量（包含分辨率），点击后插入光标位置或替换选区。
5. 当前启用维度以 `{dimension.<name>}` 动态显示，停用维度不出现。
6. 变量按钮可通过键盘触发，桌面和 390px 移动端无横向溢出。
7. 后端模板渲染、路径边界、片库安全策略无行为变化。
8. `0.3.15` 真实 FPK 内容验证和摘要校验通过；FNOS_UAT 仍由用户真机确认。
9. 来源、回收等目录已有路径但授权失效时显示“重新授权”并直接补当前路径权限；授权正常时仍显示“更改位置”。
10. 规则模板输入框不保留开头 `/`；`{resolution}` 能读取文件检测产生的分辨率等级。
