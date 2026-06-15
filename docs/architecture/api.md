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

## Scraping: 三级匹配与维度确认

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
