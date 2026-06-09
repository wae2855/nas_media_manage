---
title: "frontend: handoff prompt for final migration closeout"
type: handoff
date: 2026-06-06
status: active
confidence: high
---

# Frontend Function Migration Handoff Prompt

本文件用于把“前端重构剩余功能迁移收尾”直接交接给下一个模型执行。目标不是继续讨论方案，而是尽快完成剩余收尾工作。

## 你要接手的任务

你正在接手一个已经完成大部分展示层重构、并已完成主线功能迁移第一轮的前端项目。当前目标是：

**尽快完成前端重构剩余功能迁移，把新版前端收尾为可稳定交付的主工作界面。**

请不要把精力继续花在 Hero 海报、标题背景、视觉打磨等非阻塞项上；优先完成功能迁移收尾、旧模块收编、交互统一、代码拆分和回归。

## 当前事实

以下主线已基本完成，不要重复回到“从零迁移”的思路：

- 首页真实数据与主按钮已接线
- 任务页第一轮真实列表与主动作已接线
- 回收站第一轮真实列表与主动作已接线
- 基础配置真实保存 / 路径测试已接线
- Provider / AI 配置真实保存、测试、预览已接线
- 高级配置与模拟测试第一轮已接线
- 入库规则新增 / 编辑 / 删除第一轮已可用

当前主事实源文档是：

- [docs/plans/2026-06-06-frontend-function-migration-plan.md](/Users/wangwei/Documents/code/nas_media_manage/docs/plans/2026-06-06-frontend-function-migration-plan.md)

请优先阅读其中这两部分：

1. `Execution Progress`
2. `Remaining Work Handoff Checklist`

## 你的执行原则

1. 不要继续扩张 `cinema-app.js`
2. 不要引入新的 demo 数据或 placeholder 入口
3. 不要把旧页面 DOM 整块搬回新壳层
4. 优先替换原生 `prompt / alert`
5. 优先把提示词页、维度页从“旧全局函数 + 新壳”状态收编到更稳定的结构
6. 修改后要做最小 smoke / UI 回归
7. 每做完一阶段，都要同步更新迁移计划文档状态

## 你需要完成的事项

### 第一优先级：必须完成

按下面顺序执行：

1. 替换残留的原生 `prompt / alert`
2. 清掉新版主流程中“该操作将在后续接线完成后开放”的 fallback 入口
3. 完成提示词页迁移收尾
4. 完成维度/分类页迁移收尾
5. 清理配置模拟测试与置信度页的旧演示逻辑边界
6. 对 `cinema-app.js` 做首轮拆分
7. 回填并收口前端功能迁移计划文档状态

### 第二优先级：建议本轮一并完成

1. 任务页批量动作第一轮
2. 任务详情弹窗细节增强
3. 回收页批量恢复 / 批量清理

### 第三优先级：明确延后，不阻塞本轮收尾

以下内容除非主线全部完成，否则不要优先处理：

- Hero 海报与标题背景继续打磨
- 提示词/维度页完全重写为全新 DOM
- 更深层的设计系统抽象

## 推荐执行顺序

### Step 1

先从这里开始排查代码：

- [media_importer/webui/js/cinema-app.js](/Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/js/cinema-app.js)
- [media_importer/webui/js/prompts.js](/Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/js/prompts.js)
- [media_importer/webui/js/dimensions.js](/Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/js/dimensions.js)
- [media_importer/webui/partials/advanced-pages.html](/Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/partials/advanced-pages.html)
- [media_importer/webui/index.html](/Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/index.html)

重点先找：

- `window.prompt`
- `window.alert`
- `onclick="..."`
- `showToast("该操作将在后续接线完成后开放")`

### Step 2

优先把提示词页、维度页这种“还在新壳里跑旧交互”的页面收编掉，至少做到：

- 新页头
- 新按钮
- 新提示
- 新保存反馈
- 旧模块只做底层能力，不再承担页面主交互语气

### Step 3

在功能稳定后，立刻拆 `cinema-app.js`：

建议最小拆法：

- `cinema-shell.js`
- `cinema-dashboard.js`
- `cinema-tasks.js`
- `cinema-recycle.js`
- `cinema-config-basic.js`
- `cinema-config-advanced.js`

如果时间有限，至少先把：

- dashboard
- tasks
- recycle

中的一个或多个从 `cinema-app.js` 分离出去。

### Step 4

完成后做：

- `node --check media_importer/webui/js/*.js`
- `git diff --check`
- 最小 UI smoke
- 更新：
  - [docs/plans/2026-06-06-frontend-function-migration-plan.md](/Users/wangwei/Documents/code/nas_media_manage/docs/plans/2026-06-06-frontend-function-migration-plan.md)

## 完成判定

只有当以下条件都满足时，才能认为这轮前端重构真正收尾：

- 新版前端主入口不再依赖 demo / placeholder / prompt / alert
- 提示词页、维度页完成壳层级收编
- `cinema-app.js` 完成首轮拆分
- 迁移计划文档状态与真实代码一致
- 至少做过一轮 smoke / UI regression

## 输出要求

完成这轮工作后，请给出：

1. 已完成项清单
2. 仍未完成项清单
3. 影响范围文件列表
4. 做过的验证命令
5. 是否可以宣告“前端重构主线收尾完成”
