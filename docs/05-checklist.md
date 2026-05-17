---
title: "NAS影视自动化入库系统"
type: checklist
date: 2026-05-17
prev: docs/04-tasks.md
next: docs/06-test-guide.md
---

# NAS影视自动化入库系统 — 验收清单

## Phase 1: 项目基础设施
- [x] Task 1: 项目骨架
  - [x] media_importer/ 目录结构完整且符合 spec 定义
  - [x] `python media_importer.py --help` 显示所有子命令
  - [x] config.yaml 包含 12 个配置段落且格式正确
- [x] Task 2: 配置加载
  - [x] 有效 YAML 文件加载成功
  - [x] 损坏的 YAML 文件输出明确错误
  - [x] 缺少 config.yaml 时生成默认配置模板
  - [x] 敏感字段（api_key、secret）脱敏输出
- [x] Task 3: 日志模块
  - [x] JSON 格式日志输出正确
  - [x] 纯文本格式日志输出易读
  - [x] 日志级别过滤生效
  - [x] 文件轮转功能正常（大小触发）
- [x] Task 4: 指标统计
  - [x] 计数器正确累加
  - [x] 平均处理时间计算准确
  - [x] uptime 追踪正常

## Phase 2: 核心业务模块
- [x] Task 5: 文件扫描器
  - [x] 递归扫描覆盖所有子目录
  - [x] max_depth 限制生效
  - [x] 视频和字幕正确按扩展名过滤
  - [x] ignore_patterns 排除生效
  - [x] 视频-字幕分组正确（基于文件名前缀）
- [x] Task 6: AI 刮削引擎
  - [x] Prompt 根据 dimensions 配置动态生成
  - [x] OpenAI 兼容 API 调用成功
  - [x] 响应 JSON 解析正确
  - [x] dimensions 值在配置范围内验证通过
  - [x] 无效 JSON 响应触发重试
  - [x] 超时触发重试
  - [x] fallback_model 降级生效
  - [x] 低置信度标记 low_confidence_warning
- [x] Task 7: 分类匹配器
  - [x] path_rules 按顺序匹配
  - [x] 多 conditions AND 逻辑正确
  - [x] 不匹配时使用兜底规则
  - [x] 模板变量全部替换为实际值
- [x] Task 8: 同名检测
  - [x] 年份 + title_cn 匹配检测正确
  - [x] 年份 + title_en 匹配检测正确
  - [x] 电视剧 season + episode 检测正确
  - [x] strategy=skip 返回建议跳过
  - [x] strategy=rename 返回重命名建议
- [x] Task 9: 文件复制器
  - [x] 复制到临时目录成功
  - [x] 关联字幕同时复制
  - [x] .copying 标记文件机制正常
  - [x] 启动时清理残留 .copying 文件
  - [x] 磁盘空间不足时正确阻断
  - [x] 复制进度回调数据正确
- [x] Task 10: 文件搬运器
  - [x] filename_templates 变量替换正确
  - [x] 入库目录自动创建
  - [x] 跨设备移动降级为复制+删除
  - [x] 源文件处理后被删除

## Phase 3: 任务调度
- [x] Task 11: 任务管理器
  - [x] 任务 JSON 序列化/反序列化正确
  - [x] 状态机转换合规（PENDING→PROCESSING→SUCCESS/FAILED/SKIPPED）
  - [x] FAILED→PENDING 重试路径正常
  - [x] FIFO 队列顺序执行
  - [x] 任务清除按状态过滤正确
  - [x] 进度追踪（step/percentage）正确
  - [x] 历史任务按 retention_days 清理
- [x] Task 12: 任务调度器
  - [x] 9 步流水线完整执行
  - [x] 每步完成后日志记录
  - [x] 失败步骤正确标记并通知
  - [x] 队列暂停/恢复控制
  - [x] 文件监控轮询正常工作

## Phase 4: 通知与钩子
- [x] Task 13: Hermes 通知模块
  - [x] Webhook POST 格式符合 Hermes 规范
  - [x] HMAC-SHA256 签名正确
  - [x] 通知失败重试机制正常
  - [x] 事件过滤按配置生效
  - [x] task_complete payload 完整
  - [x] task_failed payload 含错误信息
  - [x] task_skipped payload 合同名原因
  - [x] batch_complete payload 含汇总
  - [x] Hermes Webhook 路由配置正确（飞书 chat_id 已指定）
  - [x] Hermes Skill 加载正常，api_url 配置生效
  - [x] Webhook 测试通知送达飞书（已手动验证）
- [x] Task 14: 钩子系统
  - [x] before_process 正确调用
  - [x] after_success 正确调用
  - [x] after_failure 正确调用
  - [x] 钩子失败不中断主流程

## Phase 5: API 服务
- [x] Task 15: HTTP API
  - [x] 13 个端点全部响应正常（见下方列表）
  - [x] 统一 JSON 响应格式 {code, status, message, data}
  - [x] 错误码与 spec 一致（200/202/400/404/500）
  - [x] 请求参数解析正确
  - [x] 线程安全（多请求并发无数据竞争）
  - [x] POST /api/run 触发批量处理（后台执行）
  - [x] POST /api/run/file 处理指定文件
  - [x] GET /api/tasks 任务列表（支持 status/limit/offset）
  - [x] GET /api/tasks/{id} 包含 progress 字段
  - [x] POST /api/tasks/{id}/retry 重试失败任务
  - [x] DELETE /api/tasks/{id} 删除任务
  - [x] POST /api/tasks/clear 清空任务
  - [x] POST /api/queue/pause 暂停队列
  - [x] POST /api/queue/resume 恢复队列
  - [x] POST /api/queue/retry-all 重试所有失败
  - [x] GET /api/queue/status 队列状态
  - [x] GET /api/health 返回6项检查结果
  - [x] GET /api/metrics 返回指标数据
  - [x] GET /api/config 返回配置（脱敏）
  - [x] POST /api/config/reload 重新加载配置
  - [x] GET /api/logs 查询日志
  - [x] CLI 命令全部实现（serve/run/list/show/retry/queue/clear/log/health/metrics/config）
  - [x] HTTP API 集成测试通过（19/19）

## Phase 6: 测试
- [x] Task 16: 单元测试
  - [x] 所有单元测试通过（197/197）
  - [ ] 测试覆盖率 ≥ 70%
- [x] Task 17: 集成测试
  - [x] 端到端流程测试通过（10/10）
  - [x] HTTP API 端点测试通过（19/19）
  - [x] 异常场景覆盖：复制中断/AI失败/同名跳过/磁盘满
  - [x] 配置文件兼容性验证通过

## Phase 7: 部署
- [x] Task 18: 部署配置
  - [x] systemd unit 文件可用
  - [x] 安装脚本 (deploy/install.sh)
