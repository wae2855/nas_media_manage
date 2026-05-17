# Tasks

## Phase 1: 项目基础设施

- [ ] Task 1: 创建项目骨架和依赖管理
  - [ ] 创建 media_importer/ 目录结构
  - [ ] 编写 requirements.txt（仅 pyyaml）
  - [ ] 编写 media_importer.py 主入口骨架（argparse 子命令框架：serve/run/list/show/retry/queue/clear/log/health/metrics/config）
  - [ ] 编写 config.yaml 默认配置模板

- [ ] Task 2: 配置加载与校验模块（config_loader.py）
  - [ ] 实现 YAML 文件加载
  - [ ] 实现 12 个配置段落的完整性校验
  - [ ] 实现配置缺失时自动生成默认配置模板
  - [ ] 实现 dimensions.values 与 AI 返回值的交叉校验函数
  - [ ] 实现对敏感字段（api_key、secret）的脱敏输出

- [ ] Task 3: 结构化日志模块（logger.py）
  - [ ] 实现 JSON 格式和 text 格式两种输出
  - [ ] 实现按日志级别过滤
  - [ ] 实现文件轮转（大小触发 + backup_count）
  - [ ] 实现步骤日志记录（用于任务记录的 logs 数组）

- [ ] Task 4: 指标统计模块（metrics.py）
  - [ ] 实现任务计数器（total/success/failed/skipped）
  - [ ] 实现平均处理时间计算
  - [ ] 实现 LLM 调用统计（total_calls/failures）
  - [ ] 实现队列状态统计
  - [ ] 实现 uptime 追踪
  - [ ] 提供 to_dict() 方法供 HTTP API 使用

## Phase 2: 核心业务模块

- [ ] Task 5: 文件扫描器（file_scanner.py）
  - [ ] 实现递归扫描源目录
  - [ ] 实现 max_depth 深度限制
  - [ ] 实现按 video_extensions / subtitle_extensions 过滤
  - [ ] 实现 ignore_patterns 排除（glob 匹配）
  - [ ] 实现视频和字幕按文件名前缀分组
  - [ ] 返回分组列表供调度器使用

- [ ] Task 6: AI 刮削引擎（llm_scraper.py）
  - [ ] 实现根据 dimensions 配置动态构建 system prompt
  - [ ] 实现动态构建 JSON Schema（期望响应格式）
  - [ ] 实现 OpenAI 兼容 API 调用（使用 urllib.request）
  - [ ] 实现响应 JSON 解析和校验
  - [ ] 实现 dimensions 值范围验证（必须在配置的 values 内）
  - [ ] 实现 max_retries 重试机制（间隔 retry_delay）
  - [ ] 实现 fallback_model 降级
  - [ ] 实现 confidence < threshold 时设置 low_confidence_warning
  - [ ] 实现请求/响应日志记录

- [ ] Task 7: 分类匹配器（classifier.py）
  - [ ] 实现 path_rules 逐条匹配逻辑
  - [ ] 实现 conditions 中所有 key-value 的 AND 匹配
  - [ ] 实现兜底规则（conditions: {}）
  - [ ] 实现模板变量替换（{title_cn}、{year}、{season}、{dimension.xxx} 等）
  - [ ] 返回生成的入库路径

- [ ] Task 8: 同名检测模块（dedup_checker.py）
  - [ ] 实现同名定义判断（年份 + title_cn/title_en 匹配，电视剧加 season + episode）
  - [ ] 实现入库目录文件扫描和比对
  - [ ] 实现标题比较（忽略大小写和常见标点符号）
  - [ ] 实现 strategy 处理：skip（跳过）、overwrite（覆盖）、rename（序号重命名）
  - [ ] 返回检测结果和建议处理方式

- [ ] Task 9: 文件复制器（file_copier.py）
  - [ ] 实现视频文件从源目录复制到临时目录
  - [ ] 实现关联字幕文件同时复制
  - [ ] 实现 .copying 临时标记文件机制（复制中标记，完成后重命名）
  - [ ] 实现启动时清理残留 .copying 文件
  - [ ] 实现复制前磁盘空间检查（目标剩余 < 文件大小 * 1.5 则失败）
  - [ ] 实现复制进度回调（已复制字节数/总字节数）
  - [ ] 实现网络中断后的断点续传（检测 .copying 文件大小，从断点继续）

- [ ] Task 10: 文件搬运器（file_mover.py）
  - [ ] 实现应用 filename_templates 生成最终文件名
  - [ ] 实现影视文件名变量替换（{title_cn}/{title_en}/{year}/{resolution}/{quality}/{season}/{episode}）
  - [ ] 实现字幕文件名变量替换（{video_filename}/{lang}/{ext}）
  - [ ] 实现入库目录自动创建（os.makedirs，含父目录）
  - [ ] 实现文件移动（先尝试 os.rename，失败降级为 shutil.copy2 + os.remove）
  - [ ] 实现移动后删除源文件
  - [ ] 实现移动前磁盘空间检查

## Phase 3: 任务调度

- [ ] Task 11: 任务管理器（task_manager.py）
  - [ ] 实现 Task 数据类（task_id、状态、时间戳、刮削结果、错误信息、日志）
  - [ ] 实现 tasks.json 读写（JSON 序列化/反序列化）
  - [ ] 实现任务状态机（PENDING → PROCESSING → SUCCESS/FAILED/SKIPPED）
  - [ ] 实现 FIFO 队列（取下一个 PENDING 任务）
  - [ ] 实现任务重试（重置为 PENDING）
  - [ ] 实现任务清除（按状态过滤，标记 DELETED）
  - [ ] 实现历史任务保留（按 history_retention_days 清理）
  - [ ] 实现任务进度追踪（current_step、total_steps、step_name、percentage）
  - [ ] 实现复制进度更新（bytes_copied / total_bytes）
  - [ ] 实现任务列表查询（支持 status/limit/offset 参数）
  - [ ] 实现启动时加载未完成任务

- [ ] Task 12: 任务调度器（集成在 task_manager.py 或独立模块）
  - [ ] 实现9步流水线编排（扫描→复制→刮削→分类→同名检测→命名→入库→通知→记录）
  - [ ] 实现每步完成/失败的状态更新和日志记录
  - [ ] 实现队列暂停/恢复控制
  - [ ] 实现顺序执行保证（同一时间仅一个 PROCESSING）
  - [ ] 实现文件监控轮询（configurable poll_interval）

## Phase 4: 通知与钩子

- [ ] Task 13: Hermes 通知模块（notifier.py）
  - [ ] 实现 Webhook POST 请求构建
  - [ ] 实现 HMAC-SHA256 签名（如配置 secret）
  - [ ] 实现重试机制（max_retries + retry_delay）
  - [ ] 实现事件过滤（按 hermes.webhook.events 配置决定是否发送）
  - [ ] 实现 4 种事件类型的 payload 构建：
    - task_complete（含 scraped_info、import_path）
    - task_failed（含 error_code、error_message）
    - task_skipped（含 existing_file、reason）
    - batch_complete（含汇总统计）
  - [ ] 实现通知失败不中断主流程

- [ ] Task 14: 钩子系统（hooks.py）
  - [ ] 实现 before_process 钩子（处理前执行）
  - [ ] 实现 after_success 钩子（成功后执行）
  - [ ] 实现 after_failure 钩子（失败后执行）
  - [ ] 使用 subprocess 调用外部脚本
  - [ ] 钩子执行失败记录日志但不中断主流程

## Phase 5: API 服务

- [ ] Task 15: HTTP API 服务（api_server.py）
  - [ ] 基于 http.server 实现 HTTP 服务
  - [ ] 实现路由分发（method + path 匹配）
  - [ ] 实现统一 JSON 响应格式（{code, message, data}）
  - [ ] 实现 16 个 API 端点：
    - [ ] POST /api/run — 扫描并处理所有文件
    - [ ] POST /api/run/file — 处理指定文件
    - [ ] GET /api/tasks — 任务列表（status/limit/offset 分页）
    - [ ] GET /api/tasks/{task_id} — 任务详情（含 progress）
    - [ ] POST /api/tasks/{task_id}/retry — 重试任务
    - [ ] DELETE /api/tasks/{task_id} — 删除任务
    - [ ] POST /api/tasks/clear — 按状态清空任务
    - [ ] POST /api/queue/pause — 暂停队列
    - [ ] POST /api/queue/resume — 恢复队列
    - [ ] GET /api/queue/status — 队列状态
    - [ ] GET /api/config — 当前配置（脱敏）
    - [ ] POST /api/config/reload — 重新加载配置
    - [ ] GET /api/health — 健康检查
    - [ ] GET /api/metrics — 指标统计
    - [ ] GET /api/logs — 日志查询（limit/level/task_id）
  - [ ] 实现请求参数解析（query string + JSON body）
  - [ ] 实现线程安全（共享 task_manager 实例）
  - [ ] 实现后台文件监控线程（自动扫描和入队）

## Phase 6: 测试

- [ ] Task 16: 单元测试
  - [ ] test_config_loader.py — 配置加载/校验/脱敏/默认值
  - [ ] test_file_scanner.py — 文件扫描/过滤/分组/忽略模式
  - [ ] test_llm_scraper.py — prompt 构建/响应解析/重试/降级/置信度
  - [ ] test_classifier.py — path_rules 匹配/模板替换/兜底规则
  - [ ] test_dedup_checker.py — 同名判断/skip/rename 策略
  - [ ] test_file_copier.py — 复制/.copying标记/断点检测/空间检查
  - [ ] test_file_mover.py — 重命名/目录创建/跨设备移动
  - [ ] test_task_manager.py — 状态机/持久化/FIFO队列/重试/清除

- [ ] Task 17: 集成测试
  - [ ] 完整9步流程端到端测试（mock LLM API）
  - [ ] 异常场景测试（复制中断恢复、AI失败、同名跳过、磁盘满）
  - [ ] HTTP API 端点测试
  - [ ] 配置文件兼容性测试

## Phase 7: 部署与文档

- [ ] Task 18: 部署配置
  - [ ] 编写 systemd unit 文件模板（media-importer.service）
  - [ ] 编写 PyInstaller 打包脚本
  - [ ] 编写 Dockerfile（备选）
  - [ ] 编写安装说明（README 中，包含 FNOS 特殊注意事项）

## Task Dependencies

```
Phase 1 (基础设施)
  Task 1 → Task 2, Task 3, Task 4

Phase 2 (核心业务)
  Task 2 → Task 5, Task 6, Task 7, Task 8, Task 9, Task 10
  Task 5, Task 6, Task 7, Task 8, Task 9, Task 10 之间无依赖，可并行

Phase 3 (任务调度)
  Task 2, Task 5, Task 6, Task 7, Task 8, Task 9, Task 10 → Task 11
  Task 11 → Task 12

Phase 4 (通知与钩子)
  Task 11 → Task 13, Task 14
  Task 13, Task 14 之间无依赖，可并行

Phase 5 (API 服务)
  Task 12, Task 13, Task 14 → Task 15

Phase 6 (测试)
  Task 15 → Task 16, Task 17
  Task 16, Task 17 之间无依赖，可并行

Phase 7 (部署)
  Task 15 → Task 18
```
