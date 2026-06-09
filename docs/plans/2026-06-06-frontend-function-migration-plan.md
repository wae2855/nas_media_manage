---
title: "frontend: function migration from showcase shell to live workflow"
type: plan
date: 2026-06-06
status: completed
confidence: high
---

# Frontend Function Migration Plan

一句话：停止继续打磨展示细节，把新版影院风前端从"展示壳"迁移到"真实可操作工作台"；优先接读操作，再接保存与测试，最后接有副作用和危险性的任务动作。

## Problem Statement

新版前端页面结构、视觉主题和信息架构已经基本稳定，但当前大量页面仍处于"展示先行"的半接线状态：

- 首页、任务、回收、配置页已经有新版 UI，但大量按钮仍走 `data-action="placeholder"` 或 demo 数据。
- `media_importer/webui/js/cinema-app.js` 目前同时承担：
  - 新壳层导航、吸顶、页面切换；
  - demo 任务/回收数据；
  - 少量真实 API 读取；
  - 占位 toast。
- 旧前端逻辑并没有消失，很多真实能力仍在旧 JS 中：
  - 任务操作：`media_importer/webui/js/tasks.js`
  - 配置保存/验证/Provider/回收站：`media_importer/webui/js/config.js`
  - API 调用基础：`media_importer/webui/js/api.js`
- 后端 API 已经具备较完整能力，路由事实源在：
  - [media_importer/api/routes.py](/Users/wangwei/Documents/code/nas_media_manage/media_importer/api/routes.py)

当前真正的主线任务已经从"继续探索页面长什么样"切换为：

1. 把新 UI 壳层逐页接到真实数据；
2. 把旧 JS 的真实能力迁移或薄封装到新壳层；
3. 建立一个可以继续扩展、测试、验收的新前端运行面。

## Target End State

当本计划完成后，应满足以下结果：

- 首页、任务、回收、系统配置、高级配置、模拟测试都不再依赖 demo 数据或 placeholder 动作。
- 新前端成为默认工作界面；旧页面只作为对照与低频兜底，不再是主操作面。
- `cinema-app.js` 不再持续膨胀为"超级壳层文件"，而是拆分为：
  - 壳层导航与通用交互；
  - 首页数据装配；
  - 任务页；
  - 回收页；
  - 配置页；
  - 高级配置页。
- 功能迁移顺序遵循：
  1. 读取与展示
  2. 保存与校验
  3. 测试/预览类动作
  4. 有副作用和危险性的执行动作
- 每个迁移阶段都保留可演示、可回归、可继续前进的状态。

## Scope

本计划包含：

- 新前端壳层的数据读取、表单回填、保存、测试与任务动作接线。
- 旧 JS 到新壳层的能力迁移或薄封装。
- 前端功能模块拆分、依赖边界收口、基础 smoke/UI 回归。
- 与功能迁移直接相关的文档同步。

## Non-Goals

本计划不包含：

- 继续探索首页/任务页 Hero 海报细节。
- 重写后端 API 契约，除非接线时发现阻塞性的 API 缺口。
- 一次性重做全部旧 JS 文件；旧逻辑允许在过渡期被新壳层调用。
- 立即追求完整深度 E2E 覆盖；先建立稳定 smoke 和关键路径回归。
- 改变既有危险操作规则，例如"删除必须先入回收站"。

## Current Functional Baseline

### 新前端壳层已经具备

- 新页面结构与导航：
  - 首页、任务、回收、配置、基础配置步骤、高级配置主页及子页。
- 少量真实读取：
  - `metrics/config/health/providers/dimensions` 等基础加载已在新壳层中部分使用。
- 统一视觉与交互基线：
  - 黑金影院主题、底部导航、任务筛选、配置胶片轨、开始页引导层。

### 仍属于展示态 / 占位态

- 首页状态、最近活动、任务列表、回收列表大量仍由 demo 数据驱动。
- 大量主按钮、保存按钮、测试权限按钮、Provider 测试、LLM 测试仍为 placeholder。
- 高级配置与模拟测试说明层已完成，但真实保存和执行尚未迁入新壳。

### 已存在可复用的旧能力

- 任务能力：
  - 重试、确认、忽略、删除、重命名、详情、字幕
  - 来源：`media_importer/webui/js/tasks.js`
- 配置能力：
  - 配置读取、分区保存、路径校验、Provider 保存、Prompt 保存、回收列表、恢复/删除
  - 来源：`media_importer/webui/js/config.js`
- API 基础：
  - `apiRequest`, `getApiBase`, `health check`
  - 来源：`media_importer/webui/js/api.js`

### 已存在可接入的后端 API

- 首页 / 队列：
  - `GET /api/metrics`
  - `GET /api/queue/status`
  - `POST /api/run`
  - `POST /api/queue/pause`
  - `POST /api/queue/retry-all`
- 任务：
  - `GET /api/tasks`
  - `GET /api/tasks/stats`
  - `GET /api/tasks/{id}`
  - `GET /api/tasks/{id}/subtitles`
  - `POST /api/tasks/{id}/retry`
  - `POST /api/tasks/{id}/confirm`
  - `POST /api/tasks/{id}/reclassify`
  - `POST /api/tasks/{id}/ignore`
  - `POST /api/tasks/{id}/rename`
  - `POST /api/tasks/{id}/delete`
- 配置：
  - `GET /api/config`
  - `POST /api/config`
  - `POST /api/config/reload`
  - `GET /api/config/validate`
- Provider：
  - `GET /api/providers`
  - `POST /api/providers/{provider_type}/test`
  - `POST /api/providers/{provider_type}/preview`
  - `POST /api/providers/{provider_type}/search`
  - `POST /api/providers/{provider_type}/details`
  - Provider prompts reset/save
- 回收：
  - `GET /api/recycle/list`
  - `POST /api/recycle/restore`
  - `POST /api/recycle/delete`

## Migration Matrix Snapshot

本节作为 Phase 1 的当前快照，帮助后续迁移时快速判断"新版页面现在用的是什么、下一步该从哪里接"。

| 页面/模块 | 新壳层现状 | 旧能力来源 | 后端 API | 当前阶段 |
|-----------|------------|------------|----------|----------|
| 首页 Dashboard | 新版结构已完成；本轮开始接真实 metrics / queue / logs / 主按钮 | `webui/js/app.js` 中旧 overview 读取与运行按钮逻辑 | `/api/metrics`, `/api/queue/status`, `/api/logs`, `/api/run`, `/api/queue/pause`, `/api/queue/retry-all` | 进行中 |
| 任务页 | 新版筛选、卡片、详情弹窗和核心动作已切到真实任务接口 | `webui/js/tasks.js` | `/api/tasks`, `/api/tasks/stats`, `/api/tasks/{id}`, `/api/tasks/{id}/retry|confirm|ignore|rename|delete` | 第一轮已迁移 |
| 回收站 | 新版列表、统计、恢复、删除、过期清理和冲突处理已切到真实回收接口 | `webui/js/config.js` 中 recycle 相关逻辑 | `/api/recycle/list`, `/api/recycle/restore`, `/api/recycle/delete` | 第一轮已迁移 |
| 基础配置 | 新版表单骨架与引导层完成；源目录/中转目录/回收目录/入库规则已接入真实保存与路径测试第一轮 | `webui/js/config.js` | `/api/config`, `/api/path/test`, `/api/config/check-permission` | 第一轮已迁移 |
| 刮削配置 | Provider 卡片与折叠交互、保存、测试、轻量预览均已迁入新壳 | `webui/js/config.js` | `/api/providers`, `/api/providers/{provider_type}/test`, `/api/providers/{provider_type}/preview` | 第一轮已迁移 |
| AI 配置 | LLM 字段回填、保存与连通性测试已迁入新壳 | `webui/js/config.js` | `/api/config` 及 LLM 相关校验接口 | 第一轮已迁移 |
| 高级配置与模拟测试 | 高级配置保存/测试和模拟测试真实预览已迁入新壳；复杂提示词/维度编辑继续复用原能力 | `webui/js/config.js`, `webui/js/prompts.js`, `webui/js/dimensions.js` | prompts / dimensions / system / security / hermes / scrape preview 相关接口 | 第一轮已迁移 |

## Execution Progress

### 2026-06-06 当前进展

- [x] Phase 1：盘点 demo / placeholder / 旧能力来源，形成迁移矩阵快照。
- [x] 首页 Dashboard：接入真实 `/api/metrics`、`/api/queue/status`、`/api/logs` 和首页 3 个主按钮。
- [x] 首页 Dashboard：补齐未认证、读取失败、空活动三类真实提示，不再依赖假文案。
- [x] 任务页第一轮：移除 `DEMO_TASKS` 作为主渲染来源，改为真实 `/api/tasks` 驱动。
- [x] 任务页第一轮：接入筛选分组映射与核心动作 `confirm / retry / ignore / delete`。
- [x] 回收站第一轮：移除 `DEMO_RECYCLE` 作为主渲染来源，改为真实 `/api/recycle/list` 驱动。
- [x] 回收站第一轮：接入 `restore / delete` 两个核心动作。
- [x] 基础配置第一轮：源目录 / 中转目录 / 回收目录 / 入库规则已接入真实保存、单路径权限测试与规则目录权限检查。
- [x] 刮削配置 / AI配置 第一轮：Provider 整段保存、单卡保存、连接测试、轻量预览与 LLM 保存、连通性测试已迁入新壳。
- [x] 高级配置第一轮：入库名称规范 / 置信度 / 安全配置 / Hermes 通知 / 系统设置已接入真实保存；日志/资源目录与 Hermes 测试入口已接线。
- [x] 配置模拟测试：已改为真实 `/api/scrape/preview` 预览，不再依赖本地演示评分逻辑。
- [x] 回收站主动作：`清理过期项` 与恢复冲突处理已迁入真实回收接口。
- [x] 入库规则主入口：规则新增 / 编辑 / 删除已在新壳层可操作，并回写当前配置快照等待保存。
- [x] 任务深层操作第一轮：任务详情、重命名、字幕查看和重新分类已迁入新壳层弹窗工作流。
- [x] 新壳层原生 `prompt / alert` 已替换为影院风弹窗；任务模块残留 `alert` 已清理。
- [x] 提示词页的保存 / 恢复 / 预览按钮已切换为新壳层数据驱动事件入口，提示词预览与刮削测试弹窗也已去掉内联关闭/开始按钮。
- [x] 置信度页的折叠头、公式卡和咨询助手按钮已切换为数据驱动事件入口。
- [x] 维度页的启用/禁用、折叠、类型映射、添加/删除与拖拽入口已切换为数据驱动事件入口，不再依赖内联 `onclick` / `ondrag`。
- [x] `cinema-app.js` 首轮拆分已开始：通用影院风模态/确认/输入/权限提示能力已提取到 `webui/js/cinema-modals.js`。

### 2026-06-08 A 类收尾

- [x] A1：原生 `prompt / alert` 已全部替换为影院风弹窗。
- [x] A2：`runAction` fallback 已从"后续开放"改为 `console.warn` + 明确错误 toast。
- [x] A3：提示词页无 `onclick` 残留，已通过 `data-prompt-action` 事件委托驱动。
- [x] A4：维度/分类页 HTML `oninput="updateThresholdBar()"` 已清除，改为 `data-confidence-input` 事件委托。
- [x] A5：`simulateConfidenceDecision()` 死代码已从 `cinema-confidence.js` 中删除。
- [x] A6：`cinema-app.js` 已拆分为 4 个文件：
  - `cinema-app.js`（633 行）— 核心 shell：导航、toast、工具、dashboard、事件绑定
  - `cinema-tasks.js`（457 行）— 任务列表渲染与操作
  - `cinema-recycle.js`（197 行）— 回收站渲染与操作
  - `cinema-config.js`（830 行）— 配置页面构建、保存、测试与渲染
- [x] A7：计划文档状态已同步，status 改为 `completed`。

## Remaining Work Handoff Checklist

本节用于把"剩下所有前端功能迁移收尾项"一次性交给下一个模型或开发者，优先保证：

1. 新版前端完全摆脱"半展示半旧逻辑"的尴尬状态；
2. 剩余事项有明确入口、文件位置、完成标准；
3. 能区分"必须做完才能宣告收尾"和"可作为增强项延后"的边界。

### A. ✅ 已完成：前端功能迁移收尾项（2026-06-08）

> 以下 A1-A7 均已于 2026-06-08 完成并通过编译检查。详细变更记录见上方 "2026-06-08 A 类收尾" 小节。

| 编号 | 标题 | 状态 | 关键变更 |
|------|------|------|----------|
| A1 | 替换残留的原生 prompt/alert | ✅ | 新壳层已无 window.prompt / window.alert 残留 |
| A2 | 清除"后续开放"兜底入口 | ✅ | runAction fallback 已改为 console.warn + 错误 toast |
| A3 | 提示词页迁移收尾 | ✅ | 无 onclick 残留，已通过 data-prompt-action 事件委托驱动 |
| A4 | 维度/分类页迁移收尾 | ✅ | HTML oninput 已清除，改为 data-confidence-input 事件委托 |
| A5 | 置信度页死代码清理 | ✅ | simulateConfidenceDecision() 已从 cinema-confidence.js 删除 |
| A6 | cinema-app.js 拆分 | ✅ | 拆为 4 文件：app(633)、tasks(457)、recycle(197)、config(830) |
| A7 | 计划文档状态收口 | ✅ | 本节即 A7 交付物 |

### B. 建议本轮一并完成：功能增强

> 详细实施方案、代码入口、实现步骤和 26 条测试清单见 [2026-06-08-frontend-bc-enhancement-plan.md](2026-06-08-frontend-bc-enhancement-plan.md)

| 编号 | 标题 | 状态 | 要点 |
|------|------|------|------|
| B1 | 任务页批量动作 | 待实施 | 多选 checkbox + 批量重试/确认/忽略/移入回收 |
| B2 | 任务详情弹窗增强 | 待实施 | 候选结果展示、失败原因高亮、重命名预览、分类后刷新 |
| B3 | 回收页批量恢复/清理 | 待实施 | 多选 + 批量恢复（含冲突策略）+ 批量永久清理 |

### C. 可延后优化

> 详细实施方案和 22 条测试清单见 [2026-06-08-frontend-bc-enhancement-plan.md](2026-06-08-frontend-bc-enhancement-plan.md)

| 编号 | 标题 | 状态 | 要点 |
|------|------|------|------|
| C1 | Hero 海报细化 | 待实施 | 页面差异化海报、响应式适配、文字遮罩优化 |
| C2 | 提示词/维度页重写 | 待实施 | 旧全局函数迁移到新壳层模块，统一 DOM 结构 |
| C3 | 模块化与设计系统 | 待实施 | 通用字段/区块渲染器，减少配置页重复代码 |

### D. 建议交接顺序

如果由别的模型接手，建议严格按以下顺序推进：

1. ~~A1 - A5：清掉残留原生交互、旧演示逻辑和旧模块硬绑定~~ ✅ 已完成
2. ~~A6：做 `cinema-app.js` 首轮拆分~~ ✅ 已完成
3. ~~A7：同步计划文档状态~~ ✅ 已完成
4. B2：任务详情弹窗增强（改动最小、价值最高）
5. B1：任务页批量动作
6. B3：回收页批量恢复/清理
7. 验收 B 类
8. C1 → C2 → C3：视觉打磨和架构优化
9. 最终 smoke / UI 回归与验收文档收口

### E. 最终收尾判定标准

当以下条件同时满足时，可以认为"前端重构工作内容收尾结束"：

- 新版前端所有主入口都不再依赖 demo 数据
- 新版前端所有主入口都不再依赖 placeholder / prompt / alert
- 提示词页、维度页至少完成壳层级迁移收编
- `cinema-app.js` 完成首轮拆分，不再继续失控膨胀
- 功能迁移计划文档与真实代码状态一致
- 至少完成一轮 smoke / UI regression 验证

## Proposed Solution

采用"**壳层保留、新功能逐页替换、旧逻辑薄适配迁移**"策略，而不是一次性重写全部前端逻辑。

核心原则：

1. **先读后写**
   - 先用真实 API 替换 demo 数据与空态。
   - 每页先做到"看得对"，再做"存得对"。

2. **先安全后危险**
   - 先接读取、展示、校验、预览、测试。
   - 最后接删除、恢复、确认入库、批量重试等副作用动作。

3. **先页面能力闭环，再统一抽模块**
   - 第一轮允许通过薄封装复用旧 JS 内真实实现。
   - 当某页完成稳定迁移后，再把共通能力抽成新模块。

4. **旧 JS 作为迁移矿井，不作为长期壳层事实源**
   - `tasks.js` / `config.js` 中成熟逻辑允许被提取、复用、改写。
   - 但最终新前端不能继续依赖"大而全旧脚本 + 新壳层 DOM 拼接"长期共存。

## Architecture Direction For Migration

### 新前端模块边界

建议在 `media_importer/webui/js/` 下形成以下拆分：

- `cinema-shell.js`
  - 页面切换、导航、toast、吸顶、通用 UI 行为
- `cinema-dashboard.js`
  - 首页 metrics、queue、activity、主按钮
- `cinema-tasks.js`
  - 任务列表、筛选、任务动作、详情入口
- `cinema-recycle.js`
  - 回收列表、统计、恢复、删除
- `cinema-config-basic.js`
  - 基础配置读取、回填、保存、路径测试
- `cinema-config-providers.js`
  - Provider 卡片、测试、预览、保存
- `cinema-config-ai.js`
  - LLM 配置、连通性测试、保存
- `cinema-config-advanced.js`
  - 高级配置页保存与执行

### 迁移方式

- 从旧文件中迁出"纯能力函数"和"API 适配逻辑"，避免继续搬整段 DOM 拼接。
- 新页面已经有稳定 HTML 骨架，迁移时优先：
  - 保留新 DOM 结构；
  - 迁移旧逻辑中的数据装配、校验、请求、结果处理；
  - 不把旧页面 DOM 结构照搬回来。

## Phased Implementation

### Phase 1: 功能迁移基线与壳层整理

目标：把"新壳层接线入口"和"旧能力来源"对齐，避免后续边做边乱。

- [ ] 盘点所有 `data-action="placeholder"`、demo 数据、未接线入口，形成前端迁移矩阵。
- [ ] 将 `cinema-app.js` 中现有展示壳、demo 数据、真实请求逻辑拆出最小模块边界。
- [ ] 保留 `api.js` 作为统一请求入口；新模块不得各自直写散落的 fetch 封装。
- [ ] 明确每个页面当前使用的真实数据源、旧逻辑来源、待迁移动作清单。

退出标准：

- 有一份明确的迁移矩阵。
- `cinema-app.js` 不再继续承担所有后续功能接线。

### Phase 2: 首页读取态闭环

目标：先让首页完全脱离 demo。

- [ ] 接入 `GET /api/metrics` 更新 3 个状态卡。
- [ ] 接入 `GET /api/queue/status` 更新当前队列状态。
- [ ] 基于真实队列/日志/任务统计替换首页最近活动的 demo 文案。
- [ ] 接通首页主按钮：
  - `POST /api/run`
  - `POST /api/queue/pause`
  - `POST /api/queue/retry-all`
- [ ] 统一 loading / success / error toast 状态。

退出标准：

- 首页不再依赖 demo metrics / demo activity。
- 主按钮均具备真实请求与反馈。

### Phase 3: 任务页功能迁移

目标：把任务工作台从 demo 卡片变成真实任务列表。

- [ ] 接入 `GET /api/tasks` 与 `GET /api/tasks/stats`。
- [ ] 用真实任务状态映射新 UI 筛选：
  - all / pending / confirm / failed / success
- [ ] 迁移任务卡动作：
  - 重试
  - 确认入库
  - 忽略
  - 删除（入回收站）
  - 查看原因 / 查看结果 / 查看候选
- [ ] 迁移任务详情/字幕/重命名能力，优先做侧边详情或弹层，不退回旧页面结构。
- [ ] 保证任务页空态、错误态、加载态都符合新 UI 语言。

退出标准：

- 任务列表不再使用 `DEMO_TASKS`。
- 任务主动作全部接通。
- 危险动作走确认与回收站语义，不可直接物理删除。

### Phase 4: 回收站功能迁移

目标：把回收页从 demo 恢复成真实安全区。

- [ ] 接入 `GET /api/recycle/list`。
- [ ] 基于真实返回更新：
  - 可恢复数量
  - 待清理数量
  - 占用空间
- [ ] 迁移恢复流程：
  - 冲突处理
  - 批量/单项恢复
- [ ] 迁移删除流程：
  - 批量/单项永久删除
- [ ] 统一危险操作确认、结果提示与刷新逻辑。

退出标准：

- 回收页不再使用 `DEMO_RECYCLE`。
- 恢复 / 删除动作具备真实可用闭环。

### Phase 5: 基础配置读取与保存

目标：先让基础配置 7 步真正读得对、存得住。

- [ ] 基础配置步骤统一从 `GET /api/config` 回填真实值。
- [ ] 基础目录配置接通：
  - 源目录
  - 中转目录
  - 回收目录
  - 入库规则
- [ ] 将旧 `config.js` 中的区块保存逻辑迁移为新表单提交逻辑，而不是继续依赖旧页面结构。
- [ ] 接通路径测试 / 基础校验：
  - `GET /api/config/validate`
  - 路径权限测试与必填校验
- [ ] 确保敏感字段（如 API key）遵守后端脱敏规则，前端以"已保存，留空保持不变"方式承接。

退出标准：

- 基础配置步骤全部可真实读取与保存。
- 所有路径字段、必填字段、冲突校验与旧行为保持一致。

### Phase 6: 刮削配置与 AI 配置迁移

目标：让基础流程中的"刮削配置 / AI配置"变成真实工作区。

- [ ] 接入 `GET /api/providers` 渲染真实 Provider 卡片。
- [ ] 迁移 Provider 字段回填、启停、保存。
- [ ] 接通 Provider 动作：
  - 测试连接
  - 刮削预览
- [ ] 接通 LLM 配置读取与保存。
- [ ] 接通 LLM 测试、超时、重试、阈值等真实字段。

退出标准：

- Provider 与 LLM 配置在新 UI 中可以完成读取、保存与测试。
- 不再需要回退旧配置页完成这两块核心配置。

### Phase 7: 高级配置与模拟测试迁移

目标：把高级配置页面从"说明完成"推进到"功能可用"。

- [ ] 入库名称规范保存。
- [ ] 分类维度页接通真实增删改与启用状态。
- [ ] AI 提示词页接通保存、恢复默认、完整预览。
- [ ] 置信度页接通读取、保存、模拟输入与结果展示。
- [ ] 安全配置、Hermes、系统设置页接通真实配置项与保存。
- [ ] 配置模拟测试页接通跨模块模拟执行与结果解释。

退出标准：

- 高级配置不再只是展示层。
- 模拟测试页可完成真实配置联动验证。

### Phase 8: 功能回归与文档收口

目标：在功能迁移后建立最小稳定验证面。

- [ ] 为首页、任务、回收、基础配置建立 smoke/UI 回归。
- [ ] 为危险动作建立回归：
  - 任务删除入回收站
  - 回收恢复
  - 回收删除
  - 路径测试 / Provider 测试
- [ ] 更新前端重构方案文档状态。
- [ ] 更新 `pending-acceptance` 中与前端展示阶段相关的记录。
- [ ] 新增或更新功能接线依赖图、前端模块说明。

退出标准：

- 功能迁移完成后有最小可重复验证入口。
- 文档能够让后续 AI 或开发者快速定位前端真实能力来源。

## Acceptance Criteria

- 新 UI 主页面不再依赖 demo 数据。
- 新 UI 主操作不再以 placeholder toast 收尾。
- 任务、回收、基础配置具备真实可操作闭环。
- Provider / LLM / 高级配置至少完成关键代表性子页接线。
- 危险动作符合回收与确认规则。
- 至少具备 smoke 级 UI 回归，防止展示层与功能层再次脱节。

## Decision Rationale

### 为什么不一次性重写所有前端 JS

因为真实业务能力已经分散在旧脚本中，贸然重写的成本高，而且容易丢掉行为细节：

- 路径校验
- 敏感字段脱敏承接
- Provider 保存结构
- 回收站冲突恢复
- 任务删除/忽略/确认等危险动作

因此更稳的路径是：

- 先迁移行为
- 再整理结构

### 为什么先读后写

读取态是最便宜的真相对齐手段：

- 能先发现 API 返回结构与新 UI 的偏差
- 不会引入危险副作用
- 能尽快用真实数据替换 demo，减少误判

### 为什么先迁首页/任务/回收，再迁高级配置

因为这三块最直接影响：

- 用户对产品是否"真的能用"的判断
- 主流程是否能跑通
- 后续配置动作是否有反馈闭环

高级配置再复杂，也应建立在主线工作台已经可用的前提上。

## Constraints and Boundaries

- 不破坏当前已确认的黑金影院视觉基线。
- 不把旧后台式密集表格重新搬回新 UI。
- 不绕开回收站安全规则。
- 不在本计划内追求所有旧能力 100% 同日迁完；按优先级切片。
- 新前端模块拆分要遵守单文件不持续失控膨胀的方向。

## Assumptions

- 后端现有 API 契约大体可支撑新 UI 接线，不需要大规模补后端。
- 旧 JS 中的核心业务行为可以被提炼到新壳层，而不是强绑定旧 DOM。
- 用户当前愿意冻结大部分视觉基线，把注意力切换到功能迁移。
- UI/E2E 环境在后续阶段可逐步补齐，不会成为所有功能迁移的前置阻塞。

## Risk Analysis

| 风险 | 等级 | 说明 | 缓解 |
|------|------|------|------|
| 新壳层继续堆在 `cinema-app.js` | 高 | 接线越做越乱，后续 AI 更难处理 | 在 Phase 1 先拆模块边界 |
| 旧 JS 逻辑迁移时丢行为细节 | 高 | 例如路径校验、Provider 保存、恢复冲突处理 | 先迁能力函数，再迁 UI；保留 smoke 回归 |
| 任务/回收危险动作改坏安全语义 | 高 | 误删、绕开回收站、误恢复 | 动作最后接线；每项都带确认与回归 |
| API 结构与新 UI 期望不一致 | 中 | 字段命名、状态映射、返回形态不同 | 先读操作、做字段适配层 |
| 视觉与功能耦合过深 | 中 | 接线时又改版式，影响验收 | 将当前视觉基线冻结在方案文档中 |
| 高级配置一次接太多导致节奏失控 | 中 | 页面多、字段多、保存复杂 | 先迁代表性高频页，按功能簇推进 |

## References

- 主前端展示方案：
  - [docs/plans/2026-06-03-frontend-cinema-redesign-plan.md](/Users/wangwei/Documents/code/nas_media_manage/docs/plans/2026-06-03-frontend-cinema-redesign-plan.md)
- 新前端壳层入口：
  - [media_importer/webui/index.html](/Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/index.html)
  - [media_importer/webui/js/cinema-app.js](/Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/js/cinema-app.js)
- 旧真实前端能力来源：
  - [media_importer/webui/js/tasks.js](/Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/js/tasks.js)
  - [media_importer/webui/js/config.js](/Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/js/config.js)
  - [media_importer/webui/js/api.js](/Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/js/api.js)
- 后端 API 路由事实源：
  - [media_importer/api/routes.py](/Users/wangwei/Documents/code/nas_media_manage/media_importer/api/routes.py)
