---
title: "frontend: B/C 类功能增强与优化详细计划"
type: plan
date: 2026-06-08
status: approved
confidence: high
parent: plans/2026-06-06-frontend-function-migration-plan.md
req: REQ-20260608-BC001
---

# Frontend B/C 类功能增强与优化计划

本文档为前端功能迁移计划 B 类（功能增强）和 C 类（可延后优化）的详细实施方案，含每项任务的代码入口、实现步骤、验收标准和测试清单。

父计划：[2026-06-06-frontend-function-migration-plan.md](2026-06-06-frontend-function-migration-plan.md)

## 现状基线

### 后端 API 能力盘点

| API | 方法 | 当前支持 | 说明 |
|-----|------|----------|------|
| `/api/tasks` | GET | ✅ | `status`/`limit`/`offset` 参数筛选 |
| `/api/tasks/stats` | GET | ✅ | 各状态计数统计 |
| `/api/tasks/{id}/retry` | POST | ✅ | 单任务重试 |
| `/api/tasks/{id}/confirm` | POST | ✅ | 单任务确认 |
| `/api/tasks/{id}/ignore` | POST | ✅ | 单任务忽略 |
| `/api/tasks/{id}/delete` | POST | ✅ | 单任务删除（入回收站） |
| `/api/tasks/{id}/rename` | POST | ✅ | 单任务重命名 |
| `/api/tasks/{id}/reclassify` | POST | ✅ | 单任务重新分类 |
| `/api/tasks/{id}/subtitles` | GET | ✅ | 单任务字幕列表 |
| `/api/tasks/confirm-all` | POST | ✅ | 全部确认（已有后端） |
| `/api/tasks/clear` | POST | ✅ | 按状态批量清除（`status` 参数） |
| `/api/queue/retry-all` | POST | ✅ | 重试全部失败 |
| `/api/recycle/list` | GET | ✅ | `limit`/`offset` 参数 |
| `/api/recycle/restore` | POST | ✅ | `items[]` + `conflict_mode` 支持多项目 |
| `/api/recycle/delete` | POST | ✅ | `items[]` 支持多项目 |

### 前端模块现状

| 文件 | 行数 | 职责 |
|------|------|------|
| `cinema-app.js` | 633 | 核心壳层、导航、事件绑定协调器 |
| `cinema-tasks.js` | 457 | 任务卡片渲染、筛选、单任务动作 |
| `cinema-recycle.js` | 197 | 回收卡片渲染、单项目动作 |
| `cinema-config.js` | 830 | 配置页面构建、保存、测试 |
| `cinema-modals.js` | — | 通用模态/确认/输入弹窗 |
| `cinema-confidence.js` | — | 置信度页折叠头、公式卡、阈值条 |
| `index.html` | — | 主页面、script 加载顺序 |

### 关键发现

1. **后端已支持批量 API**：`/api/recycle/restore` 和 `/api/recycle/delete` 的 `items` 字段接受数组；`/api/queue/retry-all` 已有全局重试；`/api/tasks/confirm-all` 已有全部确认；`/api/tasks/clear` 可按状态批量清除。
2. **前端无多选机制**：任务卡和回收卡目前都没有 checkbox / 多选 UI。
3. **任务详情弹窗**已有候选维度表和字幕表，但缺少候选结果展示、失败原因区分和重命名预览。
4. **CSS 变量体系**已建立 Hero 海报的完整变量层（`--hero-poster-image`、`--hero-text-safe-mask` 等），可按页定制。
5. **prompts.js / dimensions.js** 仍以旧全局函数方式工作，新壳层通过事件委托桥接。

---

## B 类：功能增强（建议本轮完成）

### B1. 任务页批量动作

#### 目标

为任务工作台增加多选能力和批量操作入口，至少覆盖"批量重试"和"批量移入回收"两个高频场景。

#### 涉及文件

| 文件 | 变更类型 |
|------|----------|
| `media_importer/webui/js/cinema-tasks.js` | 修改：增加多选状态、批量动作函数 |
| `media_importer/webui/js/cinema-app.js` | 修改：事件绑定增加批量入口 |
| `media_importer/webui/index.html` | 修改：任务面板顶部增加批量工具栏 |
| `media_importer/webui/css/cinema-pages.css` | 修改：批量工具栏和多选 checkbox 样式 |

#### 实现步骤

**B1-1. 多选 UI 基础**

1. 在 `index.html` 任务面板区域 `#task-list` 上方增加批量工具栏容器：
   - "全选当前筛选" checkbox
   - 已选计数标签
   - "批量重试" 按钮（仅 `failed` 筛选可见）
   - "批量确认" 按钮（仅 `confirm` 筛选可见）
   - "批量忽略" 按钮（仅 `confirm`/`failed` 筛选可见）
   - "批量移入回收" 按钮
2. 在 `cinema-tasks.js` 的 `renderTaskCard()` 中为每张卡片增加 checkbox：
   - `<input type="checkbox" data-task-select="{taskId}">` 放在 `.task-body` 左侧
3. 新增全局状态变量 `selectedTaskIds = new Set()`
4. 新增函数：
   - `toggleTaskSelect(taskId)` — 切换选中状态
   - `selectAllTasks()` — 全选当前筛选下的所有任务
   - `clearTaskSelection()` — 清空选中
   - `updateBatchToolbar()` — 根据选中数量和当前筛选更新工具栏按钮可见性和计数
5. 在 `renderTaskList()` 结尾调用 `updateBatchToolbar()` 同步 UI

**B1-2. 批量动作执行**

6. 新增 `performBatchTaskAction(action)` 函数：
   - `batch-retry`：对选中任务逐个调用 `POST /api/tasks/{id}/retry`，汇总结果
   - `batch-confirm`：调用 `POST /api/tasks/confirm-all`（后端已有此 API）
   - `batch-ignore`：对选中任务逐个调用 `POST /api/tasks/{id}/ignore`，汇总结果
   - `batch-delete`：弹出确认弹窗，对选中任务逐个调用 `POST /api/tasks/{id}/delete`，汇总结果
7. 批量执行结束后：
   - 显示汇总 toast："成功 N 项，失败 M 项"
   - 清空选中状态
   - 刷新任务列表
8. 在 `cinema-app.js` 的 `bindEvents()` 中注册 `[data-batch-task-action]` 事件委托

**B1-3. 后端补充（如需）**

- 当前后端没有 `POST /api/tasks/batch-retry`（传一组 id）的 API。
- **策略**：前端采用 `Promise.allSettled()` 并行逐个调用单任务 API，避免新增后端接口。
- 若后续批量操作成为性能瓶颈，再考虑新增后端批量 API。

#### 验收标准

- 任务卡片左侧出现 checkbox，点击可选中/取消
- 批量工具栏显示选中数量，按钮按筛选条件智能显隐
- 批量重试至少在 `failed` 筛选下可执行
- 批量移入回收前弹出确认弹窗
- 批量操作完成后显示汇总结果 toast
- 清空筛选或刷新后选中状态自动清除

#### 测试清单

| # | 测试项 | 类型 | 优先级 |
|---|--------|------|--------|
| B1-T1 | 点击任务卡片 checkbox 选中/取消，选中计数更新 | 单元/手动 | P0 |
| B1-T2 | "全选" checkbox 勾选后所有当前筛选任务被选中 | 手动 | P0 |
| B1-T3 | 切换筛选标签后选中状态清空，工具栏重置 | 手动 | P0 |
| B1-T4 | `failed` 筛选下"批量重试"按钮可见，其他筛选下隐藏 | 手动 | P1 |
| B1-T5 | 批量重试执行后 toast 显示"成功 N / 失败 M" | 手动 | P0 |
| B1-T6 | 批量移入回收前弹出确认弹窗，确认后执行 | 手动 | P0 |
| B1-T7 | 批量操作执行中按钮显示 loading 状态，不可重复点击 | 手动 | P1 |
| B1-T8 | 选中 0 项时批量按钮 disabled | 手动 | P1 |
| B1-T9 | 批量确认调用 `POST /api/tasks/confirm-all` | 手动 | P1 |
| B1-T10 | `cinema-tasks.js` 行数不超过 500 行 | 代码检查 | P1 |

---

### B2. 任务详情弹窗细节增强

#### 目标

增强 `openTaskDetail()` 弹窗的信息展示和交互反馈，补齐候选结果、失败原因、重命名预览和重新分类刷新。

#### 涉及文件

| 文件 | 变更类型 |
|------|----------|
| `media_importer/webui/js/cinema-tasks.js` | 修改：增强 `openTaskDetail()` 弹窗内容 |

#### 实现步骤

**B2-1. 候选结果展示**

1. 在 `openTaskDetail()` 中，从 `task.scrape_result` 提取候选信息：
   - `scrape_result.title_cn` / `title_en` — 匹配标题
   - `scrape_result.year` — 匹配年份
   - `scrape_result.type` — 匹配类型（movie/tv）
   - `scrape_result.overview` — 简介
   - `scrape_result.poster_url` — 海报图
2. 在弹窗 `.cinema-modal-stack` 内新增"刮削结果"区块：
   - 如有海报图，显示缩略图
   - 展示匹配标题（中/英）、年份、类型、置信度
   - 如有 `overview`，展示简介（可折叠）
3. 若 `scrape_result` 为空或 null，显示"本次未产生刮削结果"

**B2-2. 失败原因区分展示**

4. 在弹窗摘要区增强 `error_message` 展示：
   - 如 `task.status === "FAILED"` 且 `error_message` 非空，在摘要区用红色高亮区块展示错误信息
   - 区分常见错误模式（可按错误消息关键词）：
     - 网络超时 / API 限流 → "网络或服务暂时不可用"
     - 文件无法读取 → "源文件可能已被移动或删除"
     - 刮削无结果 → "未找到匹配的影视信息"
     - 其他 → 直接显示原始错误信息

**B2-3. 重命名前后文件名预览**

5. 在"文件名微调"输入区域增加实时预览：
   - 在输入框下方显示："新文件名：{输入值}"
   - 与原始文件名对比，如有变化显示变更箭头指示
   - 文件名为空时输入框边框变红

**B2-4. 重新分类后刷新当前卡片**

6. 在"应用分类微调"按钮的 `onClick` 回调中：
   - 成功后不仅调用 `loadTaskList()`，还确保当前弹窗内容更新
   - 新增 `refreshTaskDetail(taskId)` 函数：重新拉取 `/api/tasks/{id}` 并更新弹窗内维度区域
   - 或者成功后关闭弹窗，由 `loadTaskList()` 自动刷新卡片

#### 验收标准

- 任务详情弹窗显示刮削匹配结果（标题、年份、类型、简介）
- 失败任务在详情中高亮展示错误原因
- 重命名输入框下方实时预览新文件名
- 应用分类微调后弹窗内容刷新或关闭后卡片更新

#### 测试清单

| # | 测试项 | 类型 | 优先级 |
|---|--------|------|--------|
| B2-T1 | 已完成任务详情弹窗显示刮削标题、年份、类型 | 手动 | P0 |
| B2-T2 | 失败任务详情弹窗红色高亮展示错误信息 | 手动 | P0 |
| B2-T3 | 重命名输入框实时显示预览"新文件名：xxx" | 手动 | P1 |
| B2-T4 | 重命名输入清空时边框变红提示 | 手动 | P1 |
| B2-T5 | 应用分类微调成功后弹窗关闭、卡片信息更新 | 手动 | P0 |
| B2-T6 | 无刮削结果的任务显示"未产生刮削结果"占位 | 手动 | P1 |
| B2-T7 | `openTaskDetail()` 弹窗不超出屏幕可视区域 | 手动 | P2 |
| B2-T8 | 字幕表格在无字幕时显示"无字幕记录"占位（已有，回归验证） | 回归 | P1 |

---

### B3. 回收页批量恢复 / 批量清理

#### 目标

为回收站增加多选能力和批量恢复/批量永久清理操作。

#### 涉及文件

| 文件 | 变更类型 |
|------|----------|
| `media_importer/webui/js/cinema-recycle.js` | 修改：增加多选状态、批量动作函数 |
| `media_importer/webui/js/cinema-app.js` | 修改：事件绑定增加批量入口 |
| `media_importer/webui/index.html` | 修改：回收面板增加批量工具栏 |
| `media_importer/webui/css/cinema-pages.css` | 修改：回收批量工具栏样式 |

#### 实现步骤

**B3-1. 多选 UI 基础**

1. 在 `index.html` 回收区域 `#recycle-list` 上方增加批量工具栏：
   - "全选" checkbox
   - 已选计数标签
   - "批量恢复" 按钮
   - "批量永久清理" 按钮（红色警示样式）
2. 在 `cinema-recycle.js` 的 `renderRecycleCard()` 中为每张卡片增加 checkbox：
   - `<input type="checkbox" data-recycle-select="{id}">` 放在 `.task-body` 左侧
3. 新增全局状态变量 `selectedRecycleIds = new Set()`
4. 新增函数：
   - `toggleRecycleSelect(id)` — 切换选中
   - `selectAllRecycle()` — 全选
   - `clearRecycleSelection()` — 清空
   - `updateRecycleBatchToolbar()` — 同步工具栏

**B3-2. 批量恢复**

5. 新增 `performBatchRecycleRestore()` 函数：
   - 收集所有选中的 `recycle_path` 组成数组
   - 调用 `POST /api/recycle/restore`，body：`{ items: [...paths], conflict_mode: "skip" }`
   - 如果返回 `code === 207`（部分成功），检查 `data.failed` 是否有 conflict
   - 如有冲突，弹窗让用户选择：全部跳过 / 全部覆盖 / 全部重命名
   - 用户选择后重新调用对应 `conflict_mode` 重试失败项
   - 最终显示汇总 toast

**B3-3. 批量永久清理**

6. 新增 `performBatchRecycleDelete()` 函数：
   - 弹出确认弹窗："确定永久清理 N 个文件？此操作不可恢复。"
   - 确认后调用 `POST /api/recycle/delete`，body：`{ items: [...paths] }`
   - 显示汇总结果

**B3-4. 事件绑定**

7. 在 `cinema-app.js` 的 `bindEvents()` 中注册 `[data-batch-recycle-action]` 事件委托

#### 验收标准

- 回收卡片左侧出现 checkbox
- 批量工具栏显示选中数量
- 批量恢复调用后端多项目 API
- 恢复冲突时弹窗让用户选择处理策略
- 批量清理前弹出不可逆确认弹窗
- 操作完成后自动刷新回收列表

#### 测试清单

| # | 测试项 | 类型 | 优先级 |
|---|--------|------|--------|
| B3-T1 | 点击回收卡片 checkbox 选中/取消，计数更新 | 手动 | P0 |
| B3-T2 | "全选" checkbox 勾选后所有回收项被选中 | 手动 | P0 |
| B3-T3 | 批量恢复成功后 toast 显示"成功恢复 N 个文件" | 手动 | P0 |
| B3-T4 | 批量恢复部分冲突时弹出冲突策略选择弹窗 | 手动 | P0 |
| B3-T5 | 批量清理前弹出"不可恢复"确认弹窗 | 手动 | P0 |
| B3-T6 | 操作完成后回收列表自动刷新，选中状态清空 | 手动 | P0 |
| B3-T7 | 选中 0 项时批量按钮 disabled | 手动 | P1 |
| B3-T8 | `cinema-recycle.js` 行数不超过 300 行 | 代码检查 | P1 |

---

## C 类：可延后优化（不阻塞前端重构收尾）

### C1. Hero 海报与顶部大标题背景细化

#### 目标

优化各页面 Hero 区域的视觉层次和响应式表现，包括海报裁切、文字遮罩渐变、移动端适配。

#### 涉及文件

| 文件 | 变更类型 |
|------|----------|
| `media_importer/webui/css/cinema-pages.css` | 修改：Hero 海报变量、响应式断点 |
| `media_importer/webui/index.html` | 可能修改：增加 Hero 区域数据属性用于 CSS 选择器 |

#### 实现步骤

**C1-1. 页面差异化海报**

1. 当前 CSS 已通过 `.page-view[data-view="tasks"]` 等选择器为不同页面设置 `--hero-poster-image`。盘点所有页面 Hero 海报：
   - 首页（dashboard）→ 已有
   - 任务页（tasks）→ 已有
   - 回收页（recycle）→ 已有
   - 配置页（config）→ 使用默认
   - 各高级配置子页 → 使用默认
2. 为缺少海报的页面选择合适的静态图片或渐变方案
3. 调整 `--hero-text-safe-mask` 使文字区域在海报上方保持可读

**C1-2. 响应式优化**

4. 在 `@media (max-width: 768px)` 断点下：
   - 隐藏海报图层，改为纯渐变背景
   - 调整 Hero 高度从 `clamp(200px, 30vw, 320px)` 到固定 `180px`
   - 字号降级：h2 从 `clamp(1.5rem, 3vw, 2rem)` 到 `1.25rem`

**C1-3. 文字遮罩微调**

5. 检查所有页面 Hero 在不同文字长度下的遮罩效果
6. 调整 `--hero-text-safe-mask` 渐变角度和透明度，确保：
   - 短标题（2-4 字）完全在安全区
   - 长副标题不溢出遮罩区域

#### 验收标准

- 所有主要页面 Hero 有差异化视觉表现
- 移动端（375px 宽度）Hero 文字完全可读
- 海报不影响页面加载性能（仅用 CSS background-image）

#### 测试清单

| # | 测试项 | 类型 | 优先级 |
|---|--------|------|--------|
| C1-T1 | 首页 Hero 海报在 1920px 宽度下显示正常 | 手动 | P1 |
| C1-T2 | 任务页 Hero 海报在 375px 宽度下隐藏或适配 | 手动 | P1 |
| C1-T3 | 所有页面 h2 标题在 768px 断点下降级 | 手动 | P2 |
| C1-T4 | Hero 区域不产生水平滚动条 | 手动 | P1 |
| C1-T5 | 无海报页面使用渐变背景，不显示空白 | 手动 | P2 |

---

### C2. 复杂提示词/维度页完全重写为新 DOM 结构

#### 目标

将 `prompts.js` 和 `dimensions.js` 的旧全局函数式逻辑迁移为新壳层模块化架构，统一 DOM 结构和事件处理方式。

#### 涉及文件

| 文件 | 变更类型 |
|------|----------|
| `media_importer/webui/js/cinema-config.js` | 修改：新增提示词和维度的壳层函数 |
| `media_importer/webui/partials/advanced-pages.html` | 修改：提示词/维度区域 HTML 结构更新 |
| `media_importer/webui/js/prompts.js` | 标记为兼容层（长期移除） |
| `media_importer/webui/js/dimensions.js` | 标记为兼容层（长期移除） |

#### 实现步骤

**C2-1. 提示词页壳层迁移**

1. 在 `cinema-config.js` 中新增提示词管理函数：
   - `loadPromptConfig()` — 调用 `GET /api/config` 读取当前提示词
   - `savePromptConfig(section)` — 调用 `POST /api/config` 保存指定提示词段
   - `resetPromptConfig()` — 恢复默认提示词
   - `previewFullPrompt()` — 组装完整系统提示词并预览
2. 在 `advanced-pages.html` 提示词区域增加 `data-prompt-section` 数据属性
3. 将 `prompts.js` 中的 `_loadPromptDimensions()` 迁移为新模块内的 `loadPromptDimensions()`
4. 事件入口统一走 `[data-prompt-action]` 委托（已有）

**C2-2. 维度页壳层迁移**

5. 在 `cinema-config.js` 中新增维度管理函数：
   - `loadDimensionsConfig()` — 调用 `GET /api/dimensions/enabled`
   - `toggleDimension(dimName, enabled)` — 启停维度
   - `saveDimensionOrder()` — 保存拖拽排序后的顺序
   - `addDimension()` / `editDimension()` / `removeDimension()` — 增删改
6. 在 `advanced-pages.html` 维度区域重构为 `data-dimension-*` 属性驱动的 DOM
7. 拖拽排序改用 HTML5 Drag and Drop API + `data-dimension-order` 属性

**C2-3. 兼容层处理**

8. `prompts.js` 和 `dimensions.js` 暂时保留，但新增的函数不再依赖旧全局变量
9. 在文件头部注释标注"兼容层，新代码使用 cinema-config.js 中的函数"
10. 待所有页面确认不再依赖旧函数后，从 `index.html` 移除 script 引用

#### 验收标准

- 提示词页的保存/恢复/预览通过新壳层函数执行
- 维度页的增删改/启停/排序通过新壳层函数执行
- 新函数不依赖旧 `prompts.js` / `dimensions.js` 的全局变量
- `cinema-config.js` 行数不超过 1200 行

#### 测试清单

| # | 测试项 | 类型 | 优先级 |
|---|--------|------|--------|
| C2-T1 | 提示词保存后刷新页面值保持 | 手动 | P0 |
| C2-T2 | 提示词恢复默认后内容回退 | 手动 | P0 |
| C2-T3 | 提示词预览弹窗显示完整系统提示词 | 手动 | P1 |
| C2-T4 | 维度启用/禁用后配置保存成功 | 手动 | P0 |
| C2-T5 | 维度拖拽排序后保存顺序 | 手动 | P1 |
| C2-T6 | 维度新增/编辑/删除功能正常 | 手动 | P0 |
| C2-T7 | 旧 `prompts.js` / `dimensions.js` 标记为兼容层 | 代码检查 | P1 |
| C2-T8 | `cinema-config.js` 行数 ≤ 1200 | 代码检查 | P1 |

---

### C3. 更深的模块化与设计系统抽象

#### 目标

建立可复用的前端组件模式，减少配置页和高级配置页之间的重复代码。

#### 涉及文件

| 文件 | 变更类型 |
|------|----------|
| `media_importer/webui/js/cinema-config.js` | 重构：提取通用能力 |
| `media_importer/webui/js/cinema-field.js` | 新增：通用字段渲染器 |
| `media_importer/webui/js/cinema-section.js` | 新增：通用配置区块渲染器 |
| `media_importer/webui/css/cinema-pages.css` | 修改：抽取通用样式类 |

#### 实现步骤

**C3-1. 通用字段渲染器**

1. 新建 `cinema-field.js`，提供：
   - `renderTextField(key, label, value, options)` — 文本输入
   - `renderPathField(key, label, value, options)` — 路径输入（带测试按钮）
   - `renderSelectField(key, label, value, options)` — 下拉选择
   - `renderToggleField(key, label, value, options)` — 开关
   - `renderNumberField(key, label, value, options)` — 数字输入
   - `renderTextareaField(key, label, value, options)` — 文本域
2. 每个渲染器返回 HTML 字符串，统一使用 `data-field-key` 属性
3. 统一校验提示和错误状态样式

**C3-2. 通用配置区块渲染器**

4. 新建 `cinema-section.js`，提供：
   - `renderConfigSection(id, title, description, fieldsHtml)` — 渲染可折叠配置区块
   - `collectSectionValues(sectionElement)` — 从 DOM 收集区块内所有字段值
   - `validateSectionFields(sectionElement)` — 校验区块内所有必填字段

**C3-3. 重构配置页**

5. 用新的渲染器重构 `cinema-config.js` 中重复的配置区块构建代码
6. 优先重构基础配置步骤（源目录、中转目录、回收目录）
7. 再逐步推广到高级配置页

**C3-4. 样式统一**

8. 在 CSS 中抽取 `.cinema-field-*` 通用字段样式类
9. 替换硬编码的内联样式和重复的 CSS 规则

#### 验收标准

- `cinema-field.js` 提供 6 种以上通用字段渲染器
- 基础配置至少 3 个步骤使用通用渲染器
- 新渲染器生成的 DOM 与当前视觉一致
- `cinema-config.js` 行数下降（通过复用减少重复）

#### 测试清单

| # | 测试项 | 类型 | 优先级 |
|---|--------|------|--------|
| C3-T1 | 通用文本字段渲染器生成正确的 HTML | 单元 | P0 |
| C3-T2 | 通用路径字段渲染器包含测试按钮 | 单元 | P0 |
| C3-T3 | `collectSectionValues()` 正确收集所有字段值 | 单元 | P0 |
| C3-T4 | `validateSectionFields()` 标记必填空字段 | 单元 | P0 |
| C3-T5 | 基础配置保存行为与重构前一致 | 回归 | P0 |
| C3-T6 | 高级配置保存行为与重构前一致 | 回归 | P1 |
| C3-T7 | `cinema-field.js` 行数 ≤ 300 | 代码检查 | P1 |
| C3-T8 | `cinema-section.js` 行数 ≤ 200 | 代码检查 | P1 |
| C3-T9 | `cinema-config.js` 行数 ≤ 600（从 830 下降） | 代码检查 | P1 |

---

## 执行顺序建议

```
B1 → B2 → B3 → (验收 B 类) → C1 → C2 → C3 → (最终验收)
```

- B1-B3 可按任意顺序独立执行，但建议 B2 先行（改动最小、价值最高）
- C1-C3 有依赖关系：C3 的通用渲染器在 C2 重构后再做更合理（C2 明确了需要哪些字段类型）
- C1 可随时独立插入

## 总测试汇总

| 类 | 测试数 | P0 | P1 | P2 |
|----|--------|----|----|-----|
| B1 | 10 | 5 | 5 | 0 |
| B2 | 8 | 3 | 4 | 1 |
| B3 | 8 | 5 | 3 | 0 |
| C1 | 5 | 0 | 3 | 2 |
| C2 | 8 | 4 | 4 | 0 |
| C3 | 9 | 4 | 5 | 0 |
| **合计** | **48** | **21** | **24** | **3** |

## 风险

| 风险 | 等级 | 缓解 |
|------|------|------|
| 批量操作逐个调用 API 在大量任务时变慢 | 中 | 使用 `Promise.allSettled()` 并行；若 N>50 提示用户分批操作 |
| 多选 UI 影响卡片现有布局 | 低 | checkbox 使用绝对定位或 flex 布局，不改变卡片内容结构 |
| C3 过早抽象导致渲染器不够通用 | 中 | 先做 C2 明确字段需求，再提取通用渲染器 |
| 回收批量恢复冲突处理复杂 | 中 | 复用现有单项冲突处理逻辑，批量时统一策略（不逐项弹窗） |
