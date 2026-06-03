# Frontend Information Architecture

## Scope

本文件定义前端重做前的信息架构事实，目标是让新的 UI 与当前 feature-first 后端结构对齐，而不是继续围绕旧单页大文件增量堆逻辑。

## Current First-Level Areas

当前 `media_importer/webui/index.html` 实际承载 4 个一级空间：

1. `overview`
当前运行状态、健康检查、Watcher 状态、批量执行入口、首次引导。

2. `config`
配置导航壳，内部又塞入目录配置、路径规则、Provider、LLM、Prompt、Dimensions、Confidence、Source Cleaner、通知、安全和高级设置。

3. `tasks`
任务列表、状态筛选、详情查看、重试、确认、改名、重分类、删除、字幕查看。

4. `recycle`
回收站列表、筛选、恢复、永久删除、分区统计。

## Recommended Target IA

前端重做时建议拆成 7 个稳定工作区，而不是继续把所有能力塞进 `config`：

1. 仪表盘
系统健康、队列状态、最近失败、Watcher 开关、立即扫描/批处理入口。

2. 任务工作台
任务列表、状态筛选、批量动作、任务详情抽屉或二级页。

3. 入库规则
目录配置、路径规则、命名模板、去重策略、源文件处理策略。

4. 元数据与 AI
Provider 配置、LLM 配置、Prompt、Dimensions、Confidence。

5. 源目录清理
清理策略、预览、执行记录、AI 辅助清理说明。

6. 回收站
回收站列表、筛选、恢复、永久删除、保留策略。

7. 系统与通知
服务端配置、Hermes、Watcher、权限检查、日志/诊断入口。

## Page Split Recommendation

建议至少拆为以下页面或主视图，而不是单一 `index.html` 巨页：

| Target View | Current Source | Primary JS |
|-------------|----------------|------------|
| Dashboard | `index.html` overview blocks | `js/app.js` |
| Task List | tasks panel | `js/tasks.js` |
| Task Detail | tasks modal/actions | `js/tasks.js`, `js/confidence-detail.js` |
| Import Rules | config path/import sections | `js/config.js`, `js/path-rules.js` |
| Metadata Providers & LLM | config provider/llm sections | `js/config.js` |
| Prompt Workspace | config llm-prompt section | `js/prompts.js` |
| Dimension Workspace | config dimensions section | `js/dimensions.js` |
| Confidence Workspace | config confidence section | `js/config.js`, `js/confidence-detail.js` |
| Source Cleaner | config source_cleaner section | `js/config.js` |
| Recycle | recycle panel | `js/config.js` |

## Shared State Model

前端重做前应固定以下共享状态边界：

- `systemState`
健康检查、metrics、watcher 状态、运行按钮 loading 状态。

- `taskState`
任务列表分页、任务筛选、任务详情、任务动作 loading/error。

- `configState`
配置快照、未保存改动、分区权限检查结果、Provider/Prompt 临时编辑状态。

- `metadataState`
维度定义、Provider genres、Prompt 维度缓存、Confidence 配置。

- `recycleState`
回收站列表、筛选条件、批量选中、恢复冲突结果。

- `sourceCleanerState`
清理预览、执行中状态、记录列表、AI 预览结果。

## Redesign Inputs

当前应视为重做输入、而不是继续局部修补的超 500 行前端文件：

- `media_importer/webui/index.html` — 2048 行
- `media_importer/webui/js/config.js` — 2592 行
- `media_importer/webui/js/tasks.js` — 1140 行
- `media_importer/webui/js/dimensions.js` — 974 行
- `media_importer/webui/css/config.css` — 2217 行
- `media_importer/webui/css/layout.css` — 1460 行
- `media_importer/webui/css/tasks.css` — 1314 行
- `media_importer/webui/css/dimensions.css` — 814 行
- `media_importer/webui/css/base.css` — 654 行
- `media_importer/webui/css/components.css` — 587 行

这些文件后续应以页面拆分、状态拆分、样式拆分的方式处理，不再继续把新增需求直接压进原文件。

## Pre-Start Gates

前端正式开工前需要满足以下条件：

1. 页面拆分方案冻结
至少确认 Dashboard、Task List、Task Detail、Import Rules、Metadata & AI、Recycle 的边界。

2. 状态模型冻结
明确哪些状态由页面局部持有，哪些状态属于全局共享。

3. API 依赖地图完成
见 [frontend-api-dependency-map.md](../architecture/frontend-api-dependency-map.md)。

4. UI/E2E 验收方式冻结
至少确认 smoke、主流程、错误态、移动端布局四类验收。

## Acceptance Baseline

新前端第一阶段至少覆盖：

- 首次配置向导能完成基础配置。
- 能查看任务列表并执行重试、确认、删除。
- 能编辑 Provider/LLM/Prompt/Dimensions 关键配置。
- 能执行源目录清理预览和回收站恢复。
- 移动端和桌面端均可完成核心路径，无布局遮挡。
