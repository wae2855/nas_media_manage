# API 服务

> 对应源码路径：`media_importer/api/`

## 概述

API 服务模块是 影音库AI智能整理的 HTTP 接口层，基于 Python 标准库 `http.server` 构建，提供 RESTful 风格的 JSON API 和 Web UI 静态文件服务。模块采用 Mixin 组合模式将不同功能域的处理器解耦，通过 `ThreadingHTTPServer` 支持并发请求处理。

核心职责：

- 任务全生命周期管理（创建、查询、确认、重试、忽略、删除、重命名）
- 配置的读取、保存、校验、热重载
- 元数据刮削预览与 Provider 管理
- 维度配置的 CRUD 操作
- 提示词的加载、保存与重置
- 队列的暂停/恢复/批量重试
- 文件监控状态查询与控制
- 健康检查与指标采集
- Web UI 静态文件服务

## API 架构（Mixin 模式）

### 类继承结构

```
APIHandler
├── StaticServerMixin            → 静态文件服务
├── TaskHandlersMixin            → 任务相关端点
├── ConfigHandlersMixin          → 配置相关端点
├── DimensionHandlersMixin       → 维度相关端点
├── PromptHandlersMixin          → 提示词相关端点
├── ProviderHandlersMixin        → Provider 相关端点
├── SourceCleanerHandlers        → 源目录清理器端点
├── RecycleHandlers              → 回收站端点（浏览/恢复/永久删除）
└── BaseHTTPRequestHandler       → Python 标准库基类
```

### 全局状态管理

所有共享状态集中在 `api/globals.py` 中，避免循环导入：

| 全局变量 | 类型 | 说明 |
|----------|------|------|
| `_config` | dict | 当前运行时配置 |
| `_global_pipeline` | PipelineRunner | 流水线执行器 |
| `_global_task_manager` | TaskManager | 任务管理器 |
| `_global_metrics` | Metrics | 指标收集器 |
| `_global_logger` | Logger | 日志记录器 |
| `_global_notifier` | HermesNotifier | 通知发送器 |
| `_global_watcher` | FileWatcher | 文件监控器 |
| `_config_dirty` | bool | 配置脏标记（有待同步的配置变更） |

### 请求分发

`APIHandler` 重写 `do_GET`、`do_POST`、`do_PUT`、`do_DELETE` 四个方法，通过 URL 路径匹配将请求分发到对应 Mixin 方法。所有 `/api/` 路径（除 `/api/health`）均需通过认证检查。

### 服务启动

`start_server(host, port, config)` 函数完成以下初始化：

1. 初始化全局状态（TaskManager、Metrics、Logger、Notifier、Pipeline）
2. 清理孤立状态（重置崩溃任务、清理临时文件）
3. 启动文件监控（如果配置启用）
4. 扫描源目录中已有文件并启动初始批量处理
5. 启动 `ThreadingHTTPServer` 进入请求循环

### 孤立状态清理

服务启动时执行 `_cleanup_orphaned_state`，处理上次异常退出遗留的状态：

- 将 `PROCESSING` 状态的任务重置为 `PENDING`，清理中转目录中的临时文件
- 保留 `CONFIRMING` 状态任务的临时文件（等待用户确认）
- 清理中转目录中不属于任何活跃任务的孤立文件

## 路由表

### GET 端点

| 路径 | 处理方法 | 所属 Mixin | 说明 |
|------|----------|------------|------|
| `/` | `_serve_static_file("index.html")` | StaticServer | Web UI 首页 |
| `/css/*` | `_serve_static_file(path)` | StaticServer | CSS 样式文件 |
| `/js/*` | `_serve_static_file(path)` | StaticServer | JavaScript 文件 |
| `/api/health` | `_health` | ConfigHandlers | 健康检查（免认证） |
| `/api/metrics` | `_metrics` | ConfigHandlers | 指标统计 |
| `/api/config` | `_config` | ConfigHandlers | 获取当前配置（脱敏） |
| `/api/config/validate` | `_config_validate` | ConfigHandlers | 配置完整性验证 |
| `/api/config/prompts` | `_load_prompts_for_ui` | PromptHandlers | 获取提示词内容 |
| `/api/config/prompts/reset` | `_config_reset_prompts` | PromptHandlers | 重置提示词为默认 |
| `/api/watcher/status` | `_watcher_status` | ConfigHandlers | 文件监控状态 |
| `/api/tasks` | `_list_tasks` | TaskHandlers | 任务列表（分页+筛选） |
| `/api/tasks/stats` | `_task_stats` | TaskHandlers | 任务统计 |
| `/api/tasks/{id}` | `_get_task` | TaskHandlers | 任务详情 |
| `/api/tasks/{id}/subtitles` | `_task_subtitles` | TaskHandlers | 任务字幕列表 |
| `/api/queue/status` | `_queue_status` | TaskHandlers | 队列状态 |
| `/api/logs` | `_logs` | ConfigHandlers | 获取日志 |
| `/api/skill` | `_skill` | PromptHandlers | 获取 Hermes SKILL.md |
| `/api/skills` | `_skills_list` | PromptHandlers | 获取技能列表 |
| `/api/dimensions` | `_dimensions_list` | DimensionHandlers | 维度列表 |
| `/api/dimensions/enabled` | `_dimensions_enabled` | DimensionHandlers | 已启用维度 |
| `/api/dimensions/{name}` | `_dimension_get` | DimensionHandlers | 维度详情 |
| `/api/providers` | `_providers_list` | ProviderHandlers | Provider 列表 |
| `/api/providers/{type}/genres` | `_provider_genres_list` | ProviderHandlers | Provider 类型列表 |
| `/api/providers/{type}/prompts` | `_provider_prompts_get` | ProviderHandlers | Provider 提示词 |
| `/api/source-cleaner/preview` | `source_cleaner_preview` | SourceCleanerHandlers | 清理器预览（规则+AI分析结果） |
| `/api/source-cleaner/records` | `source_cleaner_records` | SourceCleanerHandlers | 清理器执行记录 |
| `/api/source-cleaner/status` | `source_cleaner_status` | SourceCleanerHandlers | 清理器状态查询 |
| `/api/source-cleaner/ai-preview` | `source_cleaner_ai_preview` | SourceCleanerHandlers | AI 独立分析预览 |
| `/api/recycle/list` | `recycle_list` | RecycleHandlers | 回收站文件列表（分页+筛选） |

### POST 端点

| 路径 | 处理方法 | 所属 Mixin | 说明 |
|------|----------|------------|------|
| `/api/run` | `_run_batch` | TaskHandlers | 触发批量处理 |
| `/api/run/file` | `_run_file` | TaskHandlers | 处理指定文件 |
| `/api/restart` | `_restart_service` | TaskHandlers | 重启服务 |
| `/api/watcher/control` | `_watcher_control` | ConfigHandlers | 监控控制（pause/resume/status） |
| `/api/tasks/clear` | `_clear_tasks` | TaskHandlers | 清空任务 |
| `/api/tasks/confirm-all` | `_task_confirm_all` | TaskHandlers | 批量确认 |
| `/api/tasks/{id}/retry` | `_retry_task` | TaskHandlers | 重试任务 |
| `/api/tasks/{id}/confirm` | `_task_confirm` | TaskHandlers | 确认入库 |
| `/api/tasks/{id}/reclassify` | `_task_reclassify` | TaskHandlers | 重新分类 |
| `/api/tasks/{id}/ignore` | `_task_ignore` | TaskHandlers | 忽略任务 |
| `/api/tasks/{id}/rename` | `_task_rename` | TaskHandlers | 重命名文件 |
| `/api/tasks/{id}/delete` | `_delete_task` | TaskHandlers | 删除任务（可选删除文件） |
| `/api/queue/pause` | `_queue_pause` | TaskHandlers | 暂停队列 |
| `/api/queue/resume` | `_queue_resume` | TaskHandlers | 恢复队列 |
| `/api/queue/retry-all` | `_queue_retry_all` | TaskHandlers | 重试所有失败任务 |
| `/api/config` | `_config_save` | ConfigHandlers | 保存配置 |
| `/api/config/reload` | `_config_reload` | ConfigHandlers | 重载配置 |
| `/api/config/test-llm` | `_config_test_llm` | ConfigHandlers | 测试 LLM 连通性 |
| `/api/config/test-hermes` | `_config_test_hermes` | ConfigHandlers | 测试 Hermes 通知 |
| `/api/config/check-permission` | `_config_check_permission` | ConfigHandlers | 检查路径权限 |
| `/api/config/section` | `_config_save_section` | ConfigHandlers | 保存配置区块 |
| `/api/config/prompts` | `_config_save_prompts` | PromptHandlers | 保存提示词 |
| `/api/config/prompts/reset` | `_config_reset_prompts` | PromptHandlers | 重置提示词 |
| `/api/scrape/preview` | `_scrape_preview` | ConfigHandlers | 刮削预览 |
| `/api/path/test` | `_path_test` | ConfigHandlers | 测试单个路径权限 |
| `/api/providers/{type}/test` | `_provider_test` | ProviderHandlers | 测试 Provider 连通性 |
| `/api/providers/{type}/preview` | `_provider_preview` | ProviderHandlers | Provider 元数据预览 |
| `/api/providers/{type}/search` | `_provider_search` | ProviderHandlers | Provider 搜索 |
| `/api/providers/{type}/details` | `_provider_details` | ProviderHandlers | Provider 详情 |
| `/api/providers/{type}/prompts` | `_provider_prompts_save` | ProviderHandlers | 保存 Provider 提示词 |
| `/api/providers/{type}/prompts/reset` | `_provider_prompts_reset` | ProviderHandlers | 重置 Provider 提示词 |
| `/api/dimensions/{name}/enable` | `_dimension_enable` | DimensionHandlers | 启用维度 |
| `/api/dimensions/{name}/disable` | `_dimension_disable` | DimensionHandlers | 禁用维度 |
| `/api/dimensions/{name}/reset` | `_dimension_reset` | DimensionHandlers | 重置维度 |
| `/api/source-cleaner/execute` | `source_cleaner_execute` | SourceCleanerHandlers | 执行源目录清理 |
| `/api/recycle/restore` | `recycle_restore` | RecycleHandlers | 恢复回收站文件到原位置 |
| `/api/recycle/delete` | `recycle_delete` | RecycleHandlers | 永久删除回收站文件 |

### PUT 端点

| 路径 | 处理方法 | 所属 Mixin | 说明 |
|------|----------|------------|------|
| `/api/dimensions/{name}` | `_dimension_update` | DimensionHandlers | 更新维度配置 |

### DELETE 端点

| 路径 | 处理方法 | 所属 Mixin | 说明 |
|------|----------|------------|------|
| `/api/tasks/{id}` | `_delete_task` | TaskHandlers | 删除任务（仅 DB 记录） |

## 请求/响应格式

### 统一 JSON 响应

所有 API 端点返回统一的 JSON 结构：

```json
{
  "code": 200,
  "status": "success",
  "message": "操作描述",
  "data": {}
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | int | HTTP 状态码 |
| `status` | string | 状态标识：success / created / bad_request / not_found / internal_error / unauthorized |
| `message` | string | 人类可读的操作结果描述 |
| `data` | object/null | 业务数据载荷 |

### 常见状态码

| 状态码 | 含义 | 典型场景 |
|--------|------|----------|
| 200 | 成功 | 查询、更新操作 |
| 202 | 已接受 | 异步操作（批量处理、单文件处理） |
| 400 | 请求错误 | 参数缺失、状态不允许操作 |
| 401 | 未认证 | API Key 缺失或错误 |
| 403 | 禁止访问 | 许可不足（如维度启用需要高级许可） |
| 404 | 未找到 | 资源不存在 |
| 500 | 服务器错误 | 内部异常 |
| 503 | 服务不可用 | 外部 API 调用失败 |

### 请求体格式

POST/PUT 请求使用 JSON 格式，通过 `read_json_body` 解析。常见请求体示例：

**保存配置**：`POST /api/config`
```json
{
  "source_dir": "/vol1/video/source",
  "temp_dir": "/vol1/video/temp",
  "llm": { "api_key": "***", "base_url": "https://api.example.com" }
}
```

**保存配置区块**：`POST /api/config/section`
```json
{
  "section": "llm",
  "data": { "llm": { "provider": "openai", "model": "gpt-4" } }
}

支持的 section 值：basic, path_rules, import_options, metadata.providers, llm, server, hermes, file_watcher, advanced, confidence
```

**重新分类**：`POST /api/tasks/{id}/reclassify`
```json
{
  "dimensions": { "type": "movie", "genre": "科幻" }
}
```

**删除任务（含文件）**：`POST /api/tasks/{id}/delete`
```json
{
  "delete_files": true
}
```

### 任务列表查询参数

`GET /api/tasks` 支持以下查询参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码 |
| `limit` / `page_size` | int | 20 | 每页数量 |
| `offset` | int | 0 | 偏移量（与 page 二选一） |
| `status` | string | 全部 | 状态筛选（PENDING/PROCESSING/SUCCESS/FAILED/SKIPPED/CONFIRMING/NEEDS_REVIEW/ROLLBACK/DUPLICATE_REVIEW/ALL） |
| `format` | string | json | 输出格式（json/text） |

### 敏感字段处理

配置接口对敏感字段实施脱敏和过滤策略：

- 读取配置时，`mask_sensitive` 将 `api_key`、`secret` 等字段替换为 `***`
- 保存配置时，值为 `***` 的字段不会覆盖原始值（`_update_config_safely` 跳过脱敏值）
- `_filter_sensitive_fields` 在写入 YAML 前移除脱敏字段，避免将 `***` 写入配置文件
- `_get_real_config_value` 从内存配置或磁盘文件中读取真实值，用于连通性测试

### YAML 保存策略

配置保存使用 `ruamel.yaml` 保持原始格式：

- 保留注释和引号风格
- 自动为 YAML 保留字（true/false/yes/no/null 等）和含特殊字符的值添加引号
- 嵌套更新采用 `update_nested` 递归合并，不破坏未修改的配置结构

## 认证机制

### API Key 认证

系统采用 Bearer Token 认证方式：

1. 在配置文件 `server.api_key` 中设置 API Key
2. 客户端在请求头中携带 `Authorization: Bearer <api_key>`
3. 所有 `/api/` 路径的请求（除 `/api/health`）均需认证
4. 若 `server.api_key` 为空，则跳过认证

### 认证流程

```
请求到达 → 检查路径是否为 /api/health → 是 → 跳过认证
                                        → 否 → 检查 api_key 是否配置
                                                → 未配置 → 放行
                                                → 已配置 → 校验 Authorization 头
                                                          → 通过 → 继续处理
                                                          → 失败 → 返回 401
```

### 认证失败响应

```json
{
  "code": 401,
  "status": "unauthorized",
  "message": "认证失败：请提供有效的 API Key",
  "data": null
}
```

## 静态文件服务

### 文件定位

静态文件目录为 `media_importer/webui/`，包含 Web UI 的 HTML、CSS、JavaScript 文件。

### 路由规则

| 请求路径 | 映射文件 | 说明 |
|----------|----------|------|
| `/` | `webui/index.html` | 主页面 |
| `/css/*` | `webui/css/*` | 样式文件 |
| `/js/*` | `webui/js/*` | 脚本文件 |
| 其他路径 | `webui/<path>` | 兜底静态文件 |

### 安全措施

- **路径遍历防护**：通过 `os.path.realpath` 解析真实路径，校验是否在 `WEBUI_DIR` 内，防止 `../` 穿越
- **Content-Type 推断**：根据文件扩展名设置正确的 MIME 类型（html/css/js/png/svg）
- **缓存控制**：设置 `Cache-Control: no-cache`，确保前端更新后用户立即获取最新版本
- **iframe 嵌入**：设置 `X-Frame-Options: ALLOWALL` 和 `Content-Security-Policy: frame-ancestors *`，允许在 fnOS 管理界面中嵌入

### 支持的 MIME 类型

| 扩展名 | Content-Type |
|--------|-------------|
| `.html` | text/html; charset=utf-8 |
| `.css` | text/css; charset=utf-8 |
| `.js` | application/javascript; charset=utf-8 |
| `.png` | image/png; charset=utf-8 |
| `.svg` | image/svg+xml; charset=utf-8 |

## 职责边界

### 负责

- HTTP 请求路由分发
- 请求认证（Bearer Token）
- 统一 JSON 响应格式化
- 配置读写与校验触发
- 任务操作入口（确认/重试/忽略/删除/重命名）
- 静态文件服务（WebUI）
- 全局状态管理（globals.py）

### 不负责

- 业务逻辑执行（委托 pipeline / TaskManager / scraper）
- 数据持久化（委托 task_repo / dimension_repo）
- 文件 I/O（委托 storage 模块）
- 通知发送（委托 notify 模块）

## 与其他模块的交互

### 交互关系总览

| 交互模块 | 交互方式 | 说明 |
|----------|----------|------|
| `core/task_manager` | 直接调用 | 任务 CRUD、状态流转、批量操作 |
| `core/db` | 直接调用 | 底层数据库操作（任务查询、字幕查询、维度 CRUD） |
| `core/config_loader` | 导入调用 | 配置加载、迁移、脱敏 |
| `core/config_validator` | 导入调用 | 配置完整性验证、LLM/Hermes 连通性测试 |
| `core/metrics` | 导入调用 | 指标采集与序列化 |
| `core/safety` | 导入调用 | 路径安全校验、写入权限检查 |
| `core/logger` | 导入调用 | 日志获取 |
| `pipeline` | 全局实例 | 流水线执行（run_all、process_one、confirm_task、reclassify_task） |
| `scraper/llm_scraper` | 按需实例化 | 刮削预览、提示词默认值获取 |
| `scraper/metadata_scraper` | 按需实例化 | Provider+AI 联合刮削预览 |
| `scraper/providers` | 按需实例化 | Provider 工厂方法、实例创建 |
| `scraper/dimension_manager` | 导入调用 | 维度许可层级检查 |
| `scraper/tmdb_client` | 按需实例化 | TMDB API 搜索/详情/类型列表 |
| `notify/hermes_hook` | 全局实例 | 通知发送 |
| `monitor/file_watcher` | 全局实例 | 文件监控启停 |
| `monitor/permission_checker` | 导入调用 | 路径权限检查 |
| `storage/source_cleaner` | 按需实例化 | 清理器预览、执行、AI分析 |
| `core/safety` (recycle) | 导入调用 | 回收站浏览/恢复/永久删除 |

### 配置热重载流程

```
用户保存配置 → _config_save
  ├─ 有运行中任务 → 设置 _config_dirty=True → 写入文件 → 等待任务完成后自动同步
  └─ 无运行中任务 → 写入文件 → 立即更新内存配置 → 按需重启文件监控
```

### 清理器执行流程

`POST /api/source-cleaner/execute` 执行源目录清理：

1. 检查 `recycle_dir` 写权限（`check_path_permission`）
2. 实例化 `SourceCleaner(config)`
3. 获取所有任务关联文件路径（排除已关联文件）
4. 解析请求体中的 `confirmed` 和 `merge_strategy` 参数
5. 调用 `cleaner.execute(task_paths, confirmed, merge_strategy)`
6. 如需确认（`confirm_before_cleanup=true` 且 `confirmed=false`），返回待确认列表
7. 执行清理，将文件移入回收站 `[清理器-源目录]` 分区
8. 保存清理记录到 `cleaner_records` 表

### 回收站操作流程

**浏览** `GET /api/recycle/list`：
1. 调用 `list_recycle_dir(recycle_dir, zone, reason, limit, offset)`
2. 扫描回收站目录，解析 `.meta`/`.dir.meta` 文件
3. 返回文件列表 + 分区统计 + 总大小

**恢复** `POST /api/recycle/restore`：
1. 读取请求体中的 `items` 和 `conflict_mode`
2. 调用 `restore_from_recycle(items, conflict_mode)`
3. 读取 `.meta` 获取原位置，移回文件/目录
4. 冲突处理：skip（跳过）/ overwrite（覆盖）/ rename（重命名加 `_restored` 后缀）

**永久删除** `POST /api/recycle/delete`：
1. 读取请求体中的 `items`
2. 调用 `delete_from_recycle(items)`
3. 直接删除文件/目录及对应 `.meta`/`.dir.meta`

### 刮削预览流程

`POST /api/scrape/preview` 使用 `ThreadPoolExecutor` 并行执行两种刮削：

1. **纯 AI 刮削**：直接调用 `LLMScraper.scrape`
2. **Provider+AI 刮削**：调用 `MetadataScraper.scrape`（先查 Provider API，再用 AI 整理）

两者并行执行，超时时间 60 秒，结果合并返回供前端对比展示。

### 任务忽略流程

`_task_ignore` 根据任务当前文件位置执行不同逻辑：

| 文件位置 | 处理方式 |
|----------|----------|
| `temp` + 有回收站 | 移动临时文件到回收站，更新 DB 状态为 SKIPPED |
| `temp` + 无回收站 | 删除临时文件，状态设为 SKIPPED |
| `source`/`recycle` + 有回收站 | 调用 `move_to_recycle_bin`，状态设为 SKIPPED |
| `source`/`recycle` + 无回收站 | 仅更新状态为 SKIPPED |

### 服务重启机制

`_restart_service` 根据运行环境选择重启方式：

| 环境 | 重启方式 |
|------|----------|
| fnOS（`TRIM_PKGVAR` 环境变量存在） | 调用 `cmd/main stop` + `cmd/main start` |
| 其他环境 | `os.execv` 替换当前进程 |
