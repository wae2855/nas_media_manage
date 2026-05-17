---
title: "NAS影视自动化入库系统"
type: requirements
date: 2026-05-16
participants: [wangwei]
reviewed_by: architecture-review
review_date: 2026-05-16
next: docs/02-design.md
---

# NAS影视自动化入库系统 — 需求文档

## 问题陈述

用户希望在飞牛NAS上实现影视文件的自动化刮削和分拣入库。当前痛点：
- 网盘下载的影视文件混杂在一起，需要人工识别类型并分拣
- 每次下载后需要手动刮削文件名、整理字幕文件
- 过程繁琐，频率随机（每周数次）

**核心目标：**
- 最小化人工干预，实现"下载→刮削→入库"全自动化
- 轻量级实现，依赖最少化
- 通过Hermes实现任务管理和异常通知

## 上下文

**现有环境：**
- 飞牛NAS（FNOS系统）
- 网盘已挂载到NAS
- Hermes系统已部署（用于通知和任务查询）
- 大模型API（用于刮削，需用户配置API Key）

**约束条件：**
- 不需要刮削元数据文件（海报、nfo等），仅需文件名规范
- 轻量优先，技术方案应尽量减少依赖
- 与Hermes解耦，Hermes仅用于通知和任务触发

## 确定方案

### 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        用户交互层                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Hermes Skill │  │ Webhook通知 │  │ 配置文件 (YAML)     │ │
│  │ (查询/触发)  │  │ (飞书/微信)  │  │ (完整配置项)       │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        核心服务层                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ 文件扫描器   │  │ AI刮削引擎   │  │ 任务调度器          │ │
│  │ (轮询/监控)  │  │ (LLM API)   │  │ (队列+持久化)       │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ 分类匹配器   │  │ 文件搬运器   │  │ 日志管理器          │ │
│  │ (多维度规则) │  │ (移动+整理)  │  │ (结构化日志)       │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ 钩子系统     │  │ 通知模块     │  │ 同名检测模块        │ │
│  │ (自定义脚本) │  │ (Webhook)   │  │ (跳过/重命名)      │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        存储层                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ 源目录       │  │ 临时目录     │  │ 入库目录            │ │
│  │ (网盘挂载)   │  │ (本地处理)   │  │ (分类后的最终位置)   │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 核心流程

```
触发: 用户触发 或 文件监控发现新文件
       │
       ▼
1. [扫描] 递归扫描源目录，收集视频文件+字幕文件
       │      忽略 .tmp / .DS_Store / partial 文件
       │
       ▼
2. [复制] 将视频文件和关联字幕文件复制到临时目录
       │      使用 .copying 后缀标记正在复制的文件
       │      支持断点续传，启动时清理残留 .copying 文件
       │
       ▼
3. [刮削] 调用AI大模型API，根据文件名刮削
       │      输入: 视频文件名 + 字幕文件名 + 维度配置
       │      输出: {title_cn, title_en, year, type, dimensions, ...}
       │      失败: 重试2次 → 标记失败 → 通知Hermes
       │
       ▼
4. [校验] 校验刮削结果的完整性和合法性
       │      检查必需字段是否存在（title_en、year、type等）
       │      校验 dimensions 值是否在配置范围内
       │      校验置信度是否达标
       │
       ▼
5. [分类] 根据用户配置的分类规则 + AI返回结果
       │      逐条匹配 path_rules，找到第一个符合条件的规则
       │      使用兜底规则处理无法匹配的情况
       │
       ▼
6. [同名检测] 检查入库路径下是否存在同名文件
       │      同名定义: 年份 + (英文标题相同 或 中文标题相同)
       │      发现同名 → 标记SKIPPED → 通知Hermes
       │
       ▼
7. [命名] 应用文件名模板生成最终文件名
       │      匹配字幕文件到对应视频
       │      电影/电视剧/字幕分别应用对应模板
       │
       ▼
8. [入库] 创建入库目录 → 移动文件 → 清理临时文件
       │      电影: 移入 /入库/电影/{year}/...
       │      电视剧: 移入 /入库/电视剧/{title} ({year})/Season {N}/
       │
       ▼
9. [通知] 通过Hermes Webhook发送执行结果
       │      成功 → task_complete
       │      失败 → task_failed（含错误详情）
       │      跳过 → task_skipped（合同名文件路径）
       │
       ▼
10. [记录] 更新任务日志（JSON持久化）
```

### 完整配置文件

```yaml
# ============================================================
# NAS影视自动化入库系统 - 配置文件 (config.yaml)
# ============================================================

# ------------------------------------------------------------
# 1. 基础配置
# ------------------------------------------------------------
source_dir: "/挂载/网盘下载"          # 源目录（网盘挂载路径）
temp_dir: "/nas本地/临时目录"       # 临时处理目录（NAS本地）
log_dir: "/nas本地/日志目录"         # 日志存储目录

# 源目录扫描配置
source_dir_scan:
  recursive: true                     # 是否递归扫描子目录
  max_depth: 5                        # 最大扫描深度
  ignore_patterns:                    # 忽略的文件模式
    - "*.tmp"
    - ".DS_Store"
    - "*partial*"

# 支持的视频扩展名
video_extensions:
  - ".mkv"
  - ".mp4"
  - ".avi"
  - ".ts"
  - ".mov"
  - ".wmv"
  - ".m2ts"
  - ".flv"

# 支持的字幕扩展名
subtitle_extensions:
  - ".srt"
  - ".ass"
  - ".ssa"
  - ".vtt"
  - ".sub"

# ------------------------------------------------------------
# 2. 大模型配置
# ------------------------------------------------------------
llm:
  provider: "openai"                    # 大模型提供商（openai/claude/其他）
  api_key: "your-api-key-here"         # API密钥
  base_url: "https://api.openai.com/v1"  # API基础URL
  model: "gpt-4o"                        # 使用的模型
  timeout: 30                            # 请求超时时间（秒）
  max_retries: 2                         # 最大重试次数
  retry_delay: 3                         # 重试间隔（秒）
  fallback_model: "gpt-3.5-turbo"       # 主模型失败后的降级模型（可选）
  confidence_threshold: 0.8              # 置信度阈值，低于此值标记为需人工确认

# ------------------------------------------------------------
# 3. 分类维度配置（可扩展）
# ------------------------------------------------------------
# 定义所有可能的分类维度，AI刮削时会返回这些维度的值
# AI返回的维度值必须是这里定义的values中的一个
dimensions:
  - name: media_type            # 维度名称，作为配置和AI返回的key
    label: 影视类型              # 显示用的中文标签
    values:                      # 该维度所有可能的值
      - movie                  # 值1：电影
      - tv                     # 值2：电视剧
    ai_prompt: "请判断这是电影还是电视剧（movie/tv）"  # 提示AI的提示词片段
    ai_hint: "请仅返回movie或tv"  # 给AI的额外提示

  - name: documentary
    label: 是否纪录片
    values:
      - yes
      - no
    ai_prompt: "请判断是否为纪录片（yes/no）"

  - name: restricted
    label: 是否限制级
    values:
      - yes
      - no
    ai_prompt: "请判断是否为限制级内容（yes/no）"

# ------------------------------------------------------------
# 4. 文件名模板配置
# ------------------------------------------------------------
# 定义刮削后的文件命名规则
# 支持的变量：
#   - {title_cn}: 中文标题
#   - {title_en}: 英文标题
#   - {year}: 年份
#   - {resolution}: 分辨率（从原文件名提取，如720p/1080p/2160p）
#   - {quality}: 画质（从原文件名提取，如BluRay/Web-DL）
#   - {season}: 季号（仅电视剧，如1、2、3）
#   - {episode}: 集号（仅电视剧，如1、2、3）
#   - {original}: 原文件名（不含扩展名）
#   - {ext}: 原文件扩展名
#   - {lang}: 字幕语言（仅字幕模板使用）
filename_templates:
  movie: "{title_cn}.{title_en}.{year}.{resolution}.{quality}.{ext}"
  tv: "{title_cn}.{title_en}.{year}.S{season:02d}E{episode:02d}.{resolution}.{quality}.{ext}"
  subtitle: "{video_filename}.{lang}.{ext}"  # 字幕文件命名模板

# ------------------------------------------------------------
# 5. 入库路径模板配置
# ------------------------------------------------------------
# 定义不同维度组合对应的入库路径
# 模板变量：
#   - {title_cn}: 中文标题
#   - {title_en}: 英文标题
#   - {year}: 年份
#   - {season}: 季号（仅电视剧）
#   - {episode}: 集号（仅电视剧）
#   - {dimension.xxx}: 任意维度的值，如{dimension.media_type}
# 规则按顺序匹配，命中第一条后不再继续
path_rules:
  # 规则1：电视剧
  - conditions:
      media_type: tv
    template: "/入库/电视剧/{title_cn} ({year})/Season {season}/"

  # 规则2：非纪录片电影
  - conditions:
      media_type: movie
      documentary: no
    template: "/入库/电影/{year}/{title_cn} ({year})/"

  # 规则3：纪录片电影
  - conditions:
      media_type: movie
      documentary: yes
    template: "/入库/纪录片/{title_cn} ({year})/"

  # 默认规则（兜底，必须保留此规则）
  - conditions: {}
    template: "/入库/其他/{title_cn} ({year})/"

# ------------------------------------------------------------
# 6. 特殊处理规则
# ------------------------------------------------------------
# 定义特定条件下的处理规则
rules:
  # 规则1：电视剧单独文件夹
  # 当media_type == tv时，必须为每部剧创建单独的文件夹
  - name: tv_series_folder
    description: "电视剧必须单独文件夹"
    conditions:
      media_type: tv
    actions:
      - create_series_folder: true   # 创建剧集文件夹
      - organize_by_season: true    # 按季组织
      - use_series_subfolder: "{title_cn} ({year})/"

  # 规则2：电影是否按年份文件夹
  # 当media_type == movie时，是否将电影放入年份文件夹
  - name: movie_year_folder
    description: "电影按年份分文件夹"
    conditions:
      media_type: movie
    actions:
      - create_year_folder: true    # true=按年份文件夹；false=不按年份

# ------------------------------------------------------------
# 7. 同名文件处理
# ------------------------------------------------------------
duplicate_handling:
  strategy: "skip"                      # skip=跳过, overwrite=覆盖, rename=自动重命名
  notify: true                          # 是否通知
  notify_title_only: true               # 同名检测只检查标题和年份，忽略分辨率
  # rename_pattern: "{title_cn} ({year}) - {i}.{ext}"  # 如选择rename策略时使用

# ------------------------------------------------------------
# 8. Hermes配置
# ------------------------------------------------------------
hermes:
  # 连接方式（二选一，推荐http）
  connection_type: "http"

  # HTTP API方式配置（推荐）
  http:
    base_url: "http://192.168.1.100:8080"  # Hermes服务地址
    timeout: 30                            # 请求超时时间（秒）
    api_key: ""                            # API密钥（如需要）

  # SSH方式配置（备选）
  ssh:
    host: "192.168.1.100"                  # Hermes主机地址
    port: 22                               # SSH端口
    user: "hermes"                         # SSH用户名
    private_key_path: ""                   # SSH私钥路径
    command_prefix: "python media_importer.py"  # 命令前缀

  # Webhook配置（本程序 → Hermes通知）
  webhook:
    route_name: "media-normalize"         # Webhook路由名称
    secret: ""                            # 用于签名验证（与Hermes端一致）
    max_retries: 3                        # 发送失败最大重试次数
    retry_delay: 5                        # 重试间隔（秒）
    events:                               # 需要发送通知的事件类型
      - task_complete                     # 任务完成
      - task_failed                       # 任务失败
      - task_skipped                      # 任务跳过（同名文件）
      - batch_complete                    # 批量任务完成

# ------------------------------------------------------------
# 9. 文件监控配置（可选）
# ------------------------------------------------------------
file_watcher:
  enabled: true                           # 是否启用文件监控
  poll_interval: 10                       # 轮询间隔（秒）
  ignore_patterns:                        # 忽略的文件模式
    - "*.tmp"
    - ".DS_Store"
    - "*partial*"

# ------------------------------------------------------------
# 10. 任务队列配置
# ------------------------------------------------------------
task_queue:
  persistence_path: "/nas本地/tasks.json"    # 任务持久化存储路径
  max_concurrent: 1                          # 最大并发数（当前方案固定为1）
  retry_on_failure: false                    # 失败任务是否自动重试
  auto_delete_success: true                  # 成功任务是否自动清理
  auto_delete_failed: false                  # 失败任务是否自动清理
  history_retention_days: 90                 # 历史任务保留天数

# ------------------------------------------------------------
# 11. 钩子配置（可选，为空则不执行）
# ------------------------------------------------------------
hooks:
  before_process: ""      # 处理前执行的脚本（如暂停下载、通知准备开始等）
  after_success: ""       # 成功后执行的脚本（如通知播放器刷新库）
  after_failure: ""       # 失败后执行的脚本（如发送告警）

# ------------------------------------------------------------
# 12. 日志配置
# ------------------------------------------------------------
logging:
  level: "INFO"                          # 日志级别：DEBUG/INFO/WARN/ERROR
  format: "json"                         # 日志格式：json（结构化）| text（纯文本）
  max_size_mb: 100                       # 单个日志文件最大大小（MB）
  backup_count: 5                        # 保留的日志备份数量
```

### AI刮削接口设计

**请求格式：**
```json
{
  "video_filename": "Breaking.Bad.S01E01.720p.BluRay.x264.mp4",
  "video_extension": "mp4",
  "subtitle_filenames": ["Breaking.Bad.S01E01.720p.BluRay.x264.zh.srt"],
  "source_dir": "/挂载/下载/",
  "dimensions_config": [...]
}
```

**期望响应格式：**
```json
{
  "title_cn": "绝命毒师",
  "title_en": "Breaking Bad",
  "year": "2008",
  "resolution": "720p",
  "quality": "BluRay",
  "language": "en",
  "media_type": "tv",
  "season": 1,
  "episode": 1,
  "dimensions": {
    "media_type": "tv",
    "documentary": "no",
    "restricted": "yes"
  },
  "confidence": 0.95,
  "raw_info": "从原文件名提取的原始信息（用于调试）"
}
```

**AI提示词设计（最终版）：**
```
你是一个专业的影视信息刮削助手。
请根据以下输入信息，返回JSON格式的影视元数据。

输入：
视频文件名：{video_filename}
字幕文件名：{subtitle_filenames}

请执行以下步骤：

1. 识别影视基本信息：
   - title_cn: 中文标题（如果有）
   - title_en: 英文标题
   - year: 发行年份（4位数字）
   - resolution: 分辨率（从原文件名提取，如720p/1080p/2160p）
   - quality: 画质（从原文件名提取，如BluRay/Web-DL）
   - language: 主要语言（如en/zh）

2. 识别是电视剧还是电影：
   - 注意：如果文件名中包含S01E01/S1E1/Season 1等标识的是电视剧
   - type: movie 或 tv
   - 如果是电视剧，还需要：
     - season: 季号（数字）
     - episode: 集号（数字）

3. 根据以下配置的维度，逐一判断：
{dimensions_prompts}

4. 所有维度的值必须是配置中定义的values之一

5. 最后返回所有维度的判断结果

请严格按以下JSON格式返回（不要返回Markdown代码块标记）：
{json_schema}
```

**异常处理策略（大模型API）：**
- API超时：重试2次，间隔3秒，仍失败则尝试降级模型
- 返回无效JSON：标记失败，通知Hermes
- 置信度低于阈值：继续处理但标记为低置信度，通知中提示需人工确认
- API额度用完：标记失败，通知Hermes

### 任务去重和同名检测

**同名检测规则：**
- 判断"同名"的标准：
  1. 年份相同
  2. 英文标题相同 或 中文标题相同（二者之一即可）
  3. 如果是电视剧，季号和集号也相同
- 不考虑：分辨率、画质、制作渠道等差异

**处理策略：**
- 发现同名文件 → 跳过，不覆盖
- 通过Hermes Webhook发送通知
- 记录到任务日志中
- 支持配置 rename 策略（自动追加序号重命名）

```json
{
  "task_id": "...",
  "status": "SKIPPED",
  "reason": "同名文件已存在",
  "existing_file": "/入库/.../xxx.mp4",
  "skipped_file": "源文件/xxx.mp4"
}
```

### Hermes集成设计

根据Hermes源码分析，Skill通过内置工具与外部程序交互。本程序同时提供HTTP API（推荐）和CLI（备选）两种接口。

#### 1. 本程序HTTP API设计（完整版）

```
# 任务管理
POST   /api/run                      # 触发扫描并执行所有待处理文件
POST   /api/run/file                 # 执行指定文件 {"file_path": "/path/to/file.mkv"}
GET    /api/tasks                    # 获取任务列表 ?status=pending|processing|success|failed|skipped&limit=20&offset=0
GET    /api/tasks/{task_id}          # 获取任务详情
POST   /api/tasks/{task_id}/retry    # 重试失败任务（重置状态为PENDING）
DELETE /api/tasks/{task_id}          # 删除任务
POST   /api/tasks/clear              # 清空任务列表 {"status": "failed"}（可选按状态过滤）

# 队列操作
POST   /api/queue/pause              # 暂停队列处理
POST   /api/queue/resume             # 恢复队列处理
GET    /api/queue/status             # 获取队列状态 {"paused": false, "pending_count": 10, "processing_count": 0}

# 配置
GET    /api/config                   # 获取当前配置（敏感信息脱敏）
POST   /api/config/reload            # 重新加载配置文件

# 监控
GET    /api/health                   # 健康检查（源目录可访问、LLM可连接、入库目录可写、Hermes可连接）
GET    /api/metrics                  # 指标统计

# 日志
GET    /api/logs                     # 获取日志 ?limit=100&level=ERROR&task_id=xxx
```

**统一响应格式：**
```json
{
  "code": 0,
  "message": "成功",
  "data": {...}
}
```

**错误码设计：**
```
0    成功
1001 配置文件错误
1002 源目录不可访问
1003 入库目录不可写
2001 AI刮削失败
2002 AI返回格式无效
2003 AI置信度低
3001 同名文件冲突
3002 文件移动失败
3003 磁盘空间不足
4001 Hermes通知失败
4002 Hermes连接失败
```

#### 2. Hermes Webhook通知格式

本程序主动调用Hermes Webhook发送通知：

```
POST /webhooks/{route_name}
Content-Type: application/json
X-GitHub-Event: media.normalize
X-Webhook-Signature: sha256=xxxxx

{
  "data": {
    "event_type": "task_complete",
    "status": "success|failed|skipped",
    "task_id": "uuid",
    "video_file": "原文件名.mkv",
    "scraped_info": {
      "title_cn": "绝命毒师",
      "title_en": "Breaking Bad",
      "year": "2008",
      "type": "tv",
      "season": 1,
      "episode": 1,
      "dimensions": {...}
    },
    "import_path": "/入库/电视剧/绝命毒师 (2008)/Season 1/",
    "message": "处理完成",
    "error": null
  }
}
```

**事件类型：**
- `task_complete`：任务完成（成功）
- `task_failed`：任务失败（需要人工处理）
- `task_skipped`：任务跳过（同名文件）
- `batch_complete`：批量任务完成（所有待处理任务完成后的汇总通知）

#### 3. Hermes Skill设计

**Skill Prompt模板：**
```
你是NAS影视入库助手。你可以帮助用户管理和触发影视文件入库任务。

## 可用工具
- web_tools: 调用 media_importer 的 HTTP API
- terminal_tool: 通过 SSH 执行 media_importer 命令

## 用户意图映射
- "执行入库 / 开始处理 / 触发任务" → POST /api/run
- "处理文件 xxx" → POST /api/run/file
- "查看任务 / 任务列表 / 有什么任务" → GET /api/tasks
- "查看任务详情 xxx / xxx任务怎么样了" → GET /api/tasks/{task_id}
- "重试任务 xxx / 重新处理xxx" → POST /api/tasks/{task_id}/retry
- "查看日志 / 最近日志 / 有没有报错" → GET /api/logs
- "系统状态 / 健康检查 / 有没有问题" → GET /api/health

## API地址
base_url: {config.hermes.http.base_url}

## 输出格式
将API响应格式化为用户友好的文本。重点关注：
1. 任务状态和数量
2. 成功/失败/跳过的汇总
3. 失败任务的错误原因和重试建议
```

**Hermes Skill配置（给Hermes端）：**
```yaml
skill:
  name: "media_importer"
  description: "NAS影视自动化入库管理"

  webhook:
    route: "media-normalize"
    events: ["task_complete", "task_failed", "task_skipped"]

  deliver:
    - type: feishu
      on: ["task_failed", "task_skipped", "batch_complete"]
    - type: weixin
      on: ["task_failed"]
    - type: log
      on: ["task_complete", "task_failed", "task_skipped"]
```

#### 4. 命令行工具接口（备选）

```bash
# 触发执行
python media_importer.py run --all
python media_importer.py run --file "xxx.mkv"

# 查询任务
python media_importer.py list --status pending|success|failed|skipped --limit 20
python media_importer.py show <task_id>

# 队列操作
python media_importer.py queue --pause
python media_importer.py queue --resume
python media_importer.py queue --status

# 重试失败任务
python media_importer.py retry <task_id>
python media_importer.py retry --all

# 清理任务
python media_importer.py clear --status failed

# 查看日志
python media_importer.py log --last 10 --level ERROR --task <task_id>

# 系统
python media_importer.py health
python media_importer.py metrics
python media_importer.py config
```

#### 5. 部署架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Hermes                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Skill       │  │ Webhook     │  │ Deliver             │ │
│  │ (用户交互)   │  │ (接收通知)   │  │ (飞书/微信/日志)    │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                      HTTP API / CLI
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    NAS (飞牛NAS)                            │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  media_importer                                        ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ ││
│  │  │ HTTP 服务   │  │ CLI 工具    │  │ 文件监控        │ ││
│  │  │ (http.server)│  │ (argparse) │  │ (轮询模式)      │ ││
│  │  └─────────────┘  └─────────────┘  └─────────────────┘ ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ ││
│  │  │ 任务队列    │  │ 日志管理    │  │ 配置文件        │ ││
│  │  │ (JSON持久化) │  │ (JSON格式)  │  │ (config.yaml)  │ ││
│  │  └─────────────┘  └─────────────┘  └─────────────────┘ ││
│  └─────────────────────────────────────────────────────────┘│
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ 网盘挂载     │  │ 本地临时目录 │  │ 入库目录           │ │
│  │ (源目录)     │  │ (处理中)    │  │ (分类后)          │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 任务管理设计

**任务状态机：**
```
PENDING → PROCESSING → SUCCESS / FAILED / SKIPPED
                                    ↘ 手动重试 → PENDING
                                    ↘ 清除    → DELETED
```

**任务生命周期：**

| 阶段 | 状态 | 说明 |
|------|------|------|
| 创建 | PENDING | 文件被发现，进入队列等待处理 |
| 执行中 | PROCESSING | 正在处理该文件 |
| 完成 | SUCCESS | 处理成功，文件已入库 |
| 失败 | FAILED | 处理失败，需要人工介入 |
| 跳过 | SKIPPED | 同名文件已存在，自动跳过 |
| 清除 | DELETED | 任务记录被手动清除（不删除实际文件） |

**任务记录：**
```json
{
  "task_id": "uuid",
  "video_file": "原文件名.mkv",
  "video_path": "/源目录/原文件名.mkv",
  "file_size_mb": 2048,
  "subtitle_files": ["字幕1.zh.srt", "字幕2.en.srt"],
  "source_dir_info": "发现时的目录信息",
  "scraped_info": {
    "title_cn": "绝命毒师",
    "title_en": "Breaking Bad",
    "year": "2008",
    "type": "tv",
    "season": 1,
    "episode": 1,
    "resolution": "720p",
    "quality": "BluRay",
    "dimensions": {
      "media_type": "tv",
      "documentary": "no",
      "restricted": "yes"
    },
    "confidence": 0.95,
    "low_confidence_warning": false
  },
  "import_path": "/入库/电视剧/绝命毒师 (2008)/Season 1/",
  "final_filename": "绝命毒师.Breaking Bad.2008.S01E01.720p.BluRay.mkv",
  "status": "SUCCESS",
  "created_at": "2026-05-16T10:00:00+08:00",
  "started_at": "2026-05-16T10:00:05+08:00",
  "completed_at": "2026-05-16T10:01:30+08:00",
  "error_code": null,
  "error_message": null,
  "retry_count": 0,
  "logs": [
    {"time": "10:00:05", "level": "INFO", "step": "scan", "message": "发现视频文件"},
    {"time": "10:00:05", "level": "INFO", "step": "scan", "message": "发现1个字幕文件"},
    {"time": "10:00:10", "level": "INFO", "step": "scrape", "message": "AI刮削完成，置信度0.95"},
    {"time": "10:00:10", "level": "INFO", "step": "validate", "message": "刮削结果校验通过"},
    {"time": "10:00:10", "level": "INFO", "step": "classify", "message": "匹配path_rules[0]: 电视剧"},
    {"time": "10:00:10", "level": "INFO", "step": "dedup", "message": "同名检测通过"},
    {"time": "10:00:12", "level": "INFO", "step": "match", "message": "匹配字幕: 字幕1.zh.srt"},
    {"time": "10:01:30", "level": "INFO", "step": "import", "message": "文件已入库"},
    {"time": "10:01:30", "level": "INFO", "step": "notify", "message": "已通知Hermes"}
  ]
}
```

### 错误处理策略

#### 文件操作错误

| 错误场景 | 处理策略 |
|---------|---------|
| 源目录不可访问 | 启动时检查，如不存在则报错退出 |
| 临时目录不可写 | 启动时检查，如不可写则报错退出 |
| 入库目录不可写 | 启动时检查，如不可写则报错退出 |
| 磁盘空间不足 | 处理前检查，不足则暂停任务，通知Hermes |
| 文件被占用 | 等待5秒重试，仍失败则标记`FAILED` |
| 跨设备移动失败 | 自动降级为"复制+删除"模式 |
| 文件权限错误 | 标记`FAILED`，通知Hermes |

#### AI刮削错误

| 错误场景 | 处理策略 |
|---------|---------|
| API超时 | 重试2次（间隔3秒），仍失败标记`FAILED` |
| 返回非JSON | 标记`FAILED`，附带原始返回内容 |
| 置信度 < 阈值 | 继续处理但标记低置信度，通知中提醒人工确认 |
| API额度用完 | 标记`FAILED`，通知Hermes |
| 降级模型也失败 | 标记`FAILED`，等待人工处理 |

#### 入库目录处理

| 错误场景 | 处理策略 |
|---------|---------|
| 入库目录不存在 | 自动创建（含父目录） |
| 目录创建失败 | 标记`FAILED`，通知Hermes |

### 健康检查设计

`GET /api/health` 返回：
```json
{
  "code": 0,
  "data": {
    "status": "healthy|degraded|unhealthy",
    "checks": {
      "source_dir": {"status": "ok", "detail": "/挂载/网盘下载 可访问"},
      "temp_dir": {"status": "ok", "detail": "/nas本地/临时目录 可写"},
      "import_dirs": {"status": "ok", "detail": "3个入库路径均正常"},
      "llm_api": {"status": "ok", "detail": "LLM API 响应正常"},
      "hermes": {"status": "ok", "detail": "Hermes 连接正常"},
      "disk_space": {"status": "ok", "detail": "可用空间 500GB"}
    },
    "uptime": "2d 3h 15m",
    "queue_status": {
      "pending": 5,
      "processing": 0,
      "paused": false
    }
  }
}
```

### 指标统计设计

`GET /api/metrics` 返回：
```json
{
  "code": 0,
  "data": {
    "total_tasks": 150,
    "success_tasks": 140,
    "failed_tasks": 5,
    "skipped_tasks": 5,
    "success_rate": 0.933,
    "avg_processing_time_seconds": 85.3,
    "total_llm_calls": 150,
    "llm_failures": 3,
    "current_queue_pending": 5
  }
}
```

## 部署方案

### 方式1：Python环境 + systemd（推荐）

```bash
# 步骤1：安装Python（FNOS通常已自带）
python3 --version

# 步骤2：创建虚拟环境
cd /path/to/media_importer
python3 -m venv venv
source venv/bin/activate
pip install pyyaml

# 步骤3：配置config.yaml（手动编辑）

# 步骤4：创建systemd服务
# /etc/systemd/system/media-importer.service
```

```ini
[Unit]
Description=NAS Media Importer Service
After=network.target

[Service]
Type=simple
User=nas
WorkingDirectory=/path/to/media_importer
ExecStart=/path/to/media_importer/venv/bin/python media_importer.py serve --port 9855
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable media-importer
sudo systemctl start media-importer
```

### 方式2：PyInstaller打包

```bash
# 打包为独立可执行文件（无需Python环境）
pip install pyinstaller
pyinstaller --onefile --name media_importer media_importer.py
# 产出: dist/media_importer
```

### 方式3：Docker（如有需要）

```dockerfile
FROM python:3.11-alpine
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "media_importer.py", "serve", "--port", "9855"]
```

## 依赖清单

```text
# requirements.txt
pyyaml>=6.0        # YAML配置文件解析
```

可选依赖：
```text
# requirements-optional.txt
watchdog>=4.0      # 文件系统监控（非必须，可用轮询替代）
```

本项目核心设计原则：**尽可能使用Python标准库**。
- 配置文件：`yaml` → pyyaml（唯一必须的外部依赖）
- HTTP服务：`http.server`（标准库）
- HTTP客户端：`urllib.request`（标准库，如果可用）或 `http.client`，否则`requests`
- JSON处理：`json`（标准库）
- 命令行参数：`argparse`（标准库）
- 文件操作：`os`/`shutil`/`pathlib`（标准库）
- 日志：`logging`（标准库）
- UUID：`uuid`（标准库）

## 项目结构

```
media_importer/
├── media_importer.py         # 主入口（CLI + HTTP服务）
├── config.yaml               # 默认配置文件
├── config_loader.py          # 配置加载和校验模块
├── file_scanner.py           # 文件扫描模块
├── llm_scraper.py            # AI刮削引擎
├── classifier.py             # 分类匹配引擎
├── dedup_checker.py          # 同名检测模块
├── file_mover.py             # 文件移动和重命名模块
├── task_manager.py           # 任务队列和持久化
├── hermes_hook.py            # Hermes通知模块
├── safety.py                 # 安全检查模块
├── file_watcher.py           # 文件监控模块
├── logger.py                 # 结构化日志模块
├── api_server.py             # HTTP API服务
├── hooks.py                  # 脚本钩子执行
├── tests/
│   ├── test_file_scanner.py
│   ├── test_llm_scraper.py
│   ├── test_classifier.py
│   └── test_dedup_checker.py
├── logs/                     # 日志目录（运行期生成）
├── tasks.json                # 任务持久化文件（运行期生成）
└── requirements.txt
```

## 关键设计决策

### Q1: 编程语言选择 — RESOLVED
**决策：** 使用Python开发
**理由：**
- 需要调用AI大模型API、处理JSON、文件操作等，Python生态成熟
- 用户明确表示可以接受Python，只要轻量
- 核心逻辑使用标准库，仅pyyaml一个必须外部依赖
- 支持PyInstaller打包为独立可执行文件

**替代方案考虑：**
- Shell脚本：对于复杂逻辑（JSON处理、AI调用）实现困难，不选
- Go：更轻量但用户不熟悉，增加学习成本

### Q2: 依赖管理策略 — RESOLVED
**决策：** 最小化依赖，仅使用标准库 + pyyaml
**理由：**
- 用户强调轻量优先
- FNOS环境部署便利性要求
- Python标准库已覆盖HTTP服务、JSON处理、文件操作等需求

**必需依赖：**
- `pyyaml`：配置文件解析（唯一必须的外部依赖）

**可选依赖：**
- `watchdog`：文件监控（可用轮询替代，不强制）

**排除项：**
- 不使用Web框架（Flask/FastAPI），HTTP服务使用`http.server`标准库
- 不使用数据库，使用JSON文件存储任务日志
- 不使用ORM，直接操作JSON文件

### Q3: 文件刮削策略 — RESOLVED
**决策：** 基于文件名的单文件刮削，不处理目录结构
**理由：**
- 用户明确"不管上层目录名"，只刮削文件名
- 简化实现，符合"轻量"原则
- 避免嵌套目录带来的复杂性

### Q4: 字幕处理策略 — RESOLVED
**决策：**
1. 字幕文件匹配视频文件（视频名.zh.srt → 视频名.mp4）
2. 多语言字幕全部保留
3. 暂不实现视频内嵌字幕检测

**理由：**
- 用户明确要求"尽量不要安装一堆依赖"
- 视频内嵌字幕检测需要FFmpeg等依赖，增加复杂度
- 作为后续扩展功能

### Q5: 入库目录结构 — RESOLVED
**决策：**
- 电影：支持配置是否按年份分目录
- 电视剧：必须单独文件夹，按季组织
**理由：**
- 用户提供了两种场景合并通过配置模板灵活支持

### Q6: 异常处理策略 — RESOLVED
**决策：** 失败任务暂停 → 通知Hermes → 人工处理 → 继续执行
**理由：**
- 用户表示"基本都是人工干预解决完问题，再处理执行"
- 简化实现，不需要复杂的自动重试逻辑
- 任务日志记录详细失败原因和错误码，便于排查

### Q7: 并发处理 — RESOLVED
**决策：** 不支持并发，排队顺序执行
**理由：** 简化实现，避免文件冲突和资源竞争

### Q8: 部署策略 — RESOLVED
**决策：** 优先systemd + Python虚拟环境；可选PyInstaller打包
**理由：**
- systemd是Linux标准服务管理方式，FNOS支持
- PyInstaller打包可消除Python环境依赖
- Docker作为备选方案

## 暂不包含范围

- 视频内嵌字幕检测（依赖过多，可作为后续扩展）
- 元数据文件生成（海报、nfo等，用户明确不需要）
- 资源搜索和下载（用户已有网盘资源来源）
- HTML管理界面（用户明确不需要）

## 后续扩展方向

- 视频内嵌字幕检测（需引入FFmpeg依赖）
- 大文件处理进度通知
- 多源目录支持
- 定时任务集成
