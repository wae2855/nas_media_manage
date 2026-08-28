# 待确认流程重构 - P1/P2 开发执行提示词

**任务**：执行 `docs/plans/2026-06-16-confirm-workflow-overhaul-plan.md` 中描述的 P1（确认交互重构）和 P2（决策路径展示优化）。
**仓库**：`/Users/wangwei/Documents/code/nas_media_manage`
**预估**：P1 约 8 小时，P2 约 3 小时，共 11 小时。

---

## 你的角色

你是一名**执行型开发者**。方案文档已设计好所有架构决策、接口契约、测试边界。你的职责是：

✅ **按 Phase 顺序逐步实施**，每个 Phase 完成后跑测试验证
✅ **遇到歧义停止并问**，不要自己拍板
✅ **每个 Phase 单独提交**，提交信息格式 `Phase X: 简述`
✅ **修改前先读相关文件**，理解上下文

❌ **不要做架构决策**（如改接口签名、改字段名、调整 Phase 顺序）
❌ **不要删除计划外的代码**（除非计划明确要求）
❌ **不要跳过测试**（每个 Phase 都有验证清单）
❌ **不要修既有的 LSP 错误**（详见规则 5）

---

## 硬性规则

### 1. 测试先行
每个 Phase 完成后**必须**运行：
```bash
cd /Users/wangwei/Documents/code/nas_media_manage
source .venv/bin/activate
python -m pytest tests/ -q --ignore=tests/test_scrape_ui.py --ignore=tests/test_frontend_recycle.py --ignore=tests/test_scrape_preview_ui.py -k "not test_ai_config_ui"
```

### 2. 文件操作规范
- **修改前必须先读文件**（用 Read 工具）
- **优先用 edit 工具**做精确替换，不要用 write 重写整个文件
- **复杂改动用 morph_edit**（多个分散位置）
- **新建文件用 write**

### 3. Python 缓存陷阱（重要！）
每次改 Python 代码后必须：
```bash
find /Users/wangwei/Documents/code/nas_media_manage -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
find /Users/wangwei/Documents/code/nas_media_manage -name "*.pyc" -delete 2>/dev/null
pkill -9 -f "python.*media_importer" 2>/dev/null
sleep 2
source /Users/wangwei/Documents/code/nas_media_manage/.venv/bin/activate
PYTHONPATH="/Users/wangwei/Documents/code/nas_media_manage" python -m media_importer.media_importer -c /Users/wangwei/Documents/code/nas_media_manage/config/config.yaml serve -p 9855 --host 0.0.0.0 > /tmp/nas_media_server.log 2>&1 &
sleep 5
```

### 4. 提交规范
- 每个 Phase 单独提交
- 提交信息：`Phase X: 简述`（如 `Phase A: DB migration 新增 confirmed_override 等三个字段`）
- 不要批量提交多个 Phase

### 5. LSP 错误处理
本项目有**既有的 LSP 类型错误**（如 mixin 类属性未声明、`sync_playwright` 可能未绑定）。这些是**已有的技术债**，不要修。只关注你**新增代码**引入的 LSP 错误。

---

## 实施顺序（严格按此顺序）

---

# P1：确认交互重构（Phase A → E）

---

## Phase A：DB migration — 新增 confirmed_override 等三个字段

### 目标
在 tasks 表新增三个字段，用于记录用户在确认界面是否换过元数据。

### 改动清单

#### A1. 修改 CREATE_TASKS_TABLE（DDL）
**文件**：`media_importer/core/db/constants.py` 第 4-59 行

在 `thumbnail_path TEXT DEFAULT ''` 之后（第 57 行后）、`)` 之前（第 58 行前），添加三行：
```sql
    confirmed_override INTEGER DEFAULT 0,
    confirmed_title TEXT DEFAULT '',
    override_source TEXT DEFAULT ''
```

#### A2. 添加 ALTER TABLE migration（兼容旧库）
**文件**：`media_importer/core/db/connection.py` 第 43-52 行 `_migrate_schema()`

在 `conn.execute("CREATE TABLE IF NOT EXISTS schema_version ...")` 之后添加：
```python
    # 2026-06-16: 确认流程重构 — 记录是否换过元数据
    for col_ddl in [
        "ALTER TABLE tasks ADD COLUMN confirmed_override INTEGER DEFAULT 0",
        "ALTER TABLE tasks ADD COLUMN confirmed_title TEXT DEFAULT ''",
        "ALTER TABLE tasks ADD COLUMN override_source TEXT DEFAULT ''",
    ]:
        try:
            conn.execute(col_ddl)
        except sqlite3.OperationalError:
            pass  # 列已存在（新库通过 CREATE TABLE 创建，旧库通过 ALTER 补上）
```

#### A3. 添加 valid_columns 白名单
**文件**：`media_importer/core/db/task_repo.py` 第 174-191 行 `update_task` 的 `valid_columns`

在 `"thumbnail_path"` 之后（第 190 行后）添加：
```python
        "confirmed_override", "confirmed_title", "override_source",
```

#### A4. 添加 list_tasks SELECT 列
**文件**：`media_importer/core/db/task_repo.py` 第 133-147 行 `list_tasks` 的 `data_sql`

在 `"t.thumbnail_path, "` 之后（第 142 行后）添加：
```python
                "t.confirmed_override, t.confirmed_title, t.override_source, "
```

### 验证
```bash
# 1. 编译检查
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer

# 2. 启动服务，确认 DB 初始化不报错
# 3. 检查 DB schema
sqlite3 data/nas_media.db ".schema tasks" | grep confirmed

# 4. 跑已有测试确认无回归
python -m pytest tests/test_p0_confirm_workflow_fixes.py tests/test_import_flow_services.py tests/test_feature_import_flow.py -q
```

---

## Phase B：后端 — preview_task 服务 + API

### 目标
新增 `POST /api/tasks/{id}/preview` 接口。接收 dimensions / title_cn / title_en / year / filename 任一变更，更新 DB + 重跑分类规则，返回预览结果，**不真正入库**。

### 改动清单

#### B1. 新增 preview_task 方法到 ConfirmMixin
**文件**：`media_importer/features/import_flow/confirm.py`

在 `ConfirmMixin` 类中，`confirm_task` 方法之后（第 56 行后）、`reclassify_task` 之前（第 58 行前），新增方法。

方法签名：`def preview_task(self, task_id: str, updates: dict) -> dict`

核心逻辑：
1. 从 `updates` 中提取 `dimensions` / `title_cn` / `title_en` / `year` / `filename`
2. 更新 `task["scrape_result"]` 和 `task["scrape_dimensions"]`
3. 调用 `db_update_task` 持久化（scrape_result, scrape_dimensions, scrape_title_cn, scrape_title_en, scrape_year, final_filename）
4. 调用 `ClassificationService.classify_task` 重跑分类规则，更新 `import_path`
5. 如果没传 filename，调用 `apply_filename_template` 生成预览文件名
6. 返回 `self.task_manager.get_task(tid)`（完整 task dict）
7. **不调 `_step_dedup` / `_step_import` / `mark_imported`**

#### B2. 新增 preview_task_for_api 到 review_service
**文件**：`media_importer/features/tasks/review_service.py`

在 `reclassify_task_for_api` 之后（第 58 行后）、`confirm_all_tasks_for_api` 之前（第 61 行前），新增函数。

函数签名：`def preview_task_for_api(pipeline, task_id: str, updates: dict, task_manager=None) -> TaskReviewActionResult`

核心逻辑：
1. 校验 pipeline 非空
2. 校验 updates 非空
3. 如果 updates 含 dimensions，校验维度启用状态（复用 reclassify_task_for_api 的校验逻辑）
4. 调用 `pipeline.preview_task(task_id, updates)`
5. 返回 `TaskReviewActionResult(code=200, data={"task": task})`

#### B3. 导出 preview_task_for_api
**文件**：`media_importer/features/tasks/__init__.py`

在 import 列表中添加 `preview_task_for_api`。

#### B4. 新增 handler
**文件**：`media_importer/api/task_handlers.py`

在 `TaskHandlersMixin` 类中，`_task_reclassify` 之后（第 104 行后）新增：

```python
    def _task_preview(self, *, body: dict, params: dict, query: dict):
        task_id = params.get("task_id", "")
        result = preview_task_for_api(
            globals._global_pipeline,
            task_id,
            body,
            task_manager=globals._global_task_manager,
        )
        json_response(self, result.code, data=result.data, message=result.message)
```

同时在文件顶部 import 中添加 `preview_task_for_api`。

#### B5. 注册路由
**文件**：`media_importer/api/routes.py`

在 POST 段（第 73-109 行），`_task_reclassify` 路由之后（第 82 行后）添加：
```python
    _route("POST", "/api/tasks/{task_id}/preview", "_task_preview"),
```

### 验证
```bash
# 1. 编译检查
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer

# 2. 单元测试：preview 接口不触发文件操作
python -m pytest tests/test_p0_confirm_workflow_fixes.py -q

# 3. 手动 curl 测试（需要服务运行中 + 有一个 AWAIT_REVIEW 任务）
curl -s -X POST http://localhost:9855/api/tasks/{task_id}/preview \
  -H "Content-Type: application/json" \
  -d '{"dimensions": {"media_type": "movie"}}' | python -m json.tool
# 预期：返回 200，task 的 import_path 更新，但 status 仍为 PENDING、stage 仍为 AWAIT_REVIEW
```

---

## Phase C：后端 — scrape-search 服务 + API

### 目标
新增 `POST /api/tasks/{id}/scrape-search` 接口。接收 query + year，返回 Provider 多候选列表。

### 改动清单

#### C1. 新增 handler
**文件**：`media_importer/api/task_handlers.py`

在 `TaskHandlersMixin` 类中新增 `_task_scrape_search` 方法。

核心逻辑：
1. 从 body 取 `query`（必填）、`year`（可选）、`media_type`（可选，默认从 task 取）
2. 调用 `create_providers(config)` 获取已启用 Provider 列表
3. 遍历每个 Provider，调用 `provider.search(query, year=year, media_type=media_type)`
4. 每个 Provider 最多取 5 个候选，聚合为统一结构：
   - id, title, original_title, year, media_type, overview（截取200字）, provider_type, poster_url, vote_average
5. 返回 `{"candidates": [...], "query": "..."}`

#### C2. 注册路由
**文件**：`media_importer/api/routes.py`

在 POST 段添加：
```python
    _route("POST", "/api/tasks/{task_id}/scrape-search", "_task_scrape_search"),
```

### 验证
```bash
# 1. 编译检查
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer

# 2. 手动 curl 测试
curl -s -X POST http://localhost:9855/api/tasks/{task_id}/scrape-search \
  -H "Content-Type: application/json" \
  -d '{"query": "阿凡达", "year": "2009"}' | python -m json.tool
# 预期：返回 candidates 列表，每项含 title/year/poster_url/overview/provider_type
```

---

## Phase D：后端 — confirm_task 接受 override 字段 + 拆分 reclassify

### 目标
1. `POST /api/tasks/{id}/confirm` 接受 `confirmed_title` 和 `override_source` 字段，入库时落 confirmed_override/confirmed_title/override_source
2. `POST /api/tasks/{id}/reclassify` 改为只更新不入库（兼容期保留）

### 改动清单

#### D1. confirm_task 接受 override 字段
**文件**：`media_importer/features/import_flow/confirm.py` 第 19-56 行 `confirm_task`

修改 `confirm_task` 方法签名，增加可选参数：
```python
def confirm_task(self, task_id: str, confirmed_title: str = None,
                 override_source: str = None) -> bool:
```

在 `mark_confirmed` 之后（第 30 行后）、`_step_import_from_confirm` 之前（第 36 行前），添加：
```python
        # 记录是否换过元数据
        confirmed_override = 1 if override_source else 0
        db_update_task(self.task_manager.conn, tid,
                       confirmed_override=confirmed_override,
                       confirmed_title=confirmed_title or "",
                       override_source=override_source or "")
```

#### D2. confirm_task_for_api 透传 override 字段
**文件**：`media_importer/features/tasks/review_service.py` 第 14-30 行 `confirm_task_for_api`

修改函数签名，增加可选参数：
```python
def confirm_task_for_api(pipeline, task_manager, task_id: str,
                         confirmed_title: str = None,
                         override_source: str = None) -> TaskReviewActionResult:
```

调用 `pipeline.confirm_task(task_id, confirmed_title=confirmed_title, override_source=override_source)`。

#### D3. _task_confirm handler 读取 body 字段
**文件**：`media_importer/api/task_handlers.py` 第 87-94 行 `_task_confirm`

修改为：
```python
    def _task_confirm(self, *, body: dict, params: dict, query: dict):
        task_id = params.get("task_id", "")
        result = confirm_task_for_api(
            globals._global_pipeline,
            globals._global_task_manager,
            task_id,
            confirmed_title=body.get("confirmed_title"),
            override_source=body.get("override_source"),
        )
        json_response(self, result.code, data=result.data, message=result.message)
```

#### D4. reclassify_task 改为只更新不入库
**文件**：`media_importer/features/import_flow/confirm.py` 第 58-161 行 `reclassify_task`

删除第 105-119 行的 `_step_dedup` / `_step_rename` / `_step_import` / `_step_notify` / `_step_record` / `mark_imported` 调用块。

改为：维度更新 + 分类重算 + 文件名预览（与 Phase B 的 preview_task 逻辑一致），返回 task dict。

**注意**：reclassify 改为兼容转发到 preview 逻辑，不删除方法（保持向后兼容）。

### 验证
```bash
# 1. 编译检查
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer

# 2. 单元测试：confirm 后 confirmed_override 字段正确落库
python -m pytest tests/ -q -k "test_p0 or test_import_flow_services"

# 3. 手动测试：reclassify 不再入库
curl -s -X POST http://localhost:9855/api/tasks/{task_id}/reclassify \
  -H "Content-Type: application/json" \
  -d '{"dimensions": {"media_type": "movie"}}' | python -m json.tool
# 预期：返回 200，task 的 import_path 更新，但 status 仍为 PENDING、stage 仍为 AWAIT_REVIEW
```

---

## Phase E：前端 — 详情面板改造（核心）

### 目标
1. "保存文件名"和"保存分类"按钮改为调 /preview（只预览不入库）
2. 新增"重新刮削"按钮 + 候选选择 UI
3. 卡片"重试"按钮收敛到异常态
4. 卡片"入库"按钮调 /confirm 时传 override 字段

### 改动清单

#### E1. 修改 handleSaveFilename — 调 /preview
**文件**：media_importer/webui/js/cinema-task-detail-open.js 第 153-184 行

将 POST /tasks/{taskId}/rename 改为 POST /tasks/{taskId}/preview，body 传 {"filename": newFilename}。
成功后不再 removeAppModal()，而是重新渲染详情面板（保持 modal 打开），让用户看到更新后的预览结果。
按钮文案从"保存文件名"改为"应用文件名并预览"。

#### E2. 修改 handleSaveDims — 调 /preview
**文件**：media_importer/webui/js/cinema-task-detail-open.js 第 186-252 行

将 POST /tasks/{taskId}/reclassify 改为 POST /tasks/{taskId}/preview，body 传 {"dimensions": changedDims}。
成功后不再 removeAppModal()，而是重新渲染详情面板，让用户看到更新后的预览结果。
按钮文案从"保存分类"改为"应用分类并预览"。

#### E3. 新增"重新刮削"按钮 + 候选选择 UI
**文件**：media_importer/webui/js/cinema-task-detail-open.js

在 openTaskDetailImpl 的 body 拼装中（第 91 行前），在文件名区块之前，新增一个"重新刮削"区块，包含：
- 搜索输入框 + 搜索按钮
- 候选列表容器（默认隐藏）
- 搜索按钮 click handler：调 POST /tasks/{taskId}/scrape-search，传 {query, year}
- 候选渲染函数 renderScrapeCandidates：每个候选显示 poster + title + year + overview + provider_type + 评分
- 点击候选：调 POST /tasks/{taskId}/preview，传 {title_cn, title_en, year}，成功后重新渲染详情面板

#### E4. 卡片"重试"按钮收敛到异常态
**文件**：media_importer/webui/js/cinema-task-utils.js 第 117-137 行 taskSecondaryAction

修改 AWAIT_REVIEW 状态的 secondary action 逻辑：
- 仅在 FAILED 或标题为空时显示"重试"
- 正常待确认返回 null（不显示重试按钮）

#### E5. 卡片"入库"按钮调 /confirm 时传 override 字段
**文件**：media_importer/webui/js/cinema-task-batch.js 第 21-37 行 performTaskAction("confirm", ...)

修改 confirm 调用，传入 override 信息：
- 从 task.scrape_result.title_cn 取 confirmed_title
- 对比原始文件名判断是否换过元数据，决定 override_source

### 验证
1. 打开 AWAIT_REVIEW 任务详情
2. 修改维度 → 点"应用分类并预览" → 确认 import_path 更新、任务未入库
3. 修改文件名 → 点"应用文件名并预览" → 确认 final_filename 更新
4. 点"重新刮削" → 输入查询词 → 确认候选列表显示 → 选一个候选 → 确认元数据更新
5. 点卡片"入库" → 确认任务 status 变为 SUCCESS
6. 确认正常待确认任务卡片不显示"重试"按钮

---

# P2：决策路径展示优化（Phase F → H）

---

## Phase F：前端 — buildMatchPathData 透传入库信息

### 目标
buildMatchPathData 返回对象新增 status、confirmed_override、confirmed_title 三个字段。

### 改动清单

#### F1. 修改 buildMatchPathData 返回对象
**文件**：media_importer/webui/js/build-match-path-data.js 第 31-55 行

在 return 对象中新增三个字段：
- status: task.status || ""
- confirmed_override: task.confirmed_override || false
- confirmed_title: task.confirmed_title || ""

### 验证
在浏览器 Console 中调用 buildMatchPathData(task) 确认新字段存在。

---

## Phase G：前端 — renderMatchPathPreview 已入库分支

### 目标
入库后决策路径最后一步显示"以《XXX》入库"或"直接确认入库"，不再显示"待人工确认"。

### 改动清单

#### G1. 在 NEEDS_CONFIRM 分支前增加已入库判定
**文件**：media_importer/webui/js/cinema-config-simulator.js 第 303-318 行

在 if (matchLevel === "NEEDS_CONFIRM") 之前（第 303 行前），新增：
- 如果 data.status === "SUCCESS"：
  - 如果 data.confirmed_override && data.confirmed_title：显示"以《XXX》入库"（绿色，IMPORTED 标签）
  - 否则：显示"直接确认入库"（绿色，IMPORTED 标签）
  - return html（跳过原有 NEEDS_CONFIRM 分支）

### 验证
1. 找一个已入库的任务（status=SUCCESS），打开详情
2. 确认决策路径最后一步显示"直接确认入库"或"以《XXX》入库"
3. 找一个 AWAIT_REVIEW 任务，确认仍显示"待人工确认"

---

## Phase H：前端 — 决策路径默认折叠

### 目标
决策路径 block 默认折叠，点击 header 展开。

### 改动清单

#### H1. 修改 buildScrapeTraceSection 返回的 HTML
**文件**：media_importer/webui/js/cinema-task-detail.js 第 184-188 行

将 <div class="cinema-modal-block"> 改为复用 .config-collapse-card 范式（不带 open class，默认折叠）：
- 外层：<div class="config-collapse-card" data-collapse-card>
- header：<div class="config-collapse-header" data-collapse-toggle> 决策路径 </div>
- body：<div class="config-collapse-body"> 时间轴 </div>

注意：.config-collapse-card 的折叠/展开事件委托已在 cinema-app-events.js:154-164 现成实现，无需额外 JS。

### 验证
1. 打开任务详情，确认决策路径默认折叠（只显示 header）
2. 点击"决策路径" header，确认展开显示完整时间轴
3. 再次点击 header，确认折叠

---

## 测试计划总览

### 后端单元测试（新增文件：tests/test_p1_preview_api.py）

| 测试用例 | 覆盖点 |
|----------|--------|
| test_preview_updates_dimensions_only | 调 /preview 传 dimensions，验证 import_path 更新、不入库 |
| test_preview_updates_title_cn | 调 /preview 传 title_cn，验证 scrape_result 更新 |
| test_preview_returns_task_with_stage_unchanged | 调 /preview 后 stage 仍为 AWAIT_REVIEW |
| test_preview_rejects_disabled_dimension | 传已禁用维度名，返回 400 |
| test_preview_empty_updates_returns_400 | 传空 body，返回 400 |
| test_confirm_stores_override_fields | 调 /confirm 传 confirmed_title + override_source，验证 DB 字段落库 |
| test_confirm_without_override_stores_defaults | 调 /confirm 不传 override，验证 confirmed_override=0 |
| test_reclassify_no_longer_imports | 调 /reclassify 后 task 不入库（status 仍为 PENDING） |
| test_scrape_search_returns_candidates | 调 /scrape-search 传 query，验证返回候选列表 |
| test_scrape_search_empty_query_returns_400 | 传空 query，返回 400 |

### 前端 Playwright 测试（新增文件：tests/test_p1_confirm_ui.py）

| 测试用例 | 覆盖点 |
|----------|--------|
| test_save_dims_shows_preview_not_import | 点"应用分类并预览"后任务仍在 AWAIT_REVIEW |
| test_save_filename_shows_preview_not_import | 点"应用文件名并预览"后任务仍在 AWAIT_REVIEW |
| test_scrape_search_shows_candidates | 输入查询词点搜索，候选列表渲染 |
| test_select_candidate_updates_metadata | 点候选后元数据更新 |
| test_confirm_button_imports_task | 点卡片"入库"后任务 status=SUCCESS |
| test_retry_button_hidden_for_normal_await | 正常待确认任务卡片不显示"重试" |
| test_retry_button_shown_for_no_title | 标题为空的任务卡片显示"重试" |
| test_decision_path_collapsed_by_default | 决策路径默认折叠 |
| test_decision_path_expands_on_click | 点击 header 展开决策路径 |
| test_imported_task_shows_imported_step | 已入库任务决策路径显示"直接确认入库" |

---

## 风险与注意事项

1. **Phase D 拆分 reclassify**：删除 _step_import 调用块时，注意保留异常处理框架，只是把入库动作替换为预览逻辑。

2. **Phase E 候选选择**：scrape-search handler 需要 import create_providers。确认 media_importer/scraper/provider_factory.py 中存在该函数。

3. **Phase E confirm 传 override**：findTaskById 函数需要能从当前页面数据中找到 task 对象。确认 cinema-task-batch.js 或 cinema-task-list.js 中存在该函数。

4. **Phase E 详情面板重新渲染**：handleSaveFilename/handleSaveDims 成功后改为重新渲染而非关闭 modal，需要确保事件绑定在重新渲染后仍然有效。

5. **Phase H 折叠样式**：.config-collapse-card 的 CSS 在 cinema-pages-8.css 中定义。确认 .config-collapse-body 默认 display:none，.open 时 display:block。
