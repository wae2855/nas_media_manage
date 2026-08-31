# Frontend Information Architecture

> status: active（2026-08-30）
> 项目保持 4 个一级空间和配置胶卷轨道，按「功能简洁化」方向持续降低默认配置复杂度；桌面与移动端共享业务语义，采用不同信息密度。

## Scope

本文件定义前端重做前的信息架构事实，目标是让新的 UI 与当前 feature-first 后端结构对齐，而不是继续围绕旧单页大文件增量堆逻辑。

## Current First-Level Areas

当前 `media_importer/webui/index.html` 实际承载 4 个一级空间：

1. `overview`
当前业务状态、真实运行进度、今日入库、最近最多 5 条业务活动、最近 12 部成功入库影片和批量执行入口。

2. `config`
配置导航壳，内部又塞入目录配置、路径规则、Provider、LLM、Prompt、Dimensions、Confidence、Source Cleaner、通知、安全和高级设置。

3. `tasks`
任务列表、状态筛选、详情查看、重试、确认、改名、重分类、删除、字幕查看。

4. `recycle`
回收站列表、筛选、恢复、永久删除、分区统计。

## Current Product IA Decision

当前保留首页、任务、回收、配置 4 个一级入口。配置内部继续使用用户认可的胶卷轨道承载开始、来源、中转、刮削、规则、自动运行、高级、完成八个阶段；关联配置在所属阶段内递进展开或使用弹窗，不再创建绕行的二级系统入口。

首次与后续目录管理都在胶卷的“存储检查”完成：来源、中转、回收、日志、海报缓存和多个片库各自形成一行，统一展示路径、挂载、容量与唯一修改动作。文件来源页只配置扫描及来源处理策略，进阶系统页只配置运行参数。系统能力不可用时仅非 fnOS 开发环境保留弹窗内手动路径输入。多片库卡片在手机端纵向堆叠，操作按钮折成两列。旧绝对路径规则需要关联多个片库时，用户可以反复“暂存并继续选择”；暂存区始终同时提供“继续添加片库”和“已选齐，确认关联”，确认期间显示检查进度，失败原因留在当前弹窗或暂存区，成功后刷新并退出关联状态。

业务能力仍按以下边界组织，但不要求扩展成 7 个一级导航：

1. 仪表盘
系统健康、队列状态、最近失败、Watcher 开关、立即扫描/批处理入口。

2. 任务工作台
任务列表、状态筛选、批量动作、任务详情抽屉或二级页。

3. 入库规则
目录配置、路径规则、命名模板、目标片库冲突确认和源文件处理策略。前台不再提供自动覆盖/质量优先策略。

4. 元数据与 AI
Provider 配置、LLM 配置、Prompt、Dimensions、Matching。

5. 源目录清理
清理策略、预览、执行记录、AI 辅助清理说明。

6. 回收站
回收站列表、筛选、恢复、永久删除、保留策略。

7. 系统与通知
服务端配置、Hermes、Watcher、权限检查、日志/诊断入口。

## Implementation Views

建议至少拆为以下页面或主视图，而不是单一 `index.html` 巨页：

| Target View | Current Source | Primary JS |
|-------------|----------------|------------|
| Dashboard | `index.html` overview blocks | `js/app.js` |
| Task List | tasks panel | `js/tasks.js` |
| Task Detail | tasks modal/actions | `js/tasks.js` |
| Import Rules | config path/import sections | `js/config.js`, `js/path-rules.js` |
| Metadata Providers & LLM | config provider/llm sections | `js/config.js` |
| Prompt Workspace | config llm-prompt section | `js/prompts.js` |
| Dimension Workspace | config dimensions section | `js/dimensions.js` |
| Matching & Scrape Preview | config matching section | `js/config.js` |
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
维度定义、Provider genres、Prompt 维度缓存、Matching 配置。

- `recycleState`
回收站列表、筛选条件、批量选中、恢复冲突结果。

- `sourceCleanerState`
清理预览、执行中状态、记录列表、AI 预览结果。

## Responsive Experience Contract

- 仅真实 `PENDING/RUNNING` 任务展示进度；待确认、失败、暂停和排队使用独立状态和下一步操作。
- 最近活动最多 5 行；最近影片最多 12 部，以任务成功完成时间排序并按作品去重。
- 任务卡在手机端优先展示海报、片名、状态、关键判断和主操作；额外判断进入详情，不得横向裁切。
- 片库冲突任务卡必须写明“现有文件未改动”；详情先展示现有/待入库两份文件，桌面双列、手机单列，替换入口二次确认且不得进入批量确认。
- 回收站在 768px 及以下改为纵向卡片，恢复入口优先，危险操作保持明确确认。
- 手机长弹窗使用动态视口高度，头部和底部操作区保持可达，正文内部滚动；弹窗打开时底部导航不遮挡内容。
- 配置胶卷在手机端可横滑，显示当前步骤计数和滑动提示；形式与桌面端一致。
- 主要触控热区约 44px；320px 以安全可用为底线，360—430px 保留主要影院视觉。

## Historical Redesign Inputs

以下是 2026-08-22 的历史重做输入；当前已拆分为 `cinema-*` 模块，维护时继续避免重新堆回单体文件：

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

## Change Gates

后续前端中改及以上需要满足以下条件：

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

- 首次配置向导能完成来源、多个目标片库、本地回收和最终检查；fnOS 内优先选择授权目录。
- 能查看任务列表并执行重试、确认、删除。
- 能编辑 Provider/LLM/Prompt/Dimensions 关键配置。
- 能执行源目录清理预览和回收站恢复。
- 移动端和桌面端均可完成核心路径，无布局遮挡。
