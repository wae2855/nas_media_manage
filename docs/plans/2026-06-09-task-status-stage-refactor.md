# 任务状态模型重构：status + stage 双层方案

> 版本: v2.0 | 日期: 2026-06-09 | 状态: 待实施
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

| status/stage | 主按钮 | 次按钮 |
|-------------|--------|--------|
| PENDING/QUEUED | 查看 | 移入回收 |
| PENDING/RUNNING | 查看 | —（**无操作**） |
| PENDING/AWAIT_REVIEW | 确认 | 修改 |
| SUCCESS | 查看结果 | — |
| FAILED | 重试 | 移入回收 |
| SKIPPED | 重试 | — |
| CANCELLED | 查看 | — |

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

### Phase 3：测试

#### 3.1 conftest.py fixture 适配

**文件**: `tests/conftest.py`

所有创建 task 的 fixture 需设置 `stage` 字段。默认 `stage="QUEUED"`。

#### 3.2 新增 stage 转换测试

**新文件**: `tests/test_stage_lifecycle.py`

测试内容：
- 每个转换函数正确设置 status + stage
- `mark_confirming()` 和 `mark_needs_review()` 都映射到 `PENDING/AWAIT_REVIEW`
- `reset_for_retry()` 设置 `stage=QUEUED`
- 无效转换被拒绝

#### 3.3 新增 classify-preview 测试

**新文件**: `tests/test_classify_preview.py`

测试内容：
- 不带覆盖参数的预览
- 带 dimensions 覆盖的预览
- 带 filename 覆盖的预览
- 不存在的 task_id 返回 404
- 不执行任何文件操作（mock 验证）

#### 3.4 现有测试适配

需要检查并适配的测试文件：

| 文件 | 适配内容 |
|------|---------|
| `tests/test_task_context_lifecycle.py` | 状态断言改为 status+stage |
| `tests/test_task_operations.py` | 操作前置条件改为 stage 感知 |
| `tests/test_feature_task_list.py` | 列表查询参数新增 stage |
| `tests/test_feature_task_queue.py` | 队列操作状态检查 |
| `tests/test_feature_task_review.py` | 确认操作改为 stage 检查 |
| `tests/test_feature_task_delete.py` | 删除状态校验 |
| `tests/test_feature_task_detail.py` | 任务详情返回 stage 字段 |
| `tests/test_feature_task_file_lifecycle.py` | ignore 操作需设置 stage |
| `tests/test_architecture_guards.py` | 导入检查新增 stage 相关 |
| `tests/test_e2e_02_scan.py` | E2E 扫描后状态验证 |
| `tests/test_e2e_03_task_actions.py` | E2E 操作按钮验证 |
| `tests/test_e2e_06_batch.py` | E2E 批量操作验证 |

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
