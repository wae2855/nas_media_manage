# API Architecture

## Current Pattern

- 原生 `BaseHTTPRequestHandler`。
- `api/routes.py` 负责 API route table。
- `api/handler.py` 负责请求解析、鉴权、路由调用、静态文件 fallback 和 server 启动。
- 业务 handler 按 Mixin 拆分在 `api/*_handlers.py`。
- JSON 响应格式统一为 `{code, status, message, data}`。

## Entry Points

- `media_importer/api/handler.py`
- `media_importer/api/routes.py`
- `media_importer/api/utils.py`
- `media_importer/api/task_handlers.py`
- `media_importer/api/config_handlers.py`
- `media_importer/api/provider_handlers.py`
- `media_importer/api/recycle_handlers.py`
- `media_importer/api/source_cleaner_handlers.py`

## Feature Ownership

| API area | Handler | Feature owner |
|----------|---------|---------------|
| Tasks, retry, queue, confirm, reclassify | `task_handlers.py` | `features/tasks`, `features/import_flow` |
| Config load/save/validate/check | `config_handlers.py`, `connectivity_handlers.py` | `features/configuration` |
| Provider list/test/search/details/prompts | `provider_handlers.py`, `tmdb_handlers.py` | `features/providers`, `features/scraping`, `features/prompts` |
| Prompt defaults and reset | `prompt_handlers.py` | `features/prompts` |
| Source cleaner preview/execute/records | `source_cleaner_handlers.py` | `features/source_cleaning` |
| Recycle list/restore/delete/cleanup | `recycle_handlers.py` | `features/recycle` |
| Dimensions | `dimension_handlers.py` | scraping/classification configuration; target feature doc to be added when dimensions are migrated |

API handlers should parse requests, call feature services/public APIs, and return HTTP responses. Complex business rules should move into feature modules.

Phase 4 dependency inventory is tracked in [api-dependency-audit.md](api-dependency-audit.md).

## Route Table

新增 API 端点优先注册到 `media_importer/api/routes.py`：

- `method`: HTTP method。
- `pattern`: 支持 `/api/tasks/{task_id}` 风格路径参数。
- `handler_name`: `APIHandler` 或 Mixin 上的方法名。
- `pass_query` / `pass_body`: 是否传入 query/body。
- `body_before_params`: 兼容 provider handler 的旧签名。
- `pass_self`: 兼容 source cleaner/recycle handler 的旧签名。

`handler.py` 不再扩展长 `if/elif` API 分支；未匹配 API 返回 404，非 API GET 继续走静态文件 fallback。

## Task API Details

### GET /api/tasks

任务列表查询，支持 status + stage 双参数过滤。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `status` | string | null | 过滤任务终态：PENDING / SUCCESS / FAILED / SKIPPED / CANCELLED |
| `stage` | string | null | 过滤处理环节（仅 status=PENDING 时有意义）：QUEUED / RUNNING / AWAIT_REVIEW / DONE |
| `limit` | int | 20 | 每页条数 |
| `offset` | int | 0 | 偏移量 |
| `page` | int | null | 页码（优先于 offset） |
| `format` | string | json | 输出格式：json / text |

前端筛选映射：

| 前端 Chip | status | stage |
|-----------|--------|-------|
| 全部 | - | - |
| 排队中 | PENDING | QUEUED |
| 处理中 | PENDING | RUNNING |
| 待确认 | PENDING | AWAIT_REVIEW |
| 失败 | FAILED | - |
| 已完成 | SUCCESS + SKIPPED | - |
| 已取消 | CANCELLED | - |

注意：`SUCCESS + SKIPPED` 由前端分别请求后合并，后端单次查询只支持单个 status 值。

### POST /api/tasks/{task_id}/cancel

取消排队中的任务，保留任务记录，不移动源文件。

允许状态：

```text
PENDING/QUEUED
```

成功响应：

```json
{
  "code": 200,
  "message": "任务已取消",
  "data": {
    "task": {
      "status": "CANCELLED",
      "stage": "DONE",
      "error_message": "用户取消"
    }
  }
}
```

非排队任务返回 400，例如运行中任务返回 `当前状态不可取消: PENDING/RUNNING`。

### 任务详情弹窗编辑矩阵

任务卡片按钮矩阵与详情弹窗字段编辑权限，依据 `status + stage` 决定：

| status | stage | 主按钮 | 次按钮 | 详情（幽灵） | 文件名可编辑 | 维度可编辑 |
|--------|-------|--------|--------|--------------|--------------|------------|
| PENDING | AWAIT_REVIEW | 去确认 | — | 详情 | 是 | 是 |
| PENDING | QUEUED | 取消 | — | 详情 | 否 | 否 |
| PENDING | RUNNING | — | — | 详情 | 否 | 否 |
| SUCCESS | DONE | — | — | 详情 | 否 | 否 |
| FAILED | DONE | 去重试 | 移入回收 | 详情 | 否 | 否 |
| SKIPPED | DONE | 去重试 | — | 详情 | 否 | 否 |
| CANCELLED | DONE | 重新投入 | — | 详情 | 否 | 否 |

规则：

- “详情”幽灵按钮是唯一打开详情弹窗的入口。
- 弹窗内文件名 / 分类维度是否可编辑由 `isAwaitReview` 决定，仅 `PENDING/AWAIT_REVIEW` 允许编辑。
- 文件名区域：修改 / 保存 按钮组；维度区域：修改 / 保存 + 预览入库规则 按钮组。
- 弹窗底部只保留“关闭”按钮，文件名保存和维度保存分别放在各自区域。

### POST /api/tasks/{task_id}/classify-preview

入库预览，返回分类结果但不执行文件操作。

请求体：

```json
{
  "dimensions": {"media_type": "tv", "season": "1"},
  "filename": "Inception.2010.mkv"
}
```

响应体：

```json
{
  "import_path": "/vol1/影视/电视剧/盗梦空间/Season 1/",
  "final_filename": "Inception.2010.mkv",
  "full_path": "/vol1/影视/电视剧/盗梦空间/Season 1/Inception.2010.mkv",
  "matched_rule": null,
  "warnings": []
}
```

## Standards

见 [../standards/api.md](../standards/api.md)。
