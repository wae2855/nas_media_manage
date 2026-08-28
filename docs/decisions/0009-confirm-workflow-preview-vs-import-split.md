# 0007 — 确认流程预览与入库解耦

**日期**：2026-06-16
**状态**：已实施
**关联需求**：REQ-20260616-000001（待确认流程端到端整治）
**关联计划**：[2026-06-16-confirm-workflow-overhaul-plan.md](../_archive/2026-08-22-plans-cleanup/2026-06-16-confirm-workflow-overhaul-plan.md)

---

## 背景

`reclassify_task` 原实现将"更新维度"和"执行入库"合成为一个动作，用户在待确认界面修改维度后点击"保存分类"即直接入库，违背"保存"的直觉语义。

## 决策

**拆分接口语义**：

1. **`POST /api/tasks/{id}/preview`**（新增）— 接收 dimensions / title_cn / title_en / year / filename 任一变更，更新 DB + 重跑分类规则，返回预览结果（import_path, final_filename），**不真正入库**。任务保持 `stage=AWAIT_REVIEW`。

2. **`POST /api/tasks/{id}/confirm`**（保留）— 真正入库。新增可选参数 `confirmed_title` 和 `override_source`，入库时落 `confirmed_override`/`confirmed_title`/`override_source` 三个字段。

3. **`POST /api/tasks/{id}/reclassify`**（兼容期保留）— 改为只更新维度 + 预览，不再触发入库。

## 新增 DB 字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `confirmed_override` | INTEGER | 0 | 是否换过元数据（1=是） |
| `confirmed_title` | TEXT | "" | 最终入库标题 |
| `override_source` | TEXT | "" | 来源：manual / candidate:tmdb:xxx / 空 |

## 新增 API 端点

### `POST /api/tasks/{id}/scrape-search`

确认界面内嵌重刮能力。接收 `query` + `year`，返回 Provider 多候选列表。

### `POST /api/tasks/{id}/preview`

预览元数据/维度/文件名变更。请求体任一子集：
```json
{"dimensions": {...}, "title_cn": "...", "title_en": "...", "year": 2023, "filename": "..."}
```

## 影响范围

- `features/import_flow/confirm.py`：新增 `preview_task`，`confirm_task` 增加 override 参数，`reclassify_task` 改为预览逻辑
- `features/tasks/review_service.py`：新增 `preview_task_for_api`
- `features/tasks/search_service.py`：新增 `search_provider_candidates`
- `api/task_handlers.py`：新增 `_task_preview`、`_task_scrape_search`
- `api/routes.py`：注册两个新路由
- `core/db/constants.py`：DDL 新增三列
- `core/db/connection.py`：ALTER TABLE migration
- `core/db/task_repo.py`：valid_columns + list_tasks SELECT 新增三列
- `core/task_lifecycle.py`：`reset_for_retry` 清空 override 字段
- 前端：详情面板三按钮语义统一、候选选择 UI、决策路径已入库分支、默认折叠

## 替代方案

- **多个细分接口**（/dimensions、/rename、/scrape-candidate 三个预览接口）：语义更清晰但前端需分别调用，增加复杂度。选择单一 `/preview` 接口。
- **前端比对判定 override**：不落库字段，前端自己比对。但刷新后可能丢失，选择后端落库。
