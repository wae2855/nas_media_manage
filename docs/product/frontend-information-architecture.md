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

运行任务卡额外显示真实当前阶段。文件传输/校验阶段显示“已完成字节 / 总字节”和该阶段百分比；其他阶段只显示中文阶段及四段流程位置：“获取资料 → 决定去哪里 → 写入片库 → 处理来源”。中心中转概念不出现在任务或配置界面。任务页有运行项时每 2.5 秒静默刷新，页面隐藏、弹窗打开或任务已勾选时暂停。

4. `recycle`
回收站列表、筛选、恢复、永久删除、分区统计。

## Current Product IA Decision

当前保留首页、任务、回收、配置 4 个一级入口。配置内部继续使用用户认可的八格胶卷轨道，顺序为开始、存储检查、文件来源、作品识别、片库整理、自动运行、进阶设置、完成；关联配置在所属阶段内递进展开或使用弹窗，不再创建绕行的二级系统入口。

应用顶栏右侧保持单一“服务运行状态”胶囊，真实版本以低强调小字独立放在胶囊下方，全页面可见，便于截图反馈和确认升级。版本来自公开健康接口，不写死在 HTML；移动端状态文案可收起为状态点，但版本号继续可见且不得造成横向溢出。

作品识别阶段的 TMDB 卡片内置凭据说明：明确只填写 API Key（v3 auth），不填写 API Read Access Token；同时提供免费/商业边界、动态限流、官网/API 连通测试入口和 NAS 代理排查提示，避免用户离开配置流程自行猜测。

首次与后续目录管理都在胶卷的“存储检查”完成：来源、回收、日志、海报缓存和多个片库各自形成一行，统一展示路径、挂载、容量与唯一修改动作。该阶段只处理目录事实，不展示旧规则、规则异常或片库整理跳转。文件来源页只配置扫描及来源处理策略，进阶系统页只配置运行参数。系统能力不可用时仅非 fnOS 开发环境保留弹窗内手动路径输入。多片库卡片在手机端纵向堆叠，操作按钮折成两列。fnOS 上，已有路径授权失效时显示醒目的“重新授权”，直接补当前路径权限；授权正常时才显示“更改位置”并允许重新选择。系统授权返回后，列表原位显示“正在同步”、暂时禁用重复操作，并在权限可见后自动刷新；用户不需要再手工点击“重新检查”。片库根每次选择后独立保存；规则卡在“片库整理”明确显示“尚未选择片库”或失效引用，编辑弹窗保留旧路径作为参考但不预选默认片库；用户逐条选择真实片库并确认相对子目录。入库路径模板下方提供默认折叠的变量助手，用户展开后以紧凑场记标签选择常用变量与当前启用的维度变量，点击插入光标位置；常用区包含来自文件检测的“分辨率”。输入框从所选片库开始，键入或粘贴开头 `/` 会立即移除，避免到保存时才出现相对路径报错。规则可以只使用部分片库，未使用片库不产生错误。最终“配置检查”统一展示规则目标、目录权限、外部能力和自动运行结论。

“文件来源”的媒体候选过滤使用一行默认折叠摘要；普通用户只看到“已开启，通常无需修改”，展开后才出现小视频上限、主视频下限、体积比例和附加名称规则。维度卡同样使用两层信息：卡内只显示 Provider 字段、规则数和未命中策略，点击“查看与调整映射”才打开黑金全屏/宽屏弹层。国家分组默认折叠，原始值右侧直接选产品维度值，不暴露 JSON；映射值和未命中策略统一使用产品黑金下拉组件，不显示浏览器原生下拉，支持方向键、回车和 Esc，并按可用空间向上或向下展开。弹层点遮罩不关闭，保存失败保留当前输入。

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
- 固定整体 `percentage` 只用于流程位置，不能伪装成文件或耗时百分比；没有真实 `total_bytes` 时不显示进度条和 ETA。
- 最近活动最多 5 行；最近影片最多 12 部，以任务成功完成时间排序并按作品去重。
- 任务卡在手机端优先展示海报、片名、状态、关键判断和主操作；额外判断进入详情，不得横向裁切。
- 片库冲突任务卡必须写明“现有文件未改动”；详情先展示现有/待入库两份文件，桌面双列、手机单列，替换入口二次确认且不得进入批量确认。
- 活动或异常任务统一使用“结束处理”，弹窗明确选择保留新资源、移入本地回收区或已启用的永久删除；首屏固定声明目标片库受保护。运行中先显示“正在安全停止”。
- “删除记录”只出现在已结束任务，确认文案必须说明来源与片库文件均不改动；不得再用“删除任务”隐式猜测文件去向。
- 重名冲突的“保留片库”必须同时给出保留、回收本次新资源两个直接选项；永久删除仅在高风险模式已启用时出现。
- 回收站在 768px 及以下改为纵向卡片，恢复入口优先，危险操作保持明确确认。
- 手机长弹窗使用动态视口高度，头部和底部操作区保持可达，正文内部滚动；弹窗打开时底部导航不遮挡内容。
- 任务详情在 320px 起不得产生页面或弹窗横向滚动；长片名、路径、冲突说明和字幕表格必须在正文内换行，底部多个操作按钮允许换行但始终保持可点击。
- 规则模板变量在桌面与手机端都使用可换行按钮，不允许产生横向滚动；键盘触发与鼠标/触控行为一致。
- 配置胶卷在手机端可横滑，显示当前步骤计数和滑动提示；形式与桌面端一致。
- 主要触控热区约 44px；320px 以安全可用为底线，360—430px 保留主要影院视觉。

自动运行阶段采用“更改后立即生效”而非独立保存按钮。开关和轮询周期每次更改都要回读后台 watcher 状态，并用普通用户可理解的中文区分“后台服务正在运行”“已关闭”“配置开启但因存储异常未运行”。界面必须明确说明关闭桌面窗口或手机页面不会停止 fnOS 后台整理。

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

任务运行进度采用 2.5 秒条件轮询，但渲染必须按任务 ID 局部对账：未变化卡片、封面、滚动位置和已加载分页保持原状，只更新发生状态或进度变化的任务；禁止用整列表 `innerHTML` 重建制造闪烁。

3. API 依赖地图完成
见 [frontend-api-dependency-map.md](../architecture/frontend-api-dependency-map.md)。

4. UI/E2E 验收方式冻结
至少确认 smoke、主流程、错误态、移动端布局四类验收。

## Acceptance Baseline

新前端第一阶段至少覆盖：

- 首次配置向导能完成来源、多个目标片库、本地回收和最终检查；fnOS 内优先选择授权目录。
- 能查看任务列表并执行重试、确认、结束处理、明确来源去向和只删除记录。
- 能编辑 Provider/LLM/Prompt/Dimensions 关键配置。
- 能执行源目录清理预览和回收站恢复。
- 移动端和桌面端均可完成核心路径，无布局遮挡。
