---
title: "frontend: cinema mobile-first redesign"
type: plan
date: 2026-06-03
status: in_progress
confidence: medium
---

# Frontend Cinema Redesign Plan

一句话：基于已确认的黑金影院风格原型，重做前端展示层和页面结构；先让用户逐页验收视觉与信息架构，再接功能和补 UI/E2E。

## Background

当前前端仍是旧单页管理台形态，灰蓝色后台观感明显，且 `index.html`、`config.js`、`tasks.js` 和多份 CSS 超过 500 行。用户已确认新版方向：

- 黑色 + 金色影院主题。
- 写实海报墙氛围。
- 移动端优先。
- 首页大卡片入口。
- 展示先确认，功能后统一接线。

参考原型：

- `docs/prototypes/cinema-dashboard-demo.html`
- `docs/prototypes/cinema-task-list-demo.html`
- `docs/prototypes/cinema-recycle-demo.html`
- `docs/prototypes/cinema-config-demo.html`
- `docs/prototypes/cinema-config-directory-demo.html`

## Goals

- 真实前端采用黑金影院主题，整体替换旧灰蓝管理台观感。
- 页面结构从旧 `overview/config/tasks/recycle` 重组为移动优先的页面入口。
- 首页只保留最关键的状态、快速动作、三大入口和最近活动。
- 系统配置页按初级用户视角组织：先 01-04 主步骤，再展开 05-11 更多配置。
- 先完成展示和导航，允许用户逐页对照旧界面验收内容取舍。
- 功能接线和深层 UI/E2E 在展示结构确认后统一完成。

## Non-Goals

- 不在第一阶段一次接完所有 API 功能。
- 不在第一阶段重写后端 API。
- 不保留旧后台式密集表格布局作为主体验。
- 不继续向旧大文件追加复杂逻辑；新前端应按页面、状态和样式拆分。

## Design Decisions

已确认：

- 首页顶部保留写实海报墙/私人影院氛围。
- 首页顶部按钮为：立即扫描、暂停队列、重试失败。
- 首页状态卡为：待处理、需要确认、今日入库。
- 首页入口卡为：任务列表、回收站、系统配置。
- 首页保留最近活动。
- 首页不展示系统健康，移动到系统页。
- 移动端底部导航固定 5 项：首页、任务、规则、AI、系统。
- 系统配置首页默认展示 01-04：目录配置、影视刮削配置、AI 配置、定时任务。
- 更多配置项通过向下提示按钮展开，展开后按钮消失，并显示 05-11 一行卡。
- 配置卡片点击后进入独立页面，不在配置首页内锚点跳转。

## Target Pages

| Page | Purpose | First Delivery |
|------|---------|----------------|
| Dashboard | 首页状态、快速动作、三入口、最近活动 | Static + API-light |
| Task List | 任务卡片列表、状态筛选、任务入口动作 | Static first, API later |
| Task Detail | 确认、改名、重试、忽略、删除、字幕和置信度详情 | Later functional slice |
| Recycle | 回收文件卡片、恢复、删除、来源信息 | Static first, API later |
| System Config | 01-04 主步骤 + 更多配置入口 | Static first |
| Directory Config | 源目录、中转目录、回收站目录、入库规则 | Static first, config API later |
| Metadata Config | 旧 AI刮削 / 元数据源配置承接页 | Static skeleton, API later |
| AI Config | 旧 AI刮削 / LLM配置承接页 | Static skeleton, API later |
| Schedule Config | 旧高级配置 / 轮询监控配置承接页 | Static skeleton, API later |
| More Config Pages | 名称规范、分类维度、提示词、置信度、安全、Hermes、系统设置 | Static skeleton, API later |

## Implementation Phases

### Phase 1: 计划与视觉冻结

- [x] 用户评审并确认本计划。
- [x] 用户确认当前 demo 作为第一版视觉基线。
- [x] 将原型链接登记到前端待办文档。
- [x] 明确第一阶段只做展示壳，不做完整功能接线。

验收方式：

- 用户确认黑金影院主题和首页/配置页结构。

### Phase 2: 新前端壳层落地

- [x] 建立新版前端目录拆分，避免继续堆旧大文件。
- [x] 建立共享主题 token、基础布局、底部移动导航、卡片组件样式。
- [x] 将 Dashboard 静态结构迁入真实 `webui`。
- [x] 将 Task List、Recycle、System Config、Directory Config 静态页面迁入真实 `webui`。
- [x] 旧功能入口暂时可通过占位保留，后续逐页接线。

验收方式：

- 用户在真实应用 `localhost:9855` 查看新版页面。
- 桌面和移动端无文字溢出、卡片过大或遮挡。
- 首页、任务、回收站、系统配置、目录配置可导航。

### Phase 3: 展示内容逐页验收

- [x] 为配置 02-11 建立独立承接页骨架，便于逐页验收。
- [ ] 首页展示内容对照旧 overview 做取舍验收。
- [ ] 任务列表展示内容对照旧任务页做取舍验收。
- [ ] 回收站展示内容对照旧回收站做取舍验收。
- [ ] 系统配置入口对照旧 config 分组做取舍验收。
- [ ] 目录配置内容对照旧目录/路径配置做取舍验收。
- [ ] 把用户确认删除、移动或保留的内容写入前端方案文档。

验收方式：

- 每页由用户确认“保留 / 移走 / 删除 / 待补充”。
- 未确认内容不得直接删除功能，只能隐藏、降级或保留 fallback。

### Phase 4: 功能接线

- [ ] 首页接入运行状态、任务统计、当前处理、最近活动。
- [ ] 首页按钮接入扫描、暂停队列、重试失败。
- [ ] 任务列表接入任务列表、筛选、基础动作入口。
- [ ] 回收站接入列表、恢复、永久删除。
- [ ] 配置页接入 config 读取、保存、权限检查和路径测试。
- [ ] Provider、LLM、Prompt、Dimensions、Confidence 等复杂配置逐页接入。

验收方式：

- API smoke 通过。
- 核心操作有 loading、成功、失败状态。
- 旧功能无不可达入口。

### Phase 5: UI/E2E 与收口

- [ ] 建立新版 UI smoke：Dashboard、Task List、Recycle、System Config。
- [ ] 建立移动端截图/布局测试。
- [ ] 建立核心流程 E2E：扫描、任务操作、配置保存、回收站恢复。
- [ ] 更新 `docs/product/frontend-information-architecture.md`。
- [ ] 更新 `docs/architecture/frontend-api-dependency-map.md`。
- [ ] 更新 `docs/tracking/pending-acceptance.md`。

验收方式：

- Playwright 桌面和移动端验证通过。
- 用户完成产品全流程验收后，关闭前期延期验收项。

## File Strategy

建议新结构：

```text
media_importer/webui/
├── index.html
├── css/
│   ├── tokens.css
│   ├── layout.css
│   ├── components.css
│   └── pages/
├── js/
│   ├── app.js
│   ├── shared/
│   └── pages/
└── assets/
```

原则：

- 单文件建议不超过 500 行。
- 共享样式只放 tokens、布局、基础组件。
- 页面逻辑放 `js/pages/`，不要集中到一个大 `config.js`。
- API 调用集中到 `js/shared/api/`。

## Testing Plan

每阶段至少运行：

- `git diff --check`
- `python3 -m pytest tests/test_architecture_guards.py`

功能接线后运行：

- `python3 -m pytest tests/`
- 新增/更新 Playwright UI tests。
- 桌面与移动端截图检查。

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| 展示重做时遗漏旧功能 | 高 | 逐页对照旧界面验收，功能未确认前保留 fallback |
| 配置页内容复杂导致再次膨胀 | 高 | 入口页 + 独立子页，不在一个页面塞完 |
| 移动端卡片过大或溢出 | 中 | 每阶段做移动端截图和 Playwright 检查 |
| 先做展示导致功能暂不可用 | 中 | 明确 Phase 2 为展示壳，Phase 4 统一接线 |
| 旧测试不适配新 UI | 中 | 先保留 API/后端测试，UI 测试在新版稳定后重写 |

## User Review Checklist

用户评审本计划时重点确认：

- 是否接受“展示先行、功能后接线”。
- Phase 2 是否只做真实前端壳层和静态页面。
- 页面迁移顺序是否按 Dashboard → Task List → Recycle → System Config → Directory Config。
- 配置页是否继续采用“主步骤 + 更多展开 + 独立子页”。
- 是否允许旧功能在过渡阶段以 fallback 或占位保留。
