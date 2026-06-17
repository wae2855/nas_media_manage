# 待确认流程端到端整治计划

**日期**：2026-06-16
**类型**：数据契约修复 + 交互流程重构 + 决策路径展示优化
**触发**：以一个真实电影跑通流程，发现 4 个相互关联的问题
**目标**：让"待人工确认"场景下，标题不丢、文件名不退化、保存与入库解耦、用户能在确认界面现场重刮选择元数据、入库后决策路径如实反映入库事实。

---

## 一、问题与根因

### 症状 → 根因映射表

| # | 症状 | 根因位置 | 根因类型 |
|---|------|----------|----------|
| 1 | 刮削后无中英文标题；保存后入库文件名只剩年份 | `scraper/metadata_scrape_flow.py:152-176` | 数据契约：provider-only 路径漏写 `title_cn`/`title_en` |
| 2 | 详情面板"修改文件名"点击没反应 | `webui/js/cinema-task-utils.js:51-93` | 前端：`taskDescription` 中 `desc` 未声明，AWAIT_REVIEW + `tier_short_reason` 有值时抛 ReferenceError，整个 modal 打不开 |
| 3 | 维度"保存"按钮 = 直接入库 | `features/import_flow/confirm.py:58-161` | 后端：`reclassify_task` 在维度更新后直接跑 `_step_import + mark_imported` |
| 4 | 入库后决策路径仍显示"待人工确认"；决策路径默认展开 | `webui/js/cinema-config-simulator.js:303-318` + `cinema-task-detail.js:184-188` + `build-match-path-data.js:31-55` | 前端：按 `match_level` 渲染最后一步且入库后不刷新；决策路径无折叠机制；数据装配器未透传 `task.status` |

### 数据流（症状 1 的完整链路）

```
刮削阶段（provider-only 主路径）
  metadata_scrape_flow._build_provider_only_result
    result = {title, original_title, year, ...}            ← 没有 title_cn/title_en
                ↓
features/import_flow/steps/scrape._step_scrape
    task["scrape_title_cn"] = result.get('title_cn', '')   ← ''
    task["scrape_title_en"] = result.get('title_en', '')   ← ''
    DB: tasks.scrape_title_cn='', scrape_title_en=''
                ↓
（前端列表/详情读列存字段 → 显示空标题）
                ↓
入库阶段（_step_rename → apply_filename_template → render_template）
  模板 {title_cn}.{title_en}.{year}.{resolution}.{quality}.{ext}
    → "..2023....mkv"
    → re.sub(r'\.{2,}', '.'):  ".2023.mkv"
    → re.sub(r'^\.+', ''):     "2023.mkv"                  ← 退化完成
```

### 详情面板打不开的致命点（症状 2）

`cinema-task-utils.js:58-60`：
```js
if (scrape.tier_short_reason) {
  desc += " · " + scrape.tier_short_reason;   // ← desc 从未声明
}
```
该函数被 `cinema-task-detail-open.js:95` 同步调用，位于 `showAppModal` 之前。一旦抛 ReferenceError，`openTaskDetailImpl` 整段中断，modal 不显示，所有"修改文件名/保存分类/重新刮削"按钮都无处可点。

### 接口合成语义（症状 3）

`features/import_flow/confirm.py:86-119`：
- L86-103：更新维度 + 重新跑分类规则
- L105-119：**直接执行 `_step_import + mark_imported + hooks.run_after_success`**
- L119 日志原文：`"重新分类入库成功"`

后端从一开始就把"保存维度"和"完成入库"合成了一个动作，前端按钮 selector 没有错调 confirm。

---

## 二、方案设计（三个独立工作包）

### P0 — 数据正确性（立即实施，影响所有用户）

三个独立小修复 + 回归测试。**不触碰交互流程**，行为变化最小。

#### P0-1：补全 provider-only 路径的 title_cn/title_en

文件：`media_importer/scraper/metadata_scrape_flow.py:152-176`

参照 `api/scrape_preview_job.py:246-247` 的现有约定（`title_cn = details.title`、`title_en = details.original_title`），在 `_build_provider_only_result` 的 result dict 中补两个字段。

修复后语义：
- `title_cn` = Provider 返回的本地化标题（当前实现等价于 `details.title`）
- `title_en` = 原始标题（`details.original_title`）
- 保持与 scrape_preview_job 一致，避免预览与实际结果出现两套映射

#### P0-2：修复 taskDescription 的 ReferenceError

文件：`media_importer/webui/js/cinema-task-utils.js:51-93`

把 AWAIT_REVIEW 分支重写为先收集 prefix（来自 `tier_short_reason`）再返回，避免使用未声明的 `desc`：

```js
if (status === "PENDING" && stage === "AWAIT_REVIEW") {
  const prefix = scrape.tier_short_reason || "";
  const concerns = task.match_concerns || scrape.match_concerns || [];
  const concernMessages = Array.isArray(concerns)
    ? concerns
        .map((c) => c.message || (typeof c === "string" ? c : ""))
        .filter(Boolean)
    : [];
  if (concernMessages.length > 0) {
    return [prefix, concernMessages.join("；") + "。等待你确认最终入库方向。"]
      .filter(Boolean).join(" · ");
  }
  return prefix || "需要你确认最终匹配结果。";
}
```

副作用：原本失效的 tier_short_reason 现在会真正显示（属于修 bug 顺带恢复功能）。

#### P0-3：render_template 加多层兜底

文件：`media_importer/features/import_flow/services/classification_rules.py:48-55`

当前只有 `title_cn 空 → title_en` 一层兜底。本次扩展为三层：

```python
title_cn = scraped_info.get('title_cn')
title_en = scraped_info.get('title_en', '')
title = scraped_info.get('title', '')

if not title_cn and title_en:
    title_cn = title_en
if not title_cn and title:
    title_cn = title
if title_cn and title_cn != scraped_info.get('title_cn'):
    scraped_info = dict(scraped_info)
    scraped_info['title_cn'] = title_cn
```

> **范围说明**：P0 只做三层标题兜底（cn → en → title）。P0-1 修好后 provider-only 路径已写入 `title_cn`，三层兜底已能覆盖用户场景。更深的"标题全空 → 回退原始文件名 stem"防御留给 P1 重构命名入口时一起做（需要修改 `apply_filename_template` 签名，超出 P0 范围）。

#### P0 测试

| 测试 | 文件 | 覆盖点 |
|------|------|--------|
| 单元：`_build_provider_only_result` 返回包含 title_cn/title_en | `tests/test_metadata_scrape_flow_*` | 修复 1 |
| 单元：`render_template` 在 title_cn/en/title 全空时回退到 source_filename stem | `tests/test_classification_rules_*` | 修复 3 |
| 单元：`render_template` 模板 `{title_cn}.{year}.{ext}` + 全空 → `unknown.2023.mkv`（不再只剩年份） | 同上 | 修复 3 |
| 端到端：电影 provider-only 流程入库后文件名含标题 | `tests/test_feature_import_flow.py` | 修复 1+3 联动 |

前端 `cinema-task-utils.js:59` 的 ReferenceError 难以自动化（需要 Playwright + AWAIT_REVIEW 任务），先人工冒烟，UI 测试在 P1 重构时一并补。

---

### P1 — 确认交互重构（核心体验改造）

#### P1-1：拆分接口语义（核心）

**新增**：`POST /api/tasks/{id}/preview`

请求体（任一子集）：
```json
{
  "dimensions": {"...": "..."},
  "title_cn": "...",
  "title_en": "...",
  "year": 2023,
  "filename": "..."
}
```

响应：
```json
{
  "code": 200,
  "data": {
    "task": { /* 更新后的完整 task，含新 import_path / final_filename */ },
    "preview": {
      "import_path": "/movies/科幻/...",
      "final_filename": "阿凡达.2009.mkv",
      "matched_rule": "...",
      "used_fallback": false
    }
  }
}
```

行为：
- 更新 `scrape_dimensions` / `scrape_result.title_cn` / `scrape_result.title_en` / `scrape_result.year` / `final_filename` 到 DB
- 重跑 `ClassificationService.classify_task` 计算 `import_path`
- **不调 `_step_dedup` / `_step_import` / `mark_imported`**
- **不动 source_path / video_path**
- 任务保持 `stage=AWAIT_REVIEW`，用户可继续修改或最终确认

**保留**：`POST /api/tasks/{id}/confirm` 才真正入库（行为不变）。

**改造**：`POST /api/tasks/{id}/reclassify` 改为转发到 `/preview`（兼容期保留），P2 末期下线。

#### P1-2：详情面板三按钮语义统一

| 按钮 | 现状 | 改造后 |
|------|------|--------|
| 保存文件名 | 调 `/rename`，只更新不入库 | 保持（合并到 `/preview` 也行） |
| 保存分类 | 调 `/reclassify`，**直接入库** | 调 `/preview`，只更新 + 显示预览 |
| 重新刮削 | 不存在 | 新增（见 P1-3） |

视觉上，三个"保存"按钮统一改成"应用并预览"，明确告知用户"不会入库"。

#### P1-3：详情面板新增"重新刮削"

复用 `api/scrape_preview_job.py` 已有的多候选能力：

UI 流程：
1. 用户点"重新刮削"按钮 → 弹出搜索框，预填当前 clean_title
2. 用户可输入查询词（电影名/年份），点搜索
3. 后端调 Provider 搜索，返回 Top-N 候选（poster / title / year / overview）
4. 用户选一个候选 → 前端调 `POST /preview`，把该候选的 `title_cn/title_en/year/overview/poster_url` 写入 scrape_result
5. `/preview` 自动重跑维度匹配 + 入库路径预览
6. 用户满意后点卡片"入库" → `/confirm` 入库

后端新增：`POST /api/tasks/{id}/scrape-search`

请求：
```json
{ "query": "阿凡达", "year": "2009" }
```
响应：候选列表（复用 scrape_preview_job 的序列化）。

#### P1-4：卡片"重试"按钮收敛

现状：所有 AWAIT_REVIEW 任务卡片都显示"重试"。
改造：仅在 `status=FAILED` 或 `scrape_result.title_cn` 为空时显示。正常待确认不显示。

#### P1-5：confirm 时记录 override 字段

`features/import_flow/confirm.py:confirm_task` 入参增加 `confirmed_title`、`override_source`（用户手填 / 选了某个候选 / 未改），落库到 task 新字段：

```python
task["confirmed_override"] = bool(override_source)   # 是否换过元数据
task["confirmed_title"] = final_title                 # 最终入库标题
task["override_source"] = override_source             # "manual" / "candidate:tmdb:123" / None
```

DB migration：`tasks` 表新增 `confirmed_override BOOLEAN DEFAULT 0`、`confirmed_title TEXT`、`override_source TEXT`。

---

### P2 — 决策路径展示优化（收尾）

#### P2-1：buildMatchPathData 透传入库信息

文件：`webui/js/build-match-path-data.js:31-55`

return 对象新增：
```js
{
  ...,
  status: task.status,                         // "SUCCESS" / "PENDING" / ...
  confirmed_override: task.confirmed_override || false,
  confirmed_title: task.confirmed_title || "",
}
```

后端 API 序列化（`api/utils.py`）需要透传这三个字段。

#### P2-2：renderMatchPathPreview 已入库分支

文件：`webui/js/cinema-config-simulator.js:303-362`

新增最外层判定：
```js
if (data.status === "SUCCESS") {
  // 覆盖 NEEDS_CONFIRM 分支
  const title = data.confirmed_title || data.scrape_result.title_cn || "";
  if (data.confirmed_override && title) {
    // 显示「以《XXX》入库」
  } else {
    // 显示「直接确认入库」
  }
  return html;
}
// 原 match_level 分支逻辑保持不变
```

#### P2-3：决策路径默认折叠

文件：`webui/js/cinema-task-detail.js:184-188`

把 `<div class="cinema-modal-block">` 改造为复用 `.config-collapse-card`（不带 `open` class，默认折叠）：

```html
<div class="config-collapse-card" data-collapse-card>
  <div class="config-collapse-header" data-collapse-toggle>
    <h4>决策路径${searchBadge}</h4>
  </div>
  <div class="config-collapse-body">
    <div class="cinema-detail-trace-inline">${timelineHtml}</div>
  </div>
</div>
```

事件委托已在 `cinema-app-events.js:154-164` 现成。

#### P2-4：清理未引用的老版前端（可选）

`tasks-detail.js` / `tasks-ops.js` / `tasks-actions.js` / `tasks-list.js` 未被 `index.html` 引用，建议在 P2 完成后删除，避免后续困惑。先在 `docs/architecture/legacy.md` 备案。

---

## 三、实施计划

### P0（本 PR）

| # | 任务 | 文件 | 预计行数变化 |
|---|------|------|--------------|
| P0-1 | `_build_provider_only_result` 补 title_cn/title_en | `scraper/metadata_scrape_flow.py` | +2 |
| P0-2 | `taskDescription` 修复 ReferenceError | `webui/js/cinema-task-utils.js` | ±5 |
| P0-3 | `render_template` 三层兜底（cn → en → title） | `features/import_flow/services/classification_rules.py` | +6 |
| P0-T | 4 个回归测试（实际 10 个测试用例） | `tests/test_p0_confirm_workflow_fixes.py` | +180 |

**验收**：
- 跑通 `python -m pytest tests/test_metadata_scrape_flow*.py tests/test_classification_rules*.py tests/test_feature_import_flow.py`
- `python -m compileall -q media_importer tests`
- 人工：放一个 provider-only 命中的电影到源目录，跑流程，确认详情面板能打开、标题非空、入库文件名含标题。

### P1（独立 PR）

| # | 任务 | 类型 |
|---|------|------|
| P1-1 | `POST /api/tasks/{id}/preview` 新接口 + 路由 | 后端 API |
| P1-2 | `reclassify_task` 拆出 `preview_task`（不入库）和 `confirm_task`（入库） | 后端 service |
| P1-3 | `POST /api/tasks/{id}/scrape-search` 新接口（候选搜索） | 后端 API |
| P1-4 | 详情面板三按钮统一调 `/preview` + 预览区块 | 前端 |
| P1-5 | 详情面板"重新刮削"按钮 + 候选选择 UI | 前端 |
| P1-6 | 卡片"重试"按钮收敛到异常态 | 前端 |
| P1-7 | confirm 接收 override 字段并落库 + DB migration | 后端 + DB |
| P1-T | 后端单元测试 + 前端 Playwright 端到端 | 测试 |

**验收**：
- 维度保存不再入库；卡片状态保持 AWAIT_REVIEW
- 重新刮削能选候选；选完后维度预览自动更新
- 卡片"入库"按钮走 confirm，入库后 task 状态 SUCCESS
- confirm 时落 `confirmed_override` 字段，前端能读到

### P2（独立 PR）

| # | 任务 | 类型 |
|---|------|------|
| P2-1 | `buildMatchPathData` + API 序列化透传 status / override 字段 | 前后端 |
| P2-2 | `renderMatchPathPreview` 已入库分支 | 前端 |
| P2-3 | 决策路径 block 改用 `.config-collapse-card` 默认折叠 | 前端 |
| P2-4 | 删除未引用的老版 `tasks-*.js`（可选） | 清理 |

**验收**：
- 入库后任务详情决策路径显示"以《XXX》入库"或"直接确认入库"
- 决策路径默认折叠，点击 header 展开
- 老版 JS 删除后 `index.html` 无 404

---

## 四、测试策略

### P0
- 单元：3 个新测试覆盖修复点
- 端到端：现有 `test_feature_import_flow.py` 扩展一个 provider-only 入库用例
- 编译：`python -m compileall -q media_importer tests`

### P1
- 后端：`/preview` 不应触发改文件操作（mock filesystem 断言）
- 后端：`/scrape-search` 候选返回结构正确
- 后端：confirm override 字段正确落库
- 前端：Playwright 跑通"修改维度 → 预览 → 不入库"路径
- 前端：Playwright 跑通"重新刮削 → 选候选 → 入库"路径

### P2
- 前端：Playwright 断言入库后决策路径文案与 override 一致
- 前端：决策路径默认折叠的 DOM 断言

---

## 五、风险与回滚

| 风险 | 缓解 |
|------|------|
| P0-3 兜底改动影响现有命名 | 增量测试 + 兜底只在原逻辑失效时触发 |
| P1 接口拆分破坏旧前端 | `reclassify` 转发到 `/preview` 兼容期保留 1 个版本 |
| P1 DB migration 风险 | 三个新字段都是可选/默认值，老任务读取不报错 |
| P2 决策路径折叠影响信息密度 | 折叠后保留 header 摘要（匹配层级 tag） |
| 全程 | 三个工作包独立成 PR，可单独回滚 |

---

## 六、决策记录（待 ADR 化）

如果方案确认，建议在 `docs/decisions/` 新增：
- `0007-confirm-workflow-preview-vs-import-split.md`：保存与入库解耦的接口边界
- `0008-onconfirm-scrape-retry.md`：确认界面内嵌重刮的交互范式
- `0009-decision-path-collapse-default.md`：详情面板信息密度策略

---

## 七、用户决策点（已确认）

| 决策 | 选择 |
|------|------|
| P0 时机 | 立即实施（独立 PR） |
| P1 接口粒度 | 单一 `POST /preview` 接收所有变更 |
| 重刮深度 | 支持手动输入查询词重刮 |
| override 判定 | 后端 confirm 时落 `confirmed_override` 字段 |
