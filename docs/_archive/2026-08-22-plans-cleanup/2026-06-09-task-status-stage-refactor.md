# 任务状态模型重构：status + stage 双层方案

> 版本: v2.0 | 日期: 2026-06-09 | 状态: 已完成（待验收）
> 基线提交: 41a2002 (docs: task status+stage refactor plan + UI polish)

---

## 一、背景与问题

### 当前状态模型（7 个状态混在一个字段里）

```
PENDING → PROCESSING → CONFIRMING/NEEDS_REVIEW → SUCCESS/FAILED/SKIPPED
```

### 核心问题

1. **两层概念混用**：PENDING/SUCCESS/FAILED/SKIPPED 是"任务终态"，PROCESSING/CONFIRMING/NEEDS_REVIEW 是"处理环节"，混在同一个 status 字段里导致语义冲突
2. **PROCESSING 不安全**：前端仍显示"移入回收"按钮，虽然后端有校验但用户体验差
3. **CONFIRMING vs NEEDS_REVIEW 矛盾**：前端不区分两者但后端操作权限不同，用户点"确认"可能报错
4. **AWAIT_REVIEW 操作不直觉**：用户需要区分"修改分类"和"修改文件名"，实际上只需一个"修改"入口

### 代码审计发现（必须修复）

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| A1 | 状态常量双源维护 | constants.py `VALID_STATUSES` 与 task_lifecycle.py `STATUS_*` 独立定义 | 重构时必须统一 |
| A2 | ignore 操作绕过 task_lifecycle | file_lifecycle_service.py:143-160 直接写 `status="SKIPPED"` | 不走 mark_skipped()，stage 不会被设置 |
| A3 | 新旧 UI 分组不一致 | cinema-app.js 把 CONFIRMING+NEEDS_REVIEW 合并，tasks.js 把 PROCESSING+CONFIRMING 合并 | 两边都需同步 |
| A4 | API 不支持 stage 参数 | list_service.py 只接受单个 status 参数 | 前端通过并行请求变通，需改为支持 stage |
| A5 | confirm.py 硬编码状态检查 | confirm_task() 只接受 `status == "CONFIRMING"`，拒绝 NEEDS_REVIEW | 需改为 stage 感知 |

---

## 二、新模型设计

### status（任务终态，5 个）

| status | 含义 | stage 语义 |
|--------|------|-----------|
| PENDING | 处理中（尚未到达终态） | 由 stage 细化 |
| SUCCESS | 入库成功 | DONE |
| FAILED | 处理失败 | DONE |
| SKIPPED | 跳过/忽略 | DONE |
| CANCELLED | 用户取消 | DONE |

### stage（处理环节，4 个，仅 status=PENDING 时有意义）

| stage | 含义 | 对应旧状态 |
|-------|------|-----------|
| QUEUED | 排队等待 | 原 PENDING（初始态） |
| RUNNING | 流水线处理中 | 原 PROCESSING |
| AWAIT_REVIEW | 等待人工操作 | 合并原 CONFIRMING + NEEDS_REVIEW |
| DONE | 已到达终态 | status 非 PENDING 时 stage=DONE |

### 状态转换图

```
新任务 → [PENDING/QUEUED]
           │
           ▼
       [PENDING/RUNNING]  ←── 重试(retry)
           │
    ┌──────┴──────┐
    │             │
    ▼             ▼
[PENDING/       [PENDING/
 AWAIT_REVIEW]   AWAIT_REVIEW] ──ignore──→ [SKIPPED/DONE]
    │             │
    │          reclassify
    │             │
    ▼             ▼
 confirm        confirm
    │             │
    ▼             ▼
[SUCCESS/DONE] [SUCCESS/DONE]

任意环节异常 → [FAILED/DONE]
用户取消     → [CANCELLED/DONE]
```

### 转换函数与新值对照表

| 旧函数名 | 新 status | 新 stage | 说明 |
|----------|----------|---------|------|
| `start_processing()` | PENDING | RUNNING | 开始处理 |
| `mark_processing_step()` | PENDING | RUNNING | 更新进度 |
| `mark_confirming()` | PENDING | AWAIT_REVIEW | 置信度不够，需人工确认 |
| `mark_needs_review()` | PENDING | AWAIT_REVIEW | 数据门控阻止，合并到同一 stage |
| `mark_failed()` | FAILED | DONE | 处理失败 |
| `mark_skipped()` | SKIPPED | DONE | 跳过/忽略 |
| `mark_imported()` | SUCCESS | DONE | 入库成功 |
| `reset_for_retry()` | PENDING | QUEUED | 重试 |

---

## 三、前端筛选映射

用户看到的筛选 Chip 是**场景化**的，不直接暴露 status/stage：

| Chip | 后端查询条件 | 包含的旧状态 |
|------|-------------|-------------|
| 全部 | 无过滤 | 全部 |
| 排队中 | status=PENDING, stage=QUEUED | 原 PENDING |
| 处理中 | status=PENDING, stage=RUNNING | 原 PROCESSING |
| 待确认 | status=PENDING, stage=AWAIT_REVIEW | 原 CONFIRMING + NEEDS_REVIEW |
| 已失败 | status=FAILED | 原 FAILED |
| 已完成 | status=SUCCESS 或 SKIPPED | 原 SUCCESS + SKIPPED |

### API 查询参数变更

当前 `GET /api/tasks?status=PENDING` 只支持单值。重构后：

```
GET /api/tasks?status=PENDING&stage=AWAIT_REVIEW
GET /api/tasks?status=FAILED
GET /api/tasks?status=SUCCESS&status=SKIPPED   （多值用重复参数）
```

---

## 四、按钮逻辑

### 单卡片按钮（只看 stage + status）

| status/stage | 主按钮 | 次按钮 | 详情（幽灵） | 文件名可编辑 | 维度可编辑 |
|-------------|--------|--------|--------------|--------------|------------|
| PENDING/QUEUED | 取消 | — | 详情 | 否 | 否 |
| PENDING/RUNNING | — | — | 详情 | 否 | 否 |
| PENDING/AWAIT_REVIEW | 去确认 | — | 详情 | 是 | 是 |
| SUCCESS | — | — | 详情 | 否 | 否 |
| FAILED | 去重试 | 移入回收 | 详情 | 否 | 否 |
| SKIPPED | 去重试 | — | 详情 | 否 | 否 |
| CANCELLED | 重新投入 | — | 详情 | 否 | 否 |

### AWAIT_REVIEW 编辑模式

点击"修改"按钮进入编辑弹窗。**不区分"修改分类"和"修改文件名"**，统一为一个编辑入口：

1. **维度区域**：所有分类维度均可编辑（下拉/输入），区域右上角增加"入库预览"按钮
2. **文件名区域**：源文件名输入框可编辑
3. **入库预览**：点击后调用 `POST /api/tasks/{id}/classify-preview`，展示当前维度对应的入库目录
4. 预览结果以路径展示：`目标目录 /vol1/影视/电影/2010/盗梦空间 (2010)/` + 最终文件名
5. 确认修改后调用 reclassify 入库

### 批量操作

| 批量按钮 | 启用条件 |
|----------|---------|
| 批量重试 | 存在 FAILED 或 SKIPPED |
| 批量确认 | 存在 PENDING/AWAIT_REVIEW |
| 批量忽略 | 存在 PENDING/AWAIT_REVIEW 或 FAILED |
| 批量移入回收 | 存在 PENDING（任意 stage）或 FAILED |

---

## 五、新增功能：入库预览

### API 设计

```
POST /api/tasks/{task_id}/classify-preview
```

**请求体**（可选，若提供则用临时维度覆盖任务现有维度）：
```json
{
  "dimensions": {
    "media_type": "movie",
    "genre": "action"
  },
  "filename": "Inception.2010.mkv"
}
```

**响应**：
```json
{
  "code": 200,
  "data": {
    "import_path": "/vol1/影视/电影/2010/盗梦空间 (2010)/",
    "final_filename": "盗梦空间.Inception.2010.1080p.mkv",
    "full_path": "/vol1/影视/电影/2010/盗梦空间 (2010)/盗梦空间.Inception.2010.1080p.mkv",
    "matched_rule": {
      "conditions": {"media_type": "movie"},
      "template": "/vol1/影视/电影/{year}/{title_cn} ({year})/"
    },
    "warnings": []
  }
}
```

### 后端实现要点

复用 `ClassificationService` (classification.py:17-48) 和 `render_template` (classification_rules.py)：
- 不执行任何文件操作
- 只做规则匹配 + 路径计算 + 返回结果
- 如果请求体包含 dimensions，用临时值覆盖任务的 `scrape_dimensions`
- 新增 `preview_classify()` 方法在 `ClassificationService` 中，返回 `ClassificationResult` 但不修改 task

---

## 六、DB 变更

### 新增列

```sql
ALTER TABLE tasks ADD COLUMN stage TEXT DEFAULT 'QUEUED';
```

### 数据迁移（一次性，在 `_migrate_schema()` 中执行）

```sql
-- Step 1: 先将 NEEDS_REVIEW 统一为 CONFIRMING
UPDATE tasks SET status='CONFIRMING' WHERE status='NEEDS_REVIEW';

-- Step 2: 根据 status 设置 stage
UPDATE tasks SET stage='QUEUED'       WHERE status='PENDING';
UPDATE tasks SET stage='RUNNING'      WHERE status='PROCESSING';
UPDATE tasks SET stage='AWAIT_REVIEW' WHERE status='CONFIRMING';
UPDATE tasks SET stage='DONE'         WHERE status IN ('SUCCESS','FAILED','SKIPPED');

-- Step 3: 将非终态的 status 统一为 PENDING
UPDATE tasks SET status='PENDING' WHERE status IN ('PROCESSING','CONFIRMING');
```

### valid_columns 白名单更新

task_repo.py:138-175 的 `update_task()` 使用 `valid_columns` 白名单（34 个字段），需新增 `stage`。

---

## 七、开发任务清单

### Phase 1：后端核心

#### 1.1 常量统一

**文件**: `media_importer/core/db/constants.py`

**当前状态**:
- `VALID_STATUSES` 在 constants.py:336 定义 7 个值
- `STATUS_*` 常量在 task_lifecycle.py:4-10 独立定义 7 个值

**变更内容**:
```python
# constants.py 中新增
VALID_STATUSES = ["PENDING", "SUCCESS", "FAILED", "SKIPPED", "CANCELLED"]
VALID_STAGES = ["QUEUED", "RUNNING", "AWAIT_REVIEW", "DONE"]

# CREATE_TASKS_TABLE 中新增列
# "stage TEXT DEFAULT 'QUEUED',"
```

**文件**: `media_importer/core/task_lifecycle.py`

**变更内容**:
```python
# task_lifecycle.py 中新增 stage 常量，替代旧的 CONFIRMING/NEEDS_REVIEW/PROCESSING 状态常量
STAGE_QUEUED = "QUEUED"
STAGE_RUNNING = "RUNNING"
STAGE_AWAIT_REVIEW = "AWAIT_REVIEW"
STAGE_DONE = "DONE"
VALID_STAGES = [STAGE_QUEUED, STAGE_RUNNING, STAGE_AWAIT_REVIEW, STAGE_DONE]
```

---

#### 1.2 DB 迁移

**文件**: `media_importer/core/db/connection.py`

**当前状态**: `_migrate_schema()` 函数 (connection.py:44-60) 处理 ADD COLUMN 迁移

**变更内容**:
在 `_migrate_schema()` 末尾追加 stage 列迁移逻辑：
```python
# 检查 stage 列是否存在，不存在则 ADD COLUMN + 数据迁移
cursor.execute("PRAGMA table_info(tasks)")
columns = {row[1] for row in cursor.fetchall()}
if "stage" not in columns:
    cursor.execute("ALTER TABLE tasks ADD COLUMN stage TEXT DEFAULT 'QUEUED'")
    cursor.execute("UPDATE tasks SET status='CONFIRMING' WHERE status='NEEDS_REVIEW'")
    cursor.execute("UPDATE tasks SET stage='QUEUED' WHERE status='PENDING'")
    cursor.execute("UPDATE tasks SET stage='RUNNING' WHERE status='PROCESSING'")
    cursor.execute("UPDATE tasks SET stage='AWAIT_REVIEW' WHERE status='CONFIRMING'")
    cursor.execute("UPDATE tasks SET stage='DONE' WHERE status IN ('SUCCESS','FAILED','SKIPPED')")
    cursor.execute("UPDATE tasks SET status='PENDING' WHERE status IN ('PROCESSING','CONFIRMING')")
```

---

#### 1.3 task_lifecycle.py 转换函数

**文件**: `media_importer/core/task_lifecycle.py`

**当前状态**: 8 个转换函数通过 `_apply()` 辅助函数写入字段

**变更内容**: 每个转换函数需同时设置 `stage` 字段

| 函数 | 旧 status | 新 status | 新 stage |
|------|----------|----------|---------|
| `start_processing()` | PROCESSING | PENDING | RUNNING |
| `mark_processing_step()` | PROCESSING | PENDING | RUNNING |
| `mark_temp_ready()` | 不变 | 不变 | 不变 |
| `mark_confirming()` | CONFIRMING | PENDING | AWAIT_REVIEW |
| `mark_needs_review()` | NEEDS_REVIEW | PENDING | AWAIT_REVIEW |
| `mark_failed()` | FAILED | FAILED | DONE |
| `mark_skipped()` | SKIPPED | SKIPPED | DONE |
| `mark_imported()` | SUCCESS | SUCCESS | DONE |
| `mark_confirmed()` | 不变 | 不变 | 不变 |
| `reset_for_retry()` | PENDING | PENDING | QUEUED |

**注意**: `_apply()` 函数内部需要将 `stage` 加入写入字段列表。

---

#### 1.4 task_repo.py SQL 适配

**文件**: `media_importer/core/db/task_repo.py`

**需要修改的查询**:

| 函数 | 行号 | 当前条件 | 改为 |
|------|------|---------|------|
| `list_tasks()` | 98-135 | `WHERE status=?` 单值 | 支持 `status=? AND stage=?` 组合，或 `status IN (...)` 多值 |
| `count_by_status()` | 178-188 | `GROUP BY status` | `GROUP BY status, stage` |
| `has_running_tasks()` | 216-221 | `status IN ('PROCESSING')` | `status='PENDING' AND stage='RUNNING'` |
| `count_by_specific_status()` | 224-230 | `WHERE status=?` | 支持 stage 参数 |
| `find_failed_too_many()` | 233-239 | `status='FAILED'` | 不变（FAILED 无需 stage 过滤） |
| `get_next_pending()` | 242-250 | `status='PENDING'` | `status='PENDING' AND stage='QUEUED'` |
| `clear_tasks()` | 199-213 | `WHERE status=?` | 支持 stage 条件 |

**新增**: `list_tasks()` 需支持 `stage` 参数和 `status` 多值。建议改为：
```python
def list_tasks(db, status=None, stage=None, statuses=None, ...):
    # status: 单值过滤
    # stage: 单值过滤（仅 status=PENDING 时有意义）
    # statuses: 多值过滤（用于"已完成"等组合场景）
```

**valid_columns 更新**: update_task() 的 valid_columns 白名单新增 `"stage"`。

---

#### 1.5 task_manager.py 适配

**文件**: `media_importer/core/task_manager.py`

**当前状态**: 33 处引用 status 常量

**关键改动点**:

| 位置 | 当前逻辑 | 改为 |
|------|---------|------|
| `retry_task()` :124-128 | `status not in ("FAILED", "SKIPPED")` | 不变（FAILED/SKIPPED 是终态） |
| `check_source_duplicate()` | `status in ("PROCESSING", "CONFIRMING")` | `status="PENDING" AND stage IN ("RUNNING","AWAIT_REVIEW")` |
| `retry_all_failed()` :134-137 | `status == "FAILED"` | 不变 |

---

#### 1.6 新增 classify-preview API

**文件**: `media_importer/features/import_flow/services/classification.py`

**当前状态**: `ClassificationService` 只有 `classify_task()` 方法

**新增方法**:
```python
def preview_classify(self, task_dict, override_dimensions=None, override_filename=None):
    """
    预览分类结果，不执行任何文件操作。
    task_dict: 任务数据的 dict
    override_dimensions: 可选，临时覆盖维度
    override_filename: 可选，临时覆盖文件名
    返回: ClassificationResult
    """
```

**新文件或扩展文件**: `media_importer/api/task_handlers.py` 或新文件

**新增 handler**:
```python
def handle_classify_preview(request_body, task_id):
    task = get_task(task_id)
    if not task:
        return {"code": 404, "message": "任务不存在"}
    override_dims = request_body.get("dimensions")
    override_name = request_body.get("filename")
    svc = ClassificationService(config)
    result = svc.preview_classify(task, override_dims, override_name)
    return {"code": 200, "data": {...}}
```

**文件**: `media_importer/api/routes.py`

新增路由:
```python
("POST", "/api/tasks/{task_id}/classify-preview", handle_classify_preview),
```

---

#### 1.7 list_service.py 支持 stage

**文件**: `media_importer/features/tasks/list_service.py`

**当前状态**: `list_tasks_for_api()` (list_service.py:16-66) 只解析 `status` 参数

**变更内容**: 新增 `stage` 参数解析，传递给 `task_repo.list_tasks()`

```python
def list_tasks_for_api(db, query_params):
    status = query_params.get("status")
    stage = query_params.get("stage")
    # status 可以多值（重复参数），stage 单值
    # 校验合法性后传给 task_repo.list_tasks()
```

**active_count 计算**: 当前 `PENDING+PROCESSING+FAILED+CONFIRMING`，改为 `status='PENDING'` + `status='FAILED'` 的计数。

---

#### 1.8 queue_service.py 适配

**文件**: `media_importer/features/tasks/queue_service.py`

**变更**: `clear_tasks` 和 `retry_all_failed` 的 status 参数传递需适配。retry 逻辑不变（FAILED/SKIPPED 仍是终态）。

---

#### 1.9 review_service.py 适配

**文件**: `media_importer/features/tasks/review_service.py`

**变更**: confirm-all 操作当前可能只查 CONFIRMING 状态，需改为 `status='PENDING' AND stage='AWAIT_REVIEW'`。

---

#### 1.10 file_lifecycle_service.py 修复

**文件**: `media_importer/features/tasks/file_lifecycle_service.py`

**当前问题 (A2)**: ignore 操作 (file_lifecycle_service.py:143-160) 直接硬编码 `status="SKIPPED"` 绕过 `mark_skipped()`

**修复**: 改为调用 `mark_skipped()` 确保同时设置 `stage='DONE'`，或直接在写入时同时设置 `stage='DONE'`。

**ignore 白名单**: 当前 file_lifecycle_service.py 只允许 FAILED 和 CONFIRMING 的 ignore（排除了 NEEDS_REVIEW），重构后应改为 `stage='AWAIT_REVIEW'` 或 `status='FAILED'`。

---

#### 1.11 delete_service.py 适配

**文件**: `media_importer/features/tasks/delete_service.py`

**当前状态**: `delete_task()` 黑名单拒绝 PROCESSING

**变更**: 改为拒绝 `status='PENDING' AND stage='RUNNING'` 的任务。

---

#### 1.12 runner.py 适配

**文件**: `media_importer/features/import_flow/runner.py`

**当前状态**: 流水线调用 `start_processing()`、`mark_confirming()`、`mark_needs_review()` 等

**变更**: 这些函数内部已改为同时设置 status+stage，runner.py **无需修改调用方式**，只需确保 `mark_needs_review()` 和 `mark_confirming()` 都映射到 `stage=AWAIT_REVIEW`。

**注意**: runner.py 中如有直接读取 `task["status"]` 做判断的地方（如 `status == "CONFIRMING"`），需改为 `task.get("stage") == "AWAIT_REVIEW"`。

---

#### 1.13 confirm.py 适配

**文件**: `media_importer/features/import_flow/confirm.py`

**当前问题 (A5)**: `confirm_task()` 硬编码 `status == "CONFIRMING"` 检查

**变更**:
- `confirm_task()`: 状态检查改为 `stage == "AWAIT_REVIEW"`
- `reclassify_task()`: 状态检查改为 `stage == "AWAIT_REVIEW"`

---

#### 1.14 handler.py 和 metrics.py 适配

**文件**: `media_importer/api/handler.py`

启动逻辑中如果有 `status == "PROCESSING"` 的判断，需改为 stage 感知。

**文件**: `media_importer/core/metrics.py`

`count_by_status()` 改为 `count_by_status_and_stage()`，返回结果包含 stage 维度。

---

### Phase 2：前端核心

#### 2.1 筛选映射重构

**文件**: `media_importer/webui/js/cinema-app.js`

**当前**: `TASK_FILTER_STATUS_MAP` 按 status 数组映射，前端通过并行请求变通

**改为**: 按单个 status + stage 参数映射，一次请求

```javascript
const TASK_FILTER_PARAMS = {
    all: {},
    queued: { status: "PENDING", stage: "QUEUED" },
    running: { status: "PENDING", stage: "RUNNING" },
    review: { status: "PENDING", stage: "AWAIT_REVIEW" },
    failed: { status: "FAILED" },
    success: { status: ["SUCCESS", "SKIPPED"] },
};
```

**`loadTaskList()` 改为单次请求**:
```javascript
async function loadTaskList() {
    const params = TASK_FILTER_PARAMS[currentTaskFilter];
    const query = buildQuery(params);
    const resp = await fetch(`/api/tasks?${query}`);
    // ...
}
```

**Chip 标签更新**:
```javascript
const TASK_FILTER_META = {
    all:     { label: "全部", icon: "fa-list" },
    queued:  { label: "排队中", icon: "fa-clock" },
    running: { label: "处理中", icon: "fa-spinner" },
    review:  { label: "待确认", icon: "fa-check-circle" },
    failed:  { label: "已失败", icon: "fa-exclamation-triangle" },
    success: { label: "已完成", icon: "fa-check" },
};
```

---

#### 2.2 卡片按钮逻辑

**文件**: `media_importer/webui/js/cinema-tasks.js`

**当前**: `taskPrimaryAction(task)` 和 `taskSecondaryAction(task)` (cinema-tasks.js:86-100) 按 `task.status` 判断

**改为**: 按 `task.status` + `task.stage` 联合判断

```javascript
function taskPrimaryAction(task) {
    const s = task.status, st = task.stage;
    if (s === "PENDING" && st === "AWAIT_REVIEW") return { label: "确认", action: "confirm" };
    if (s === "FAILED") return { label: "重试", action: "retry" };
    if (s === "SKIPPED") return { label: "重试", action: "retry" };
    return { label: "查看", action: "view" };
}

function taskSecondaryAction(task) {
    const s = task.status, st = task.stage;
    if (s === "PENDING" && st === "QUEUED") return { label: "移入回收", action: "recycle" };
    if (s === "PENDING" && st === "AWAIT_REVIEW") return { label: "修改", action: "edit" };
    if (s === "FAILED") return { label: "移入回收", action: "recycle" };
    return null;
}
```

---

#### 2.3 批量操作适配

**文件**: `media_importer/webui/js/cinema-tasks.js`

**当前**: `isBatchableStatus()` (cinema-tasks.js:641-643) 按单个 status 判断

**改为**: 按 status+stage 判断

```javascript
function getBatchActions(tasks) {
    const has = (s, st) => tasks.some(t => t.status === s && (!st || t.stage === st));
    return {
        batchRetry:   has("FAILED") || has("SKIPPED"),
        batchConfirm: has("PENDING", "AWAIT_REVIEW"),
        batchIgnore:  has("PENDING", "AWAIT_REVIEW") || has("FAILED"),
        batchRecycle: has("PENDING") || has("FAILED"),
    };
}
```

---

#### 2.4 AWAIT_REVIEW 编辑模式 + 入库预览

**文件**: `media_importer/webui/js/cinema-tasks.js`

**当前**: `buildTaskDimensionsForm(task, editable)` 渲染维度表单

**变更**: 当 `stage === "AWAIT_REVIEW"` 且进入编辑模式时：

1. 所有维度字段设为可编辑
2. 文件名字段设为可编辑
3. 在维度区域**右上角**增加"入库预览"按钮
4. 点击"入库预览"调用 API 并展示结果

**入库预览 UI 交互**:
```
┌─────────────────────────────────────────┐
│  任务详情 - 编辑模式                      │
│                                         │
│  ┌─── 维度信息 ──────── [入库预览] ───┐  │
│  │ 媒体类型: [movie ▼]               │  │
│  │ 年份:     [2010]                  │  │
│  │ 标题:     [盗梦空间]              │  │
│  │ ...                               │  │
│  └───────────────────────────────────┘  │
│                                         │
│  预览结果:                               │
│  ┌───────────────────────────────────┐  │
│  │ 📁 /vol1/影视/电影/2010/          │  │
│  │    └─ 盗梦空间 (2010)/            │  │
│  │       └─ 盗梦空间.2010.mkv        │  │
│  │                                   │  │
│  │ 匹配规则: media_type=movie        │  │
│  └───────────────────────────────────┘  │
│                                         │
│  源文件名: [Inception.2010.1080p.mkv]   │
│                                         │
│           [取消]  [确认修改]             │
└─────────────────────────────────────────┘
```

**入库预览请求逻辑**:
```javascript
async function previewClassify(taskId, dimensions, filename) {
    const body = {};
    if (dimensions) body.dimensions = dimensions;
    if (filename) body.filename = filename;
    const resp = await fetch(`/api/tasks/${taskId}/classify-preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    return resp.json();
}
```

---

#### 2.5 首页 metrics 适配

**文件**: `media_importer/webui/js/cinema-app.js`

**当前**: `fetchQueueSnapshot()` 按 status 获取统计数据

**变更**: 后端 `/api/tasks/stats` 返回改为包含 stage 维度，前端按新分组展示。

---

#### 2.6 CSS badge 颜色

**文件**: `media_importer/webui/css/cinema-pages.css`

**变更**: 新增 stage 相关的 badge 样式：

```css
.cinema-badge--queued   { background: var(--cinema-badge-queued); }
.cinema-badge--running  { background: var(--cinema-badge-running); }
.cinema-badge--review   { background: var(--cinema-badge-review); }
.cinema-badge--done     { background: var(--cinema-badge-done); }
```

---

#### 2.7 旧版 tasks.js 同步

**文件**: `media_importer/webui/js/tasks.js`

**当前**: `STATUS_GROUPS` (tasks.js:51-56) 将状态分为 4 组

**变更**: 同步更新为 stage 感知的分组，确保旧版 UI 也能正常工作（如果仍被使用）。

---

### Phase 3：测试清单

> 测试分类说明：
> - **U（Unit）**：单函数/单类隔离测试，不依赖 DB 或外部服务
> - **I（Integration）**：多组件协作测试，使用真实 SQLite 或 mock API
> - **R（Regression/E2E）**：端到端回归测试，Playwright + 真实 HTTP 服务

#### 3.1 基础设施适配

| # | 类型 | 测试文件 | 适配内容 |
|---|------|---------|---------|
| 3.1.1 | 基础 | `tests/conftest.py` | `_build_e2e_config` 和 `e2e_server` fixture 无需改动（不涉及 status），但 `_create_terminal_task` 等辅助函数的 INSERT 语句需新增 `stage` 列 |

#### 3.2 新增测试：stage 转换（Unit）

**新文件**: `tests/test_stage_lifecycle.py`

| # | 测试用例 | 验证点 | 对应旧测试 |
|---|---------|--------|-----------|
| 3.2.1 | `test_start_processing_sets_status_pending_stage_running` | `start_processing()` → status=PENDING, stage=RUNNING, started_at 被设置 | 原 test_task_context_lifecycle 中 `test_start_processing_sets_status_and_started_at`（断言从 PROCESSING 改为 PENDING+RUNNING） |
| 3.2.2 | `test_mark_processing_step_keeps_stage_running` | `mark_processing_step()` → status=PENDING, stage=RUNNING, step 字段更新 | 新增（验证 step 更新不改变 status/stage） |
| 3.2.3 | `test_mark_confirming_sets_stage_await_review` | `mark_confirming()` → status=PENDING, stage=AWAIT_REVIEW | 原 `test_mark_confirming_can_preserve_error_message_when_no_reason` |
| 3.2.4 | `test_mark_confirming_records_reason` | `mark_confirming(reason=...)` → error_message 被设置 | 原 `test_mark_confirming_records_reason_when_provided` |
| 3.2.5 | `test_mark_needs_review_same_stage_as_confirming` | `mark_needs_review()` → status=PENDING, stage=AWAIT_REVIEW（与 mark_confirming 相同 stage） | 原 `test_mark_needs_review_records_temp_location` + **新增验证 stage 一致性** |
| 3.2.6 | `test_mark_failed_sets_stage_done` | `mark_failed()` → status=FAILED, stage=DONE, completed_at 被设置 | 原 `test_mark_failed_can_clear_or_preserve_video_path` |
| 3.2.7 | `test_mark_skipped_sets_stage_done` | `mark_skipped()` → status=SKIPPED, stage=DONE, skip_reason 被记录 | 原 `test_mark_skipped_records_completion_and_location` |
| 3.2.8 | `test_mark_imported_sets_stage_done` | `mark_imported()` → status=SUCCESS, stage=DONE, import_success=1 | 原 `test_mark_imported_records_success_fields` |
| 3.2.9 | `test_reset_for_retry_sets_stage_queued` | `reset_for_retry()` → status=PENDING, stage=QUEUED, retry_count+1 | 原 `test_reset_for_retry_resets_runtime_fields` |
| 3.2.10 | `test_mark_temp_ready_does_not_change_stage` | `mark_temp_ready()` → status 和 stage 不变，只改 file_location | 原 `test_mark_temp_ready_tracks_current_temp_video` |
| 3.2.11 | `test_lifecycle_transition_table_records_stage` | 综合验证所有转换函数的 stage 字段记录 | 原 `test_lifecycle_transition_table_records_core_contract` 扩展 |
| 3.2.12 | `test_terminal_statuses_have_stage_done` | 直接构造 SUCCESS/FAILED/SKIPPED/CANCELLED 状态的任务，验证 stage=DONE | **新增** |

#### 3.3 新增测试：入库预览（Unit + Integration）

**新文件**: `tests/test_classify_preview.py`

| # | 类型 | 测试用例 | 验证点 |
|---|------|---------|--------|
| 3.3.1 | U | `test_preview_uses_existing_dimensions` | 不带覆盖参数，使用任务现有 scrape_dimensions 返回正确路径 |
| 3.3.2 | U | `test_preview_with_override_dimensions` | 传入 `{"media_type": "tv"}`，返回 TV 剧集路径而非电影路径 |
| 3.3.3 | U | `test_preview_with_override_filename` | 传入不同文件名，final_filename 随之改变 |
| 3.3.4 | U | `test_preview_returns_matched_rule_info` | 返回 matched_rule.conditions 和 matched_rule.template |
| 3.3.5 | U | `test_preview_returns_warnings_for_missing_fields` | 缺少必要维度时 warnings 包含提示 |
| 3.3.6 | U | `test_preview_does_not_modify_task` | 调用前后 task 对象无变化（mock 验证无 update_task 调用） |
| 3.3.7 | U | `test_preview_uses_fallback_dir_when_no_rule_matches` | 无匹配规则时使用 fallback_dir |
| 3.3.8 | I | `test_classify_preview_api_returns_200` | POST /api/tasks/{id}/classify-preview 返回 200 + 正确数据 |
| 3.3.9 | I | `test_classify_preview_api_returns_404_for_missing_task` | 不存在的 task_id 返回 404 |
| 3.3.10 | I | `test_classify_preview_api_rejects_non_pending_task` | SUCCESS/FAILED 任务返回 400（只允许 PENDING/AWAIT_REVIEW） |

#### 3.4 新增测试：DB 迁移（Integration）

**新文件**: `tests/test_stage_db_migration.py`

| # | 测试用例 | 验证点 |
|---|---------|--------|
| 3.4.1 | `test_migration_adds_stage_column` | 迁移后 tasks 表包含 stage 列 |
| 3.4.2 | `test_migration_converts_pending_to_queued` | 旧 PENDING → PENDING/QUEUED |
| 3.4.3 | `test_migration_converts_processing_to_running` | 旧 PROCESSING → PENDING/RUNNING |
| 3.4.4 | `test_migration_converts_confirming_to_await_review` | 旧 CONFIRMING → PENDING/AWAIT_REVIEW |
| 3.4.5 | `test_migration_converts_needs_review_to_await_review` | 旧 NEEDS_REVIEW → PENDING/AWAIT_REVIEW |
| 3.4.6 | `test_migration_converts_success_to_done` | 旧 SUCCESS → SUCCESS/DONE |
| 3.4.7 | `test_migration_converts_failed_to_done` | 旧 FAILED → FAILED/DONE |
| 3.4.8 | `test_migration_converts_skipped_to_done` | 旧 SKIPPED → SKIPPED/DONE |
| 3.4.9 | `test_migration_is_idempotent` | 重复运行迁移不改变数据 |
| 3.4.10 | `test_new_task_default_stage_is_queued` | 迁移后新建任务 stage 默认 QUEUED |

#### 3.5 现有测试适配：单元测试

##### 3.5.1 `tests/test_task_context_lifecycle.py`（12 个用例）

**当前**: 直接构造 dict 模拟任务，断言 `status == "PROCESSING"` / `"CONFIRMING"` / `"NEEDS_REVIEW"` 等

| # | 用例 | 适配内容 |
|---|------|---------|
| 3.5.1.1 | `test_lifecycle_transition_table_records_core_contract` | 全部 7 种状态的断言改为 status+stage 联合断言 |
| 3.5.1.2 | `test_start_processing_sets_status_and_started_at` | `status == "PROCESSING"` → `status == "PENDING" and stage == "RUNNING"` |
| 3.5.1.3 | `test_mark_confirming_can_preserve_error_message_when_no_reason` | `status == "CONFIRMING"` → `status == "PENDING" and stage == "AWAIT_REVIEW"` |
| 3.5.1.4 | `test_mark_confirming_records_reason_when_provided` | 同上 |
| 3.5.1.5 | `test_mark_needs_review_records_temp_location` | `status == "NEEDS_REVIEW"` → `status == "PENDING" and stage == "AWAIT_REVIEW"` |
| 3.5.1.6 | `test_mark_failed_can_clear_or_preserve_video_path` | `status == "FAILED"` 不变，新增 `stage == "DONE"` |
| 3.5.1.7 | `test_mark_skipped_records_completion_and_location` | `status == "SKIPPED"` 不变，新增 `stage == "DONE"` |
| 3.5.1.8 | `test_mark_imported_records_success_fields` | `status == "SUCCESS"` 不变，新增 `stage == "DONE"` |
| 3.5.1.9 | `test_reset_for_retry_resets_runtime_fields` | `status == "PENDING"` 不变，新增 `stage == "QUEUED"` |
| 3.5.1.10 | `test_mark_temp_ready_tracks_current_temp_video` | 无需改（不涉及 status/stage） |

##### 3.5.2 `tests/test_task_operations.py`（~15 个用例）

**当前**: 使用真实 SQLite DB，通过 `_create_task` + `update_task` 设置状态

| # | 用例 | 适配内容 |
|---|------|---------|
| 3.5.2.1 | `test_retry_failed_task` | 重试后断言 `status == "PENDING" and stage == "QUEUED"` |
| 3.5.2.2 | `test_retry_pending_task_should_fail` | 条件不变（PENDING 不允许重试） |
| 3.5.2.3 | `test_retry_success_task_should_fail` | 条件不变 |
| 3.5.2.4 | `test_retry_confirming_task_should_fail` | 改为 `test_retry_await_review_task_should_fail`：stage=AWAIT_REVIEW 不允许重试 |
| 3.5.2.5 | `test_ignore_task` | ignore 后断言 `status == "SKIPPED" and stage == "DONE"` |
| 3.5.2.6 | `test_check_source_duplicate_processing_file` | PROCESSING → `status=PENDING, stage=RUNNING` 时 action=SKIP |
| 3.5.2.7 | `test_check_source_duplicate_confirming_file` | CONFIRMING → `status=PENDING, stage=AWAIT_REVIEW` 时 action=SKIP |
| 3.5.2.8 | `test_pagination_with_status_filter` | `status=FAILED` 不变，新增 `test_pagination_with_stage_filter` |
| 3.5.2.9 | `test_retry_all_failed` | 重试后全部为 PENDING/QUEUED |
| 3.5.2.10 | `test_api_confirm_all_finds_confirming_tasks` | `list_tasks(status="CONFIRMING")` → `list_tasks(status="PENDING", stage="AWAIT_REVIEW")` |

**辅助函数适配**: `_create_task` 需在 `update_task` 时同时设置 `stage` 字段

##### 3.5.3 `tests/test_feature_task_queue.py`（7 个用例）

**当前**: 使用 FakeTaskManager 伪对象

| # | 用例 | 适配内容 |
|---|------|---------|
| 3.5.3.1 | `test_clear_tasks_normalizes_all_status` | 不变 |
| 3.5.3.2 | `test_clear_tasks_rejects_invalid_status` | 新增 `test_clear_tasks_rejects_invalid_stage` |
| 3.5.3.3 | `test_retry_task_starts_pipeline_when_available` | 返回值 status=PENDING 不变，新增 stage=QUEUED |
| 3.5.3.4 | `test_pause_resume_and_status_payloads` | `FakeTaskManager.counts` 改为按 status+stage 分组 |

##### 3.5.4 `tests/test_feature_task_list.py`（3 个用例）

**当前**: mock `db_list_tasks`，验证 status 过滤

| # | 用例 | 适配内容 |
|---|------|---------|
| 3.5.4.1 | `test_list_tasks_for_api_builds_pagination_payload` | 新增 `stage` 参数传递验证 |
| 3.5.4.2 | `test_list_tasks_for_api_rejects_invalid_status` | 新增 `test_list_tasks_for_api_rejects_invalid_stage` |
| 3.5.4.3 | 新增 `test_list_tasks_for_api_filters_by_status_and_stage` | 验证 `status=PENDING&stage=AWAIT_REVIEW` 组合过滤 |
| 3.5.4.4 | 新增 `test_list_tasks_for_api_supports_multi_status` | 验证 `status=SUCCESS&status=SKIPPED` 多值过滤 |

##### 3.5.5 `tests/test_feature_task_review.py`（5 个用例）

**当前**: FakeTaskManager + FakePipeline

| # | 用例 | 适配内容 |
|---|------|---------|
| 3.5.5.1 | `test_confirm_task_returns_success_message` | 任务数据改为 `status=PENDING, stage=AWAIT_REVIEW` |
| 3.5.5.2 | `test_reclassify_task_returns_updated_task_payload` | 断言 `status == "CONFIRMING"` → 断言 `stage == "AWAIT_REVIEW"` |
| 3.5.5.3 | `test_confirm_all_tasks_returns_success_and_failure_counts` | `list_tasks(status="CONFIRMING")` → `list_tasks(status="PENDING", stage="AWAIT_REVIEW")` |
| 3.5.5.4 | 新增 `test_confirm_rejects_non_await_review_task` | stage != AWAIT_REVIEW 时返回 400 |

##### 3.5.6 `tests/test_feature_task_delete.py`（2 个用例）

| # | 用例 | 适配内容 |
|---|------|---------|
| 3.5.6.1 | `test_delete_task_rejects_processing_task` | `status=PROCESSING` → `status=PENDING, stage=RUNNING` |
| 3.5.6.2 | `test_delete_task_cleans_temp_file_and_deletes_record` | 任务数据改为 `status=PENDING, stage=QUEUED` |

##### 3.5.7 `tests/test_feature_task_detail.py`（3 个用例）

| # | 用例 | 适配内容 |
|---|------|---------|
| 3.5.7.1 | `test_get_task_returns_payload` | 返回 payload 包含 `stage` 字段 |
| 3.5.7.2 | `test_get_task_stats_returns_status_counts` | 统计结果包含 stage 维度 |

##### 3.5.8 `tests/test_feature_task_file_lifecycle.py`（6 个用例）

| # | 用例 | 适配内容 |
|---|------|---------|
| 3.5.8.1 | `test_ignore_temp_task_cleans_temp_files_and_recycles_source` | 断言 `status == "SKIPPED"` + `stage == "DONE"` |
| 3.5.8.2 | `test_ignore_source_task_recycles_source_when_cleanup_enabled` | 同上 |
| 3.5.8.3 | `test_ignore_task_rejects_invalid_status` | PENDING/QUEUED 不可忽略，PENDING/RUNNING 不可忽略，PENDING/AWAIT_REVIEW 可忽略 |
| 3.5.8.4 | 新增 `test_ignore_sets_stage_done_via_mark_skipped` | 验证 ignore 调用了 `mark_skipped()` 而非直接写 status |

##### 3.5.9 `tests/test_architecture_guards.py`

| # | 用例 | 适配内容 |
|---|------|---------|
| 3.5.9.1 | 导入检查 | 确认 `STAGE_*` 常量可从 `features.tasks` 正确导入 |
| 3.5.9.2 | 依赖方向 | 确认新文件 classify_preview_handler 的导入方向合规 |

##### 3.5.10 `tests/test_import_flow_services.py`（~10 个用例）

| # | 用例 | 适配内容 |
|---|------|---------|
| 3.5.10.1 | `test_gate_blocked_requires_review` | FakeConfidenceEngine("NEEDS_REVIEW") → 决策仍为 needs_review，但最终映射到 stage=AWAIT_REVIEW |
| 3.5.10.2 | `test_low_confidence_fails` | FakeConfidenceEngine("FAILED") → 决策为 failed，映射到 status=FAILED, stage=DONE |
| 3.5.10.3 | `test_missing_required_fields_requires_confirm` | 决策为 confirm → 映射到 status=PENDING, stage=AWAIT_REVIEW |

##### 3.5.11 `tests/test_confidence_engine.py`（3 个用例）

| # | 用例 | 适配内容 |
|---|------|---------|
| 3.5.11.1 | `test_confidence_levels` | "CONFIRMING" 和 "NEEDS_REVIEW" 等级名称保持不变（这是置信度等级，不是任务状态），但需添加注释说明映射关系 |

#### 3.6 现有测试适配：集成测试

##### 3.6.1 `tests/test_integration_recycle.py`（~8 个用例，需 `--run-service-integration`）

**当前**: 启动真实 HTTP 服务器，通过 DB repo 直接操作

| # | 用例 | 适配内容 |
|---|------|---------|
| 3.6.1.1 | `test_tasks_return_provider_type_and_id` | `_db_create_task` 新增 stage 参数 |
| 3.6.1.2 | `test_task_with_recycle_file_location_returned` | status=FAILED 不变，新增 stage=DONE |
| 3.6.1.3 | `test_task_with_source_file_location_shows_correctly` | status=PENDING + stage=QUEUED |
| 3.6.1.4 | `test_task_ignore_moves_file_to_recycle` | ignore 后断言 `status == "SKIPPED" and stage == "DONE"` |
| 3.6.1.5 | `test_delete_task_with_delete_files_preserves_recycle_file` | stage=DONE |
| 3.6.1.6 | `test_duplicate_fingerprint_gets_rename_detected` | SUCCESS+PENDING → SUCCESS/DONE + PENDING/QUEUED |

**辅助函数适配**: `_db_create_task` 的 INSERT 语句需新增 `stage` 列

##### 3.6.2 `tests/test_api_routes.py`

| # | 用例 | 适配内容 |
|---|------|---------|
| 3.6.2.1 | 路由匹配测试 | 新增 classify-preview 路由匹配验证 |

#### 3.7 现有测试适配：E2E 回归测试

##### 3.7.1 `tests/test_e2e_02_scan.py`（9 个用例，需 `--run-live-e2e`）

**当前**: 扫描源文件 → 等待处理 → 验证最终状态

| # | 用例 | 适配内容 |
|---|------|---------|
| 3.7.1.1 | `test_t01_new_task_shows_pending` | 新任务断言 stage=QUEUED |
| 3.7.1.2 | `test_t02_success_after_processing` | 成功后 stage=DONE |
| 3.7.1.3 | `test_t03_failed_shows_error_info` | 失败后 stage=DONE |
| 3.7.1.4 | `test_t04_low_confidence_shows_confirming` | 断言 stage=AWAIT_REVIEW（前端显示"待确认"） |
| 3.7.1.5 | `test_t05_confirm_confirming_task_to_success` | 确认后 status=SUCCESS, stage=DONE |
| 3.7.1.6 | `test_t06_ignore_confirming_task_to_skipped` | 忽略后 status=SKIPPED, stage=DONE |
| 3.7.1.7 | `test_t07_retry_failed_task` | 重试后 status=PENDING, stage=QUEUED → RUNNING |
| 3.7.1.8 | `test_t08_failed_beyond_retry_to_recycle` | 不变（FAILED 终态） |
| 3.7.1.9 | `test_t09_success_is_terminal` | 不变 |

##### 3.7.2 `tests/test_e2e_03_task_actions.py`（~12 个用例，需 `--run-live-e2e`）

**当前**: 通过 SQLite INSERT 构造指定状态任务，Playwright 验证前端行为

| # | 用例 | 适配内容 |
|---|------|---------|
| 3.7.2.1 | `test_A01_click_task_card_opens_detail_modal` | INSERT 新增 stage=DONE |
| 3.7.2.2 | `test_A03_failed_task_shows_error_highlighted` | INSERT 新增 stage=DONE |
| 3.7.2.3 | `test_A09_retry_failed_task_changes_status` | 验证重试后前端显示"排队中" |
| 3.7.2.4 | `test_A10_confirm_confirming_task_succeeds` | INSERT 改为 `status=PENDING, stage=AWAIT_REVIEW`，验证确认成功 |
| 3.7.2.5 | `test_A11_ignore_confirming_task_skipped` | INSERT 改为 `status=PENDING, stage=AWAIT_REVIEW` |
| 3.7.2.6 | `test_A12_delete_task_confirm_removes` | 不变 |
| 3.7.2.7 | `test_A14_filter_all_shows_all_tasks` | 不变 |
| 3.7.2.8 | `test_A15_filter_pending_shows_pending_tasks` | 筛选条件改为 PENDING/QUEUED + PENDING/RUNNING |
| 3.7.2.9 | `test_A16_filter_confirm_shows_confirming_tasks` | 筛选条件改为 PENDING/AWAIT_REVIEW |
| 3.7.2.10 | `test_A17_filter_failed_shows_failed_tasks` | 不变 |
| 3.7.2.11 | `test_A18_filter_success_shows_success_tasks` | 不变 |
| 3.7.2.12 | `test_A20_switch_filter_clears_selection` | 不变 |

**辅助函数适配**: `_create_terminal_task` 的 INSERT 语句需新增 `stage` 列

##### 3.7.3 `tests/test_e2e_06_batch.py`（~7 个用例，需 `--run-live-e2e`）

**当前**: 批量操作测试

| # | 用例 | 适配内容 |
|---|------|---------|
| 3.7.3.1 | `test_B01_select_single_task_shows_count` | INSERT 新增 stage=DONE |
| 3.7.3.2 | `test_B06_batch_retry_failed_tasks` | 重试 SKIPPED 任务，验证变为 QUEUED |
| 3.7.3.3 | `test_B07_batch_confirm_confirming_tasks` | INSERT 改为 `status=PENDING, stage=AWAIT_REVIEW` |
| 3.7.3.4 | `test_B08_batch_ignore_tasks` | FAILED 任务 ignore 后 stage=DONE |
| 3.7.3.5 | `test_B09_batch_delete_tasks` | 不变 |
| 3.7.3.6 | `test_B12_filter_all_retry_hidden` | 不变 |
| 3.7.3.7 | `test_B13_filter_failed_retry_visible` | 不变 |

**辅助函数适配**: `_create_terminal_task` 和 `_set_task_status` 需同时设置 `stage`

##### 3.7.4 `tests/test_frontend_recycle.py`（2 个用例，需 `--run-ui`）

| # | 用例 | 适配内容 |
|---|------|---------|
| 3.7.4.1 | `test_tasks_file_location_labels` | mock 数据新增 stage 字段 |
| 3.7.4.2 | `test_tasks_recycle_css_class` | 不变 |

#### 3.8 新增测试：前端 E2E 回归

##### 3.8.1 筛选 Chip 验证（新增用例到 test_e2e_03_task_actions.py）

| # | 用例 | 验证点 |
|---|------|--------|
| 3.8.1.1 | `test_filter_queued_shows_queued_tasks` | 排队中 Chip 只显示 PENDING/QUEUED 任务 |
| 3.8.1.2 | `test_filter_running_shows_running_tasks` | 处理中 Chip 只显示 PENDING/RUNNING 任务 |
| 3.8.1.3 | `test_filter_review_shows_await_review_tasks` | 待确认 Chip 只显示 PENDING/AWAIT_REVIEW 任务 |

##### 3.8.2 按钮逻辑验证（新增用例到 test_e2e_03_task_actions.py）

| # | 用例 | 验证点 |
|---|------|--------|
| 3.8.2.1 | `test_running_task_has_no_secondary_action` | PENDING/RUNNING 任务卡片无次按钮 |
| 3.8.2.2 | `test_await_review_task_shows_confirm_and_edit` | PENDING/AWAIT_REVIEW 任务显示"确认"+"修改" |
| 3.8.2.3 | `test_edit_button_opens_modal_with_preview` | "修改"按钮打开编辑弹窗，包含入库预览按钮 |
| 3.8.2.4 | `test_classify_preview_shows_correct_path` | 入库预览返回正确的目录路径和文件名 |

##### 3.8.3 批量操作规则验证（新增用例到 test_e2e_06_batch.py）

| # | 用例 | 验证点 |
|---|------|--------|
| 3.8.3.1 | `test_batch_confirm_only_for_await_review` | 只有 PENDING/AWAIT_REVIEW 任务可批量确认 |
| 3.8.3.2 | `test_batch_ignore_for_await_review_and_failed` | AWAIT_REVIEW 和 FAILED 可批量忽略 |
| 3.8.3.3 | `test_batch_recycle_hidden_when_all_success` | 全部 SUCCESS 时批量移入回收按钮隐藏 |

#### 3.9 不需要适配的测试文件

以下文件不涉及 status/stage 逻辑，无需修改：

| 文件 | 原因 |
|------|------|
| `tests/test_config_consumers.py` | 配置消费测试，不涉及任务状态 |
| `tests/test_config_save_load_e2e.py` | 配置保存加载，不涉及任务状态 |
| `tests/test_feature_entrypoints.py` | feature 入口点检查，不涉及具体状态值 |
| `tests/test_recycle_safety.py` | 回收安全测试，使用固定 file_location |
| `tests/test_feature_import_flow_run_file.py` | 使用 FakeTaskManager，不检查具体 status 值 |
| `tests/test_feature_configuration_runtime.py` | 配置运行时测试 |
| `tests/test_feature_prompts_application.py` | 提示词测试 |
| `tests/test_feature_dimensions_service.py` | 维度服务测试 |
| `tests/test_feature_configuration_application.py` | 配置应用测试 |
| `tests/test_feature_source_cleaning.py` | 源文件清理测试 |
| `tests/test_feature_providers.py` | Provider 测试 |
| `tests/test_feature_import_flow.py` | 导入流程测试（不直接断言 status 值） |
| `tests/test_config_view.py` | ConfigView 测试 |
| `tests/test_consult_prompt.py` | 提示词咨询测试 |
| `tests/test_e2e_01_config.py` | 配置 E2E 测试 |
| `tests/test_e2e_04_recycle.py` | 回收站 E2E（不依赖 status） |
| `tests/test_e2e_05_navigation.py` | 导航 E2E |
| `tests/test_e2e_07_visual.py` | 视觉 E2E |
| `tests/test_confidence_v2_ui.py` | 置信度 UI（外部服务） |
| `tests/test_confidence_ui.py` | 置信度 UI（外部服务） |
| `tests/test_scrape_ui.py` | 刮削 UI（外部服务） |
| `tests/test_confidence_config_ui.py` | 置信度配置 UI（外部服务） |

#### 3.10 测试执行命令

```bash
# Phase 1 完成后：运行非 UI/E2E 测试
python -m pytest tests/ \
  --ignore=tests/test_*_ui.py \
  --ignore=tests/test_frontend_*.py \
  --ignore=tests/test_scrape_ui.py \
  --ignore=tests/test_e2e_*.py \
  --ignore=tests/test_integration_recycle.py \
  -v

# Phase 1 完成后：集成测试
python -m pytest tests/test_integration_recycle.py --run-service-integration -v

# Phase 2 完成后：E2E 回归测试
python -m pytest tests/test_e2e_02_scan.py tests/test_e2e_03_task_actions.py tests/test_e2e_06_batch.py \
  --run-live-e2e -v

# Phase 3 完成后：全量测试
python -m pytest tests/ -v

# 编译检查
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer tests
```

#### 3.11 测试统计

| 类别 | 文件数 | 用例数（估） | 新增用例 |
|------|--------|-------------|---------|
| 新增 Unit | 3 | ~30 | 全部 |
| 适配 Unit | 10 | ~55 | ~8 |
| 适配 Integration | 2 | ~10 | 0 |
| 适配 E2E | 3 | ~28 | 0 |
| 新增 E2E | 0（追加到现有文件） | ~10 | 全部 |
| 不需修改 | 22 | - | 0 |
| **合计** | **40** | **~133** | **~48** |

---

### Phase 4：文档

| # | 文件 | 更新内容 |
|---|------|---------|
| 4.1 | `docs/architecture/task-lifecycle.md` | 状态机图改为双层模型 |
| 4.2 | `docs/features/tasks.md` | 服务矩阵增加 stage 列 |
| 4.3 | `docs/standards/api.md` | API 新增 stage 参数、classify-preview 端点 |
| 4.4 | `docs/testing/regression-matrix.md` | 测试矩阵适配 |
| 4.5 | `docs/INDEX.md` | 变更索引更新 |

---

## 八、验收标准

### 功能验收

- [ ] DB 新增 stage 列，所有旧数据正确迁移
- [ ] NEEDS_REVIEW 状态不再存在
- [ ] PROCESSING 状态不再作为 status 值（改为 stage=RUNNING）
- [ ] CONFIRMING 状态不再作为 status 值（改为 stage=AWAIT_REVIEW）
- [ ] 前端 6 个筛选 Chip 全部正常工作
- [ ] PENDING/RUNNING 状态只显示"查看"，无其他操作按钮
- [ ] PENDING/AWAIT_REVIEW 状态显示"确认"和"修改"
- [ ] "修改"弹窗中可同时修改维度和文件名
- [ ] "入库预览"按钮可预览目标目录和最终文件名
- [ ] 所有批量操作按钮按新规则正确显示/隐藏
- [ ] 重试、确认、忽略、删除操作正确校验 status+stage
- [ ] 入库预览结果与实际入库路径一致

### 质量验收

- [ ] 全部现有测试通过（含适配后的修改）
- [ ] 新增 classify-preview 和 stage 转换的测试
- [ ] Playwright E2E 验证所有筛选和操作按钮
- [ ] `python -m compileall -q media_importer tests` 编译检查通过
- [ ] 文档同步更新

---

## 九、风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| ~40 个文件改动，回归风险高 | Phase 1 完成后先跑全量测试再进入 Phase 2 |
| DB 迁移不可逆 | stage 列是新增（ADD COLUMN），不删除旧列，可回退 |
| NEEDS_REVIEW 合并可能导致确认流程异常 | 合并后 confirm_task 同时接受原 CONFIRMING 和原 NEEDS_REVIEW（都映射到 AWAIT_REVIEW） |
| file_lifecycle_service.py 绕过 task_lifecycle | 修复为调用 mark_skipped() 确保 stage 正确 |
| 前端硬编码状态字符串多 | 统一由 TASK_FILTER_PARAMS 常量管理 |
| 入库预览与实际入库结果不一致 | preview 复用完全相同的 ClassificationService 代码路径 |
| 状态常量双源 | 统一以 task_lifecycle.py 为权威源，constants.py 的 VALID_STATUSES 从 task_lifecycle 导入 |
| 旧版 tasks.js 未同步 | Phase 2 最后一个任务专门处理旧版 UI |

---

## 十、执行顺序与提交策略

```
Phase 1（后端核心）→ 全量测试 → git commit
                → Phase 2（前端核心）→ Playwright 验证 → git commit
                → Phase 3（测试补全）→ 全量测试 → git commit
                → Phase 4（文档）→ git commit
```

**每个 Phase 完成后提交一次，共 4 次提交。**

### Phase 内执行顺序

**Phase 1 推荐顺序**（依赖关系）:
```
1.1 constants → 1.2 DB 迁移 → 1.3 task_lifecycle → 1.4 task_repo → 1.5 task_manager
                                                                    ↓
1.7 ClassificationService preview ← 独立，可并行 ← 1.6 API handler ← 1.16 routes
                  ↓
1.8 list_service → 1.9 queue_service → 1.10 review_service
1.11 file_lifecycle → 1.12 delete_service → 1.13 runner → 1.14 confirm
1.15 handler → 1.17 metrics
```

**Phase 2 推荐顺序**:
```
2.1 筛选映射 → 2.2 按钮逻辑 → 2.3 批量操作 → 2.4 编辑模式 + 入库预览 → 2.5 metrics → 2.6 CSS → 2.7 旧版
```

---

## 十一、关键文件索引

### 后端（按修改优先级）

| 文件 | 修改类型 | 行数影响 |
|------|---------|---------|
| `media_importer/core/db/constants.py` | 新增常量、更新表定义 | ~20 行 |
| `media_importer/core/db/connection.py` | 新增迁移逻辑 | ~15 行 |
| `media_importer/core/task_lifecycle.py` | 所有转换函数加 stage | ~40 行 |
| `media_importer/core/db/task_repo.py` | SQL 适配 + valid_columns | ~50 行 |
| `media_importer/core/task_manager.py` | 状态判断适配 | ~30 行 |
| `media_importer/features/import_flow/services/classification.py` | 新增 preview 方法 | ~30 行 |
| `media_importer/features/tasks/list_service.py` | stage 参数支持 | ~20 行 |
| `media_importer/features/tasks/file_lifecycle_service.py` | 修复绕过 + stage | ~15 行 |
| `media_importer/features/tasks/delete_service.py` | stage 校验 | ~10 行 |
| `media_importer/features/import_flow/runner.py` | 状态读取适配 | ~10 行 |
| `media_importer/features/import_flow/confirm.py` | 状态检查改为 stage | ~10 行 |
| `media_importer/api/routes.py` | 新增路由 | ~3 行 |
| `media_importer/api/handler.py` | metrics/启动适配 | ~10 行 |
| `media_importer/core/metrics.py` | by_stage 统计 | ~15 行 |
| `media_importer/features/tasks/queue_service.py` | 参数适配 | ~10 行 |
| `media_importer/features/tasks/review_service.py` | stage 条件 | ~10 行 |

### 前端

| 文件 | 修改类型 | 行数影响 |
|------|---------|---------|
| `media_importer/webui/js/cinema-app.js` | 筛选映射重构 | ~40 行 |
| `media_importer/webui/js/cinema-tasks.js` | 按钮 + 编辑 + 预览 | ~100 行 |
| `media_importer/webui/css/cinema-pages.css` | badge 样式 | ~15 行 |
| `media_importer/webui/js/tasks.js` | 旧版同步 | ~20 行 |

### 新增文件

| 文件 | 内容 |
|------|------|
| `media_importer/api/classify_preview_handler.py`（或扩展 task_handlers.py） | 入库预览 handler |
| `tests/test_stage_lifecycle.py` | stage 转换测试 |
| `tests/test_classify_preview.py` | 入库预览测试 |
