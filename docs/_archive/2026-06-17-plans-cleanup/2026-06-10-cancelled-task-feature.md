# CANCELLED 任务取消能力实现计划

> 日期: 2026-06-10 | 状态: complete

---

## 一、背景

status + stage 双层模型已将 `CANCELLED` 定义为终态，但当前代码只有常量、DB 合法值、前端展示和筛选，没有任何后端业务路径会产生 `CANCELLED`。

这会导致：

1. 前端存在“已取消”筛选，但真实任务永远不会进入该状态；
2. 架构文档和实现不一致；
3. 用户无法对排队任务执行“取消但保留记录”的操作，只能删除记录或忽略任务。

---

## 二、目标与非目标

### 目标

1. 增加 `mark_cancelled()` 生命周期函数；
2. 增加 TaskManager 取消排队任务能力；
3. 增加 `POST /api/tasks/{task_id}/cancel` API；
4. 前端对 `PENDING/QUEUED` 任务显示“取消”操作；
5. `CANCELLED` 任务可通过已有重试逻辑重新投入队列；
6. 补充单元测试、API 路由测试和架构文档。

### 非目标

1. 不支持强制中断 `PENDING/RUNNING` 正在处理的任务；
2. 不支持取消 `PENDING/AWAIT_REVIEW` 待确认任务；
3. 不引入新的 DB 字段；
4. 不调整 import-flow runner 的执行中断机制。

---

## 三、设计决策

### D1：V1 只允许取消 QUEUED

RUNNING 任务当前没有步骤级取消检查点，强行改状态会产生竞态和临时文件残留风险。因此 V1 只允许：

```text
PENDING/QUEUED --cancel--> CANCELLED/DONE
```

其他状态返回 400。

### D2：取消原因复用 error_message

为避免 DB 迁移，本次不增加 `cancel_reason` 字段，取消原因写入 `error_message`。

### D3：取消不移动源文件

排队任务尚未进入 temp/import，正常情况下 `file_location=source`。取消只改变任务状态，不移动源文件、不删除文件。

### D4：CANCELLED 可重试

`retry_task()` 和 `retry_all_failed()` 支持 `CANCELLED`，使用户可将已取消任务重新投入队列。

---

## 四、任务清单

- [x] `media_importer/core/task_lifecycle.py` 添加 `mark_cancelled()`；
- [x] `media_importer/core/task_manager.py` 添加 `cancel_task()`，并让 retry 支持 CANCELLED；
- [x] `media_importer/features/tasks/cancel_service.py` 添加 `cancel_task_for_api()`；
- [x] `media_importer/features/tasks/__init__.py` 导出 `mark_cancelled` 和 `cancel_task_for_api`；
- [x] `media_importer/api/task_handlers.py` 添加 `_task_cancel()`；
- [x] `media_importer/api/routes.py` 注册 `POST /api/tasks/{task_id}/cancel`；
- [x] `media_importer/webui/js/cinema-tasks.js` 添加取消按钮、确认弹窗、已取消重试入口；
- [x] `tests/test_feature_task_cancel.py` 覆盖生命周期、TaskManager、API service；
- [x] `tests/test_api_routes.py` 补充 cancel 路由断言；
- [x] `docs/architecture/task-lifecycle.md` 同步 transition table；
- [x] 运行专项测试、非 UI 测试和编译检查。

---

## 五、验收标准

1. `PENDING/QUEUED` 任务调用 cancel 后变为 `CANCELLED/DONE`；
2. `PENDING/RUNNING`、`PENDING/AWAIT_REVIEW`、`SUCCESS`、`FAILED`、`SKIPPED` 取消返回 400；
3. `GET /api/tasks?status=CANCELLED` 能查到取消后的任务；
4. CANCELLED 任务可点击重试，变回 `PENDING/QUEUED`；
5. 前端排队任务显示“取消”，运行中任务不显示“取消”；
6. 测试和编译检查通过。
