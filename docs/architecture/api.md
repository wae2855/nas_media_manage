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
| Dashboard business summary | `task_handlers.py` | `features/tasks`, `features/scraping` |
| Tasks, retry, queue, confirm, reclassify, preview, scrape-search, series batch apply | `task_handlers.py` | `features/tasks`, `features/import_flow` |
| Config load/save/validate/check | `config_handlers.py`, `connectivity_handlers.py` | `features/configuration` |
| Provider list/test/search/details/prompts | `provider_handlers.py`, `tmdb_handlers.py` | `features/providers`, `features/scraping`, `features/prompts` |
| Prompt defaults and reset | `prompt_handlers.py` | `features/prompts` |
| Source cleaner preview/execute/records | `source_cleaner_handlers.py` | `features/source_cleaning` |
| Recycle list/restore/delete/cleanup | `recycle_handlers.py` | `features/recycle` |
| Dimensions | `dimension_handlers.py` | scraping/classification configuration; target feature doc to be added when dimensions are migrated |

API handlers should parse requests, call feature services/public APIs, and return HTTP responses. Complex business rules should move into feature modules.

### GET /api/health

公开健康检查返回服务状态、目录探针、时间戳和 `version`。`version` 必须由包内 `server/VERSION` 读取，并与根 `VERSION`、FPK manifest 保持一致；前端只展示服务端返回值，不得写死版本号。

### GET /api/config/startup-readiness

正式运行前的只读聚合检查，用户界面名称为“配置检查”。handler 只调用 `features.configuration.inspect_startup_readiness`；返回配置 revision、总状态 `PASS|BLOCKED`，以及目录/磁盘、规则与目标片库、TMDB、按需 LLM、自动运行分项。规则分项同时检查显式 root ID 和被引用目标的目录能力；自动运行分项同时读取目录的 `automatic_allowed` 和当前服务内 watcher 的真实运行状态。分项状态为 `PASS|WARN|BLOCKED|SKIPPED`，前端不得自行推断 READY。

### Provider 维度映射

- `GET /api/providers/{type}/dimension-capabilities`：Provider 可提供的标准字段与有界数据形态。
- `GET /api/dimensions/{name}/mappings/{provider}`：当前映射、值域、摘要和内容哈希。
- `PUT /api/dimensions/{name}/mappings/{provider}`：带 `expected_hash` 保存经验证的 schema v2 映射；目标值不存在或哈希过期时失败关闭。
- `POST /api/dimensions/{name}/mappings/{provider}/preview`：对请求内的未保存映射执行本地试算，返回目标值和映射证据。

映射编辑不经过通用维度 PUT，不允许任意 Python/JavaScript/正则执行。试算不保存 DB，也不触发文件操作。

### GET /api/watcher/status

返回后台自动整理的配置意图与运行事实：`configured_enabled` 表示用户是否设置开启，`enabled` 表示 watcher 线程是否实际存活，`automatic_allowed` 表示当前目录能力是否允许自动化，`status` 为 `disabled|blocked|not_started|running`。`reason` 和 `blocking_reasons[]` 提供可直接展示的中文原因，禁止前端用“全部绿色”等笼统文案覆盖服务端事实。

### GET /api/config/fnos-folders

返回 fnOS 目录授权能力：`enforced` 表示当前运行时必须使用系统 ACL，`available` 表示本次查询成功，`folders` 是当前应用已授权根目录。`GET /api/config` 同步返回同一份 `directory_authorization`，并把来源、片库和回收的 containment 结果纳入 `readiness.locations[].authorization`。token 永不进入响应。

服务端通过 Unix socket 调用 `trim.file.getSharedAccessibleFolders`；`TRIM_API_TOKEN` 仅从当前进程环境读取，响应永不包含 token。非 fnOS 环境返回 HTTP 200 + `enforced=false, available=false`，前端明确降级为开发手填；已检测到 fnOS 宿主但查询失败时返回 `enforced=true, available=false`，保存和运行失败关闭。

Phase 4 dependency inventory is tracked in [api-dependency-audit.md](api-dependency-audit.md).

### GET /api/dashboard/summary

首页只读业务摘要。handler 调用 `features.tasks.get_dashboard_summary_for_api`，返回：

- `queued`、`running`、`await_review`、`failed`：按任务 `status + stage` 聚合的当前数量；
- `running_progress`：真实运行任务进度的平均值，仅 `running > 0` 时供前端展示；
- `today_success`：服务器本地自然日内成功完成入库的任务数；
- `activities`：最近最多 5 条面向用户的任务事件，不返回原始技术日志；
- `recent_movies`：按成功完成时间倒序、作品去重后的最近最多 12 部影片；
- `thumbnail_cache`：可再生成 Thumbnail 缓存的数量、容量和本次治理结果。

缩略图只允许来自应用 Thumbnail 根目录的普通图片文件；响应使用 `/api/thumbnails/{file}`，不得泄露服务器绝对路径。队列暂停状态由现有 queue service 提供。

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

列表每条任务同时返回实时进度合同：

- `current_step`、`total_steps`：兼容流程位置；
- `step_name`：内部真实阶段，如 `copy_transfer`、`copy_verify_target`、`import_transfer`、`source_cleanup_transfer`；
- `percentage`：整体流程的单调位置，不代表剩余时间；
- `bytes_copied`、`total_bytes`：只在当前字节阶段用于计算阶段百分比；
- `source_cleanup_status`：来源策略结果或等待/阻断状态。

前端不得对刮削、分类、发布等非字节阶段显示伪造百分比，也不得从 `percentage` 推算 ETA。

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
| SUCCESS | DONE | 待整理结果显示“重新整理”；其他无 | — | 详情 | 否 | 否 |
| FAILED | DONE | 去重试 | 移入回收 | 详情 | 否 | 否 |
| SKIPPED | DONE | 去重试 | — | 详情 | 否 | 否 |
| CANCELLED | DONE | 重新投入 | — | 详情 | 否 | 否 |

规则：

- “详情”幽灵按钮是唯一打开详情弹窗的入口。
- 弹窗内文件名 / 分类维度是否可编辑由 `isAwaitReview` 决定，仅 `PENDING/AWAIT_REVIEW` 允许编辑。
- 待确认详情底部提供“保存”；只有当前预览满足确认门禁时才显示“确认入库”或“确认重新整理”。
- `SUCCESS/DONE + FALLBACK_PENDING` 详情保持只读，只提供“创建重新整理任务”；新任务独立记录，不重新打开原任务。
- 重新整理仍命中兜底时只能继续改维度或手动刮削；命中正式规则后才允许确认，视频和随片字幕按 no-replace 文件包移动。

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

### POST /api/tasks/{task_id}/preview

预览元数据/维度/文件名变更，更新 DB + 重跑分类规则，返回更新后的完整 task，**不执行文件操作**。任务保持 `stage=AWAIT_REVIEW`。

请求体（任一子集）：

```json
{
  "dimensions": {"media_type": "movie", "genre": "科幻"},
  "title_cn": "阿凡达",
  "title_en": "Avatar",
  "year": "2009",
  "filename": "阿凡达.2009.mkv"
}
```

响应体：

```json
{
  "code": 200,
  "data": {
    "task": {
      "task_id": "abc123",
      "import_path": "/movies/科幻/",
      "final_filename": "阿凡达.2009.mkv",
      "stage": "AWAIT_REVIEW",
      "...": "..."
    }
  }
}
```

### POST /api/tasks/{task_id}/scrape-search

在确认界面内嵌重刮能力。接收查询词、作品类型、结果语言、年份和数量，返回 Provider 多候选列表；`limit` 默认 20、最大 20。

请求体：

```json
{
  "query": "阿凡达",
  "year": 2009,
  "media_type": "movie",
  "language": "zh-CN",
  "limit": 20
}
```

响应体：

```json
{
  "code": 200,
  "data": {
    "candidates": [
      {
        "id": "19995",
        "title": "阿凡达",
        "original_title": "Avatar",
        "year": "2009",
        "media_type": "movie",
        "overview": "战斗中负伤而下身瘫痪的前海军战士杰克·萨利...",
        "provider_type": "tmdb",
        "poster_url": "https://...",
        "vote_average": 7.5
      }
    ],
    "query": "阿凡达",
    "media_type": "movie",
    "language": "zh-CN",
    "limit": 20
  }
}
```

### POST /api/tasks/{task_id}/scrape-apply

把用户选中的 Provider ID 应用到等待确认任务。服务端按 ID 获取完整详情、重新映射维度、分类、命名和冲突预览，任务继续保持 `PENDING/AWAIT_REVIEW`；本端点不复制、不入库，也不自动调用 `confirm`。

电视剧请求可附带 `related_task_ids`。服务端以当前任务重新计算安全同批次集合，只处理仍处于待确认、同一实际父目录、同标准化剧名且季集号唯一的任务。Provider 详情每次请求只加载一次，每个任务分别保留自己的季集号并重算派生结果。响应增加 `updated`、`skipped`、`failed`；部分失败必须如实返回。

请求体：

```json
{
  "provider_type": "tmdb",
  "item_id": "19995",
  "media_type": "movie",
  "language": "zh-CN",
  "related_task_ids": []
}
```

响应返回更新后的完整 `task`。任务状态在 Provider 网络请求期间发生变化时，CAS 会拒绝应用并要求刷新。

### POST /api/tasks/{task_id}/scrape-series-preview

在应用电视剧候选前返回可勾选的同剧同批次任务。请求包含 `provider_type`、`item_id`、`media_type=tv`。响应 `tasks` 含锚点任务以及安全关联任务的 `task_id/source_filename/season/episode/is_anchor`，`excluded` 仅用于诊断规则排除。电影候选返回空集合。本接口只读，不加载 Provider 详情，不更新任务。

### POST /api/tasks/{task_id}/confirm

确认入库。普通人工核对继续使用可选参数 `confirmed_title` 和 `override_source`。当任务含未决目标片库冲突时，必须额外提交 `conflict_action`，且只能逐项调用。分类落入兜底目录时必须显式提交 `fallback_acknowledged=true`，否则返回 400；重新整理任务仍落入兜底时固定拒绝确认。

请求体：

```json
{
  "confirmed_title": "阿凡达",
  "override_source": "manual",
  "conflict_action": "keep_both",
  "source_disposition": "keep",
  "fallback_acknowledged": false
}
```

`conflict_action` 允许值：`keep_existing`（目标与来源保持不变，任务跳过）、`keep_both`（只新增带编号文件）、`replace_existing`（指纹重检后把旧文件移入本地回收，再发布新文件）。未提供动作的冲突确认返回 400；`confirm-all` 会排除冲突任务并返回 `conflict_skipped`。

仅当 `conflict_action=keep_existing` 时允许携带 `source_disposition=keep|local_recycle|permanent_delete`，分别表达保留、移入本地回收区和已显式启用后的永久删除本次新资源。该字段不影响目标片库现有文件。

### POST /api/tasks/{task_id}/reorganize

对已成功进入待整理区的任务创建关联重新整理任务。父任务必须为 `SUCCESS/DONE` 且 `organization_status=FALLBACK_PENDING`；已有活动子任务时返回同一任务，避免重复创建。接口不移动文件，返回的新任务为 `PENDING/AWAIT_REVIEW + task_kind=REORGANIZE`，用户仍通过维度编辑或手动刮削匹配正式规则，再调用 confirm。父任务始终只读且不重新打开。

重新整理确认只允许 no-replace 整组移动影片与随片字幕；目标同名时进入逐项冲突处理，替换按钮关闭。完成后父任务记录 `reorganized_by_task_id`，父子 `organization_status` 均为 `ORGANIZED`。

响应体：

```json
{
  "code": 200,
  "message": "确认入库成功"
}
```

### POST /api/tasks/{task_id}/delete

只删除已结束任务记录，不触发任何文件动作。活动任务返回 400 并引导先结束处理；目标片库和来源文件均不得因删除记录而变化。旧 `delete_files=true` 仅兼容转交来源处置，片库路径固定拒绝。

### POST /api/tasks/{task_id}/dispose

结束一次尚未正常完成的整理，并明确本次新资源去向。

```json
{"source_disposition": "local_recycle"}
```

- `keep`：只结束任务，来源视频和字幕保持原位。
- `local_recycle`：只把任务登记的视频和字幕移入本地回收区，可恢复。
- `permanent_delete`：仅 ADR-0019 高风险模式已启用时允许，使用隔离账本永久删除登记成员。
- 排队、待确认、失败状态同步返回 200；运行中写入协作停止请求并返回 202；视频文件包已提交返回 409 并继续安全收尾；成功任务返回 400 并提示只可删除记录。

### POST /api/tasks/{task_id}/rename

只允许重命名仍位于来源目录的任务文件。已入库任务固定返回 400；目标片库命名变化只能通过新的入库任务或明确的冲突替换协议完成。

入库后 task 新增字段：

| 字段 | 说明 |
|------|------|
| `confirmed_override` | 1=换过元数据，0=未换 |
| `confirmed_title` | 最终入库标题 |
| `override_source` | 来源：manual / candidate:tmdb:xxx / 空 |

## Standards

见 [../standards/api.md](../standards/api.md)。

批处理、单文件、重试和确认 API 虽由后台线程快速接收，但最终都进入同一 Pipeline 任务槽位；实际并发只读取 `task_queue.max_concurrent=1|2`。重复批处理请求不会创建第二个调度池，等待槽位的任务在真正取得槽位前不得提前领取为 `RUNNING`。

## Config API: AI 配置字段

### ai_assist 配置段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `base_url` | string | "" | AI 辅助模型 API 地址 |
| `model` | string | "" | AI 辅助模型 ID |
| `api_key` | string | "" | API Key（返回时脱敏为 `***`） |
| `timeout` | int | 30 | 请求超时（秒） |
| `max_retries` | int | 2 | 最大重试次数 |
| `retry_delay` | int | 3 | 重试间隔（秒） |
| `verify_ssl` | bool | true | 是否验证 SSL 证书 |
| `log_prompt` | bool | true | 是否记录提示词日志（INFO 级别输出前 200 字符摘要，DEBUG 输出完整内容） |
| `prompt_title_clean` | string | "" | 标题清洗提示词（空=使用默认） |
| `prompt_match_assist` | string | "" | 匹配辅助提示词（空=使用默认） |
| `prompt_dimension_mapping` | string | "" | 维度映射提示词（空=使用默认） |
| `prompt_source_clean` | string | "" | 源目录清理提示词（空=使用默认） |

### ai_search 配置段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | true | 是否启用 AI 联网搜索增强（已废弃，由场景策略控制） |
| `provider` | string | "" | 搜索厂商：zhipu/qwen/moonshot |
| `model` | string | "" | 搜索模型 ID |
| `search_type` | string | "" | 搜索类型（厂商相关） |
| `api_key` | string | "" | API Key（返回时脱敏为 `***`） |
| `base_url` | string | "" | 搜索模型 API 地址 |
| `prompt_dimension_supplement` | string | "" | 维度补全提示词（空=使用默认，现划归到 `ai_search` 段） |

### ai_scene_strategy 配置段

5 个场景，每个场景有 `primary`（必填）和 `fallback`（可选）两个模型选择。

| 场景 | primary 默认值 | 说明 |
|------|---------------|------|
| `dimension_supplement` | `ai_search` | 刮削缺失补充：Provider 命中但维度不全，且场景 2 失败后的兜底 |
| `dimension_mapping` | `ai_assist` | 刮削结果归类：Provider 数据映射到本地维度体系 |
| `title_clean` | `ai_assist` | 文件标题清洗：从脏文件名提取干净标题 |
| `match_assist` | `ai_search` | 影视名 AI 推测：Tier1 精确匹配失败后进入 Tier2 推测 |
| `source_clean` | `ai_assist` | 源目录清理分析：独立于刮削流程，由清理 API 触发 |

### GET /api/config/prompt-defaults

返回各场景默认提示词，供前端"恢复默认"使用。

响应体：

```json
{
  "code": 200,
  "data": {
    "prompts": {
      "prompt_title_clean": "你是一个影视标题提取助手...",
      "prompt_match_assist": "你是一个影视搜索关键词优化助手...",
      "prompt_dimension_mapping": "你是影视维度映射助手...",
      "prompt_dimension_supplement": "你是影视维度补充助手...",
      "prompt_source_clean": "你是\"影音库AI智能整理\"系统的源目录清理助手..."
    },
    "descriptions": {
      "prompt_title_clean": "文件标题清洗：从脏文件名中清洗出干净标题...",
      "prompt_match_assist": "影视名AI推测：通过文件名 + 文件夹路径 + 同级文件名...",
      "prompt_dimension_mapping": "刮削结果归类：Provider 刮削到的原始字段...",
      "prompt_dimension_supplement": "刮削缺失补充：Provider 刮削结果缺失的维度...",
      "prompt_source_clean": "源目录清理分析：由 AI 分析源目录下每个子目录的文件构成..."
    }
  }
}
```

### 新增 PUT /api/config/section

支持按 section 局部更新配置。

| section 名 | 更新内容 |
|-----------|----------|
| `ai_assist` | AI 辅助所有字段 |
| `ai_search` | AI 联网搜索所有字段 |
| `ai_prompts` | 5 个提示词字段（来自 ai_assist.prompt_* + ai_search.prompt_dimension_supplement） |
| `ai_scene_strategy` | 5 场景的 primary/fallback |

### GET /api/config/section/{section}

支持按 section 读取配置，返回对应 section 的字段 + 状态信息。

| section | 返回内容 |
|---------|---------|
| `ai_assist` | ai_assist 配置段 + 脱敏 api_key |
| `ai_search` | ai_search 配置段 + 脱敏 api_key |

## Scraping: 两级匹配与维度确认

### 匹配流程

1. **第一级**：Provider 精确匹配（标题+年份）→ AUTO_PASS
2. **第二级**：AI 建议关键词 → Provider 回搜 → 唯一精确匹配 → CONTEXT_PASS
3. **第三级**：用户确认 → NEEDS_CONFIRM

### 维度来源追踪

每个维度来源记录为以下格式之一：
- `provider:tmdb` / `provider:douban` — Provider 直接映射
- `ai_assist` — AI 辅助模型分析
- `ai_search` — AI 联网搜索补全
- `file` — 文件分析（ffprobe 等）
- `unknown` — 无法确定来源

### 任务字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `confirm_reason` | string | 需要用户确认的原因（持久化到 DB） |
| `dim_sources` | dict | 逐维度来源追踪 |
| `match_level` | string | AUTO_PASS / CONTEXT_PASS / NEEDS_CONFIRM |
| `scrape_media_type` | string | 优先使用 media_type，兼容 type |
