# 任务状态模型重构：status + stage 双层方案

> 版本: v1.0 | 日期: 2026-06-09 | 状态: 待实施
> 基线提交: d23a250 (feat(webui): cinema UI 全面优化 + 多项 bug 修复)

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

点击"修改"按钮进入编辑弹窗，用户可自由操作：
1. 修改分类维度（下拉/输入）
2. 修改文件名（输入框）
3. 点击**入库预览**按钮 → 调用 `POST /api/tasks/{id}/classify-preview`
4. 预览结果展示：目标目录路径 + 最终文件名
5. 确认后调用 reclassify 入库

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

### 后端实现

复用现有 `ClassificationService` 和 `render_template`：
- 不执行任何文件操作
- 只做规则匹配 + 路径计算 + 返回结果
- 如果请求体包含 dimensions，用临时值覆盖任务的 scrape_dimensions

---

## 六、DB 变更

### 新增列

```sql
ALTER TABLE tasks ADD COLUMN stage TEXT DEFAULT 'QUEUED';
```

### 数据迁移

```sql
UPDATE tasks SET stage='RUNNING'      WHERE status='PROCESSING';
UPDATE tasks SET stage='AWAIT_REVIEW' WHERE status IN ('CONFIRMING','NEEDS_REVIEW');
UPDATE tasks SET stage='DONE'         WHERE status IN ('SUCCESS','FAILED','SKIPPED');
UPDATE tasks SET stage='QUEUED'       WHERE status='PENDING';
```

### 旧状态迁移

```sql
-- NEEDS_REVIEW 合并到 CONFIRMING（迁移前）
UPDATE tasks SET status='CONFIRMING' WHERE status='NEEDS_REVIEW';
-- 之后再统一迁移 stage
```

---

## 七、开发任务清单

### Phase 1：后端核心（~15 文件）

| # | 任务 | 涉及文件 | 依赖 |
|---|------|---------|------|
| 1.1 | constants.py：新增 STAGE_* 常量、STAGE_VALID_VALUES、更新 VALID_STATUSES | constants.py | 无 |
| 1.2 | DB 迁移：新增 stage 列 + 数据迁移脚本 | connection.py | 1.1 |
| 1.3 | task_lifecycle.py：8 个转换函数改为同时设置 status+stage | task_lifecycle.py | 1.1 |
| 1.4 | task_repo.py：10 条 SQL 适配 stage 条件 | task_repo.py | 1.2 |
| 1.5 | task_manager.py：33 处引用适配 | task_manager.py | 1.3, 1.4 |
| 1.6 | 新增 classify-preview API handler | task_handlers.py 或新文件 | 1.5 |
| 1.7 | ClassificationService 增加 preview 方法 | classification.py | 无 |
| 1.8 | list_service.py：list_tasks 支持 stage 参数 | list_service.py | 1.4 |
| 1.9 | queue_service.py：clear/retry 适配 | queue_service.py | 1.5 |
| 1.10 | review_service.py：confirm-all 适配 | review_service.py | 1.5 |
| 1.11 | file_lifecycle_service.py：ignore/delete 适配 | file_lifecycle_service.py | 1.3 |
| 1.12 | delete_service.py：status 校验改为 stage 感知 | delete_service.py | 1.3 |
| 1.13 | runner.py：流水线步骤改用 stage | runner.py | 1.3 |
| 1.14 | confirm.py：confirm/reclassify 适配 | confirm.py | 1.3 |
| 1.15 | handler.py：启动逻辑、metrics 适配 | handler.py | 1.5 |
| 1.16 | routes.py：新增 classify-preview 路由 | routes.py | 1.6 |
| 1.17 | metrics.py：by_status 改为 by_status+by_stage | metrics.py | 1.5 |

### Phase 2：前端核心（~7 文件）

| # | 任务 | 涉及文件 | 依赖 |
|---|------|---------|------|
| 2.1 | TASK_FILTER_MAP 改为 status+stage 双参数 | cinema-app.js | Phase 1 |
| 2.2 | taskPrimaryAction/taskSecondaryAction 改为 stage 感知 | cinema-tasks.js | 2.1 |
| 2.3 | 批量操作按钮逻辑适配 | cinema-tasks.js | 2.2 |
| 2.4 | 任务详情弹窗：AWAIT_REVIEW 编辑模式 + 入库预览按钮 | cinema-tasks.js | 2.2 |
| 2.5 | 入库预览 UI：弹窗中展示预览路径 | cinema-tasks.js | 1.6 |
| 2.6 | 首页 metrics 展示适配 | cinema-app.js | 2.1 |
| 2.7 | CSS badge 颜色适配 | cinema-pages.css | 2.2 |
| 2.8 | 旧版 tasks.js 同步适配 | tasks.js | 2.1 |

### Phase 3：测试（~19 文件）

| # | 任务 | 涉及文件 | 依赖 |
|---|------|---------|------|
| 3.1 | conftest.py：fixture 适配 stage | conftest.py | Phase 1 |
| 3.2 | task_lifecycle 单测 | test_task_context_lifecycle.py | 3.1 |
| 3.3 | task_operations 单测 | test_task_operations.py | 3.1 |
| 3.4 | task_list 单测 | test_feature_task_list.py | 3.1 |
| 3.5 | task_queue 单测 | test_feature_task_queue.py | 3.1 |
| 3.6 | task_review 单测 | test_feature_task_review.py | 3.1 |
| 3.7 | task_delete 单测 | test_feature_task_delete.py | 3.1 |
| 3.8 | task_detail 单测 | test_feature_task_detail.py | 3.1 |
| 3.9 | task_file_lifecycle 单测 | test_feature_task_file_lifecycle.py | 3.1 |
| 3.10 | architecture_guards 单测 | test_architecture_guards.py | 3.1 |
| 3.11 | E2E 扫描测试 | test_e2e_02_scan.py | 3.1 |
| 3.12 | E2E 任务操作测试 | test_e2e_03_task_actions.py | 3.1 |
| 3.13 | E2E 批量操作测试 | test_e2e_06_batch.py | 3.1 |
| 3.14 | 新增：classify-preview 单测 | test_classify_preview.py | 1.6 |
| 3.15 | 新增：stage 转换单测 | test_stage_lifecycle.py | 1.3 |
| 3.16 | 新增：E2E 入库预览测试 | test_e2e_08_classify_preview.py | Phase 2 |
| 3.17 | 其余测试文件适配 | ~5 files | 3.1 |

### Phase 4：文档（~5 文件）

| # | 任务 | 涉及文件 | 依赖 |
|---|------|---------|------|
| 4.1 | 更新 task-lifecycle.md | docs/architecture/task-lifecycle.md | Phase 1 |
| 4.2 | 更新 tasks.md | docs/features/tasks.md | Phase 1 |
| 4.3 | 更新 api.md | docs/standards/api.md | Phase 1 |
| 4.4 | 更新 regression-matrix.md | docs/testing/regression-matrix.md | Phase 3 |
| 4.5 | 新增 task-operations.md | docs/features/task-operations.md | Phase 2 |

---

## 八、验收标准

### 功能验收

- [ ] DB 新增 stage 列，所有旧数据正确迁移
- [ ] 前端 6 个筛选 Chip 全部正常工作
- [ ] PENDING/RUNNING 状态只显示"查看"，无其他操作按钮
- [ ] PENDING/AWAIT_REVIEW 状态显示"确认"和"修改"
- [ ] "修改"弹窗中可同时修改维度和文件名
- [ ] "入库预览"按钮可预览目标目录和最终文件名
- [ ] 所有批量操作按钮按新规则正确显示/隐藏
- [ ] 重试、确认、忽略、删除操作正确校验 status+stage
- [ ] NEEDS_REVIEW 状态不再存在（已合并到 CONFIRMING 再迁移）

### 质量验收

- [ ] 全部现有测试通过（19 个测试文件）
- [ ] 新增 classify-preview 和 stage 转换的测试
- [ ] Playwright E2E 验证所有筛选和操作按钮
- [ ] Python 编译检查通过
- [ ] 文档同步更新

---

## 九、风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| 53 个文件改动，回归风险高 | Phase 1 完成后先跑全量测试再进入 Phase 2 |
| DB 迁移不可逆 | stage 列是新增（ADD COLUMN），不删除旧列，可回退 |
| NEEDS_REVIEW 合并可能导致确认流程异常 | 合并后 confirm_task 同时接受原 CONFIRMING 和原 NEEDS_REVIEW |
| 前端硬编码状态字符串多 | 统一由 TASK_STATUS_MAP 和 TASK_STAGE_MAP 两个常量管理 |
| 入库预览与实际入库结果不一致 | preview 复用完全相同的 ClassificationService 代码路径 |

---

## 十、执行顺序

```
Phase 1（后端核心）→ 全量测试 → Phase 2（前端核心）→ Playwright 验证 → Phase 3（测试补全）→ Phase 4（文档）
```

每个 Phase 完成后提交一次，共 4 次提交。
