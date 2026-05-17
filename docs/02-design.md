---
title: "NAS影视自动化入库系统"
type: design
date: 2026-05-16
prev: docs/01-requirements.md
next: docs/03-development-plan.md
---

# NAS影视自动化入库系统 — 方案设计

## Why
飞牛NAS影视文件下载后需要人工刮削文件名和分拣入库，过程繁琐。需要一套轻量级自动化系统，通过AI自动刮削+分类入库，结合Hermes实现任务管理和异常通知。

## What Changes
- 新增 media_importer 项目（Python，最小依赖）
- 提供 HTTP API + CLI 双接口
- 配置文件驱动（YAML），支持多维度分类
- 集成 Hermes Webhook 通知
- systemd 部署方案

## Impact
- Affected specs: 全新项目，无已有受影响 specs
- Affected code: 全新项目目录 `media_importer/`

---

## ADDED Requirements

### Requirement: 配置文件管理
系统 SHALL 通过 YAML 配置文件管理所有设置，包含12个配置段落。

配置文件 SHALL 位于项目根目录 `config.yaml`，包含以下段落：
1. 基础配置（源目录、临时目录、日志目录、扫描规则、视频/字幕扩展名）
2. 大模型配置（provider、api_key、base_url、model、timeout、重试、降级模型、置信度阈值）
3. 分类维度配置（可扩展，每个维度含 name/label/values/ai_prompt/ai_hint）
4. 文件名模板配置（movie/tv/subtitle 三种模板，支持变量替换）
5. 入库路径模板配置（path_rules 数组，按 conditions 条件匹配 template）
6. 特殊处理规则（电视剧单独文件夹、电影按年份配置）
7. 同名文件处理（strategy/notify/rename_pattern）
8. Hermes 配置（连接方式/http/ssh/webhook/events）
9. 文件监控配置（enabled/poll_interval/ignore_patterns）
10. 任务队列配置（persistence_path/max_concurrent/auto_delete/retention）
11. 钩子配置（before_process/after_success/after_failure）
12. 日志配置（level/format/max_size_mb/backup_count）

#### Scenario: 配置文件缺失
- **WHEN** 程序启动时 config.yaml 不存在
- **THEN** 系统在项目根目录生成默认配置模板并退出，提示用户编辑配置

#### Scenario: 配置文件格式错误
- **WHEN** YAML 解析失败
- **THEN** 系统输出错误详情并退出，返回错误码 1001

#### Scenario: 配置校验通过
- **WHEN** 配置加载成功且所有必需字段完整
- **THEN** 系统继续启动流程

### Requirement: 任务处理核心流程
系统 SHALL 实现10步处理流水线，每个视频文件依次通过。

**10步流水线：**

1. **[扫描]** — 递归扫描源目录，按 video_extensions 和 subtitle_extensions 过滤，忽略 ignore_patterns
2. **[复制]** — 将视频文件和关联字幕文件复制到临时目录，支持断点续传：
   - 使用临时文件标记（.copying 后缀），复制完成后重命名
   - 启动时检查并清理残留的 .copying 文件
   - 复制失败（网络中断、磁盘空间不足）标记 FAILED 并通知
3. **[刮削]** — 调用大模型 API，根据文件名分析元数据：
   - 输入：视频文件名 + 字幕文件名 + dimensions 配置
   - 输出：{title_cn, title_en, year, resolution, quality, language, type, season, episode, dimensions, confidence}
   - 失败重试 2 次（间隔 3 秒），仍失败则尝试降级模型
   - 置信度 < 阈值时继续但标记 low_confidence_warning
4. **[校验]** — 校验刮削结果的完整性和合法性：
   - 检查必需字段是否存在（title_en、year、type 等）
   - 校验 dimensions 值是否在配置的 values 范围内
   - 校验置信度是否达标
   - 校验失败标记 FAILED（错误码 2002 或 2003）
5. **[分类]** — 遍历 path_rules，用 dimensions 匹配 conditions：
   - 命中第一条规则 → 使用对应 template 生成入库路径
   - 未命中任何规则 → 使用 conditions: {} 的兜底规则
6. **[同名检测]** — 检查入库路径下是否已存在同名文件：
   - 同名定义：年份相同 + (title_cn 相同 或 title_en 相同)
   - 电视剧还需 season + episode 相同
   - 根据 duplicate_handling.strategy 处理（skip/overwrite/rename）
7. **[命名]** — 应用 filename_templates 生成最终文件名，匹配字幕文件到对应视频
8. **[入库]** — 创建入库目录 → 移动文件 → 清理临时文件 → 删除源文件
9. **[通知]** — 调用 Hermes Webhook 通知
10. **[记录]** — 更新 tasks.json

#### Scenario: 完整成功流程
- **WHEN** 系统处理一个视频文件
- **THEN** 执行完整的10步流程：扫描→复制→刮削→校验→分类→同名检测→命名→入库→通知→记录
- **AND** 每个步骤在任务日志中记录时间和状态

#### Scenario: 复制步骤中断恢复
- **WHEN** 复制过程中程序崩溃或网络中断
- **THEN** 重启后扫描临时目录中残留的 .copying 文件
- **AND** 自动清理残留文件并重新开始复制

#### Scenario: AI刮削失败
- **WHEN** 大模型 API 返回非 JSON 或超时（重试 2 次后）
- **THEN** 任务标记为 FAILED，错误码 2001
- **AND** 调用 Hermes Webhook 发送 task_failed 通知

#### Scenario: 同名文件跳过
- **WHEN** 入库路径下已存在同名文件且 strategy=skip
- **THEN** 任务标记为 SKIPPED，记录 existing_file 路径
- **AND** 调用 Hermes Webhook 发送 task_skipped 通知

### Requirement: 任务队列管理
系统 SHALL 通过 JSON 文件实现任务持久化和队列管理。

任务状态机：`PENDING → PROCESSING → SUCCESS / FAILED / SKIPPED`
- FAILED 任务支持手动重试（状态重置回 PENDING）
- 支持通过 API 清除指定状态的任务（软删除，保留历史）

任务记录 JSON 结构包含：
- task_id（UUID）、video_file、video_path、file_size_mb
- subtitle_files 列表
- scraped_info（完整刮削结果含 dimensions）
- import_path、final_filename
- status、created_at、started_at、completed_at
- error_code、error_message、retry_count
- logs 数组（每个步骤的 time/level/step/message）

#### Scenario: 任务持久化
- **WHEN** 系统创建新任务或更新任务状态
- **THEN** 立即写入 tasks.json 文件
- **AND** 程序重启后自动加载所有未完成的任务

#### Scenario: 顺序执行
- **WHEN** 多个文件进入 PENDING 状态
- **THEN** 系统按 FIFO 顺序逐个处理
- **AND** 同一时间仅一个文件处于 PROCESSING 状态

#### Scenario: 查看任务进度
- **WHEN** 用户查询某个 PROCESSING 状态的任务
- **THEN** 响应包含 progress 字段（当前步骤/总步骤，百分比）
- **AND** 当前步骤名称（如"复制中"、"刮削中"、"入库中"）

### Requirement: 进度追踪
系统 SHALL 支持实时任务进度查询。

进度信息 SHALL 包含：
- 当前步骤编号和名称（如 4/10 刮削中）
- 百分比完成度（整数，0-100）
- 如当前步骤为复制，额外包含已复制字节数/总字节数

进度 SHALL 通过以下方式暴露：
- GET /api/tasks/{task_id} 返回 progress 字段
- Hermes Skill 可查询并展示给用户

#### Scenario: 查询处理中任务的进度
- **WHEN** 用户通过 Hermes 查询 "任务xxx怎么样了"
- **THEN** 返回当前步骤、百分比、预估剩余时间（如可计算）

### Requirement: HTTP API 服务
系统 SHALL 提供 HTTP REST API，使用 Python 标准库 `http.server` 实现。

**API 端点：**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/run | 触发扫描并执行所有待处理文件 |
| POST | /api/run/file | 执行指定文件 |
| GET | /api/tasks | 任务列表（支持 status/limit/offset 参数） |
| GET | /api/tasks/{task_id} | 任务详情（含 progress） |
| POST | /api/tasks/{task_id}/retry | 重试失败任务 |
| DELETE | /api/tasks/{task_id} | 删除任务 |
| POST | /api/tasks/clear | 清空指定状态的任务 |
| POST | /api/queue/pause | 暂停队列 |
| POST | /api/queue/resume | 恢复队列 |
| GET | /api/queue/status | 队列状态 |
| GET | /api/config | 当前配置（脱敏） |
| POST | /api/config/reload | 重新加载配置 |
| GET | /api/health | 健康检查 |
| GET | /api/metrics | 指标统计 |
| GET | /api/logs | 查询日志 |

**统一响应格式：**
```json
{
  "code": 0,
  "message": "success",
  "data": {...}
}
```

**错误码体系：**
- 0：成功
- 1001：配置文件错误
- 1002：源目录不可访问
- 1003：临时/入库目录不可写
- 2001：AI 刮削失败
- 2002：AI 返回格式无效
- 2003：AI 置信度低
- 3001：同名文件冲突
- 3002：文件操作失败（移动/复制）
- 3003：磁盘空间不足
- 4001：Hermes 通知失败
- 4002：Hermes 连接失败

#### Scenario: HTTP 服务启动
- **WHEN** 执行 `python media_importer.py serve --port 9855`
- **THEN** HTTP 服务在指定端口启动，监听所有接口
- **AND** 启动时先校验配置和关键目录可访问性

#### Scenario: 健康检查通过
- **WHEN** 请求 GET /api/health
- **THEN** 返回各组件状态（源目录、临时目录、入库目录、LLM API、Hermes、磁盘空间）
- **AND** 每个组件显示 ok/degraded/unhealthy 状态

### Requirement: 命令行接口
系统 SHALL 提供 CLI 工具作为备选交互方式。

```bash
python media_importer.py serve --port 9855     # 启动HTTP服务
python media_importer.py run --all             # 扫描并处理所有文件
python media_importer.py run --file "xxx.mkv"  # 处理指定文件
python media_importer.py list --status [status] --limit [N]
python media_importer.py show <task_id>
python media_importer.py retry <task_id>
python media_importer.py retry --all
python media_importer.py queue --pause|--resume|--status
python media_importer.py clear --status [status]
python media_importer.py log --last [N] --level [LEVEL] --task [ID]
python media_importer.py health
python media_importer.py metrics
python media_importer.py config
```

### Requirement: AI 刮削引擎
系统 SHALL 调用大模型 API 进行文件刮削，支持 OpenAI 兼容接口。

刮削引擎 SHALL：
- 接收视频文件名 + 字幕文件名列表 + dimensions 配置
- 构建动态 system prompt（根据 dimensions 配置生成字段要求）
- 发送请求到配置的 LLM base_url
- 解析返回 JSON
- 验证所有 dimensions 值在配置的 values 范围内
- 支持 max_retries 次重试 + fallback_model 降级

#### Scenario: 刮削返回无效 JSON
- **WHEN** LLM 返回内容不是合法 JSON 或缺少必需字段
- **THEN** 尝试重试（最多 max_retries 次）
- **AND** 仍失败则标记 FAILED（错误码 2002），附带原始返回内容

#### Scenario: 低置信度处理
- **WHEN** confidence < confidence_threshold
- **THEN** 继续处理但设置 low_confidence_warning=true
- **AND** 通知中提示用户需人工确认

### Requirement: 文件扫描器
系统 SHALL 递归扫描源目录，识别视频和字幕文件。

扫描器 SHALL：
- 按 source_dir_scan.recursive 递归扫描
- 按 source_dir_scan.max_depth 限制深度
- 按 video_extensions 过滤视频文件
- 按 subtitle_extensions 过滤字幕文件
- 按 ignore_patterns 排除临时文件
- 将视频和字幕按文件名前缀分组（同一组的视频和字幕一起处理）

#### Scenario: 发现新文件
- **WHEN** 文件监控检测到源目录有新文件
- **THEN** 自动创建 PENDING 任务并加入队列
- **AND** 如队列未暂停，自动开始处理

### Requirement: 分类匹配器
系统 SHALL 根据 AI 刮削结果和配置规则确定入库路径。

匹配逻辑：
1. 遍历 path_rules 数组（按顺序）
2. 对每条规则，检查 conditions 中所有 key-value 是否与 dimensions 匹配
3. 命中 → 使用该规则 template 生成路径
4. 未命中任何规则 → 使用 conditions: {} 的兜底规则
5. 将 generated path 中的模板变量替换为实际值

### Requirement: 文件搬运器
系统 SHALL 实现安全的文件移动和重命名。

搬运器 SHALL：
- 复制阶段：使用 .copying 后缀标记正在复制的文件，复制完成后重命名去掉后缀
- 启动时清理残留 .copying 文件
- 移动前检查磁盘空间（不足则通知并暂停）
- 入库目录不存在时自动创建（含父目录）
- 跨设备移动失败时自动降级为"复制+删除"
- 处理完成后删除源文件（在网盘挂载目录上）

#### Scenario: 磁盘空间不足
- **WHEN** 复制或移动前检测到目标磁盘剩余空间 < 文件大小 * 1.5
- **THEN** 任务标记 FAILED（错误码 3003）
- **AND** 队列自动暂停
- **AND** 通知 Hermes

### Requirement: Hermes 通知模块
系统 SHALL 通过 Webhook 主动通知 Hermes。

通知模块 SHALL：
- 根据 hermes.webhook.events 配置决定哪些事件需要通知
- 发送 POST 到 hermes.http.base_url + /webhooks/{route_name}
- 使用 HMAC-SHA256 签名（如配置了 secret）
- 失败时重试 max_retries 次（间隔 retry_delay 秒）
- 重试仍失败记录错误日志但不中断主流程

#### Scenario: 任务完成通知
- **WHEN** 任务状态变为 SUCCESS
- **THEN** 发送 event_type=task_complete，含 scraped_info 和 import_path

#### Scenario: 批量任务完成通知
- **WHEN** 所有 PENDING 任务处理完毕
- **THEN** 发送 event_type=batch_complete，含汇总统计

### Requirement: 健康检查
系统 SHALL 提供完整的健康检查能力。

检查项：
1. source_dir — 目录存在且可读
2. temp_dir — 目录存在且可写
3. import_dirs — path_rules 中所有基础路径可访问
4. llm_api — 发送一个最小测试请求（或检查配置有效性）
5. hermes — HTTP 连接到 hermes base_url 可达
6. disk_space — 计算临时目录和入库目录所在磁盘的剩余空间

健康状态：
- healthy — 所有检查通过
- degraded — 部分非关键检查失败（如 hermes 不可达）
- unhealthy — 关键检查失败（如 source_dir 不可访问）

### Requirement: 指标统计
系统 SHALL 追踪并提供运行指标。

指标内容：
- total_tasks / success_tasks / failed_tasks / skipped_tasks
- success_rate（小数）
- avg_processing_time_seconds
- total_llm_calls / llm_failures
- current_queue_pending / current_queue_processing
- uptime

### Requirement: 结构化日志
系统 SHALL 输出结构化日志，支持 JSON 和纯文本两种格式。

日志 SHALL：
- 按 logging.level 过滤
- 按 logging.format 输出（json 或 text）
- 轮转策略：单个文件达 max_size_mb 后轮转，保留 backup_count 个备份
- 步骤日志（step log）记录在任务记录中

### Requirement: 项目依赖
系统 SHALL 最小化外部依赖。

**唯一必须依赖：** `pyyaml>=6.0`

**可选依赖：** `watchdog>=4.0`（文件监控，可用轮询替代）

所有其他功能使用 Python 3.8+ 标准库：http.server、json、argparse、os、shutil、pathlib、logging、uuid、urllib、hashlib、hmac、threading、time

### Requirement: 部署方案
系统 SHALL 提供 systemd 服务作为推荐部署方式。

部署步骤：
1. 创建 Python 虚拟环境
2. `pip install pyyaml`
3. 编辑 config.yaml
4. 创建 systemd unit 文件
5. 启用并启动服务

备选方案：PyInstaller 打包为独立可执行文件。

### Requirement: 项目目录结构
系统 SHALL 按以下结构组织代码：

```
media_importer/
├── media_importer.py         # 主入口（CLI + HTTP 服务启动）
├── config.yaml               # 默认配置模板
├── config_loader.py          # 配置加载、校验、默认值
├── file_scanner.py           # 文件扫描和分组
├── file_copier.py            # 文件复制（含断点续传）
├── llm_scraper.py            # AI 刮削引擎
├── classifier.py             # 分类规则匹配
├── dedup_checker.py          # 同名检测
├── file_mover.py             # 文件重命名和移动
├── task_manager.py           # 任务队列持久化和状态管理
├── hermes_hook.py            # Hermes Webhook 通知
├── safety.py                 # 安全检查模块
├── file_watcher.py           # 文件监控模块
├── api_server.py             # HTTP API 路由和处理
├── logger.py                 # 结构化日志
├── hooks.py                  # 脚本钩子
├── metrics.py                # 指标统计
├── tests/
│   ├── test_file_scanner.py
│   ├── test_llm_scraper.py
│   ├── test_classifier.py
│   ├── test_dedup_checker.py
│   ├── test_file_copier.py
│   ├── test_file_mover.py
│   └── test_task_manager.py
├── logs/                     # 运行期生成
├── tasks.json                # 运行期生成
└── requirements.txt
```
