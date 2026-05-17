# Checklist

## Phase 1: 项目基础设施
- [ ] Task 1: 项目骨架
  - [ ] media_importer/ 目录结构完整且符合 spec 定义
  - [ ] `python media_importer.py --help` 显示所有子命令
  - [ ] config.yaml 包含 12 个配置段落且格式正确
- [ ] Task 2: 配置加载
  - [ ] 有效 YAML 文件加载成功
  - [ ] 损坏的 YAML 文件输出明确错误
  - [ ] 缺少 config.yaml 时生成默认配置模板
  - [ ] 敏感字段（api_key、secret）脱敏输出
- [ ] Task 3: 日志模块
  - [ ] JSON 格式日志输出正确
  - [ ] 纯文本格式日志输出易读
  - [ ] 日志级别过滤生效
  - [ ] 文件轮转功能正常（大小触发）
- [ ] Task 4: 指标统计
  - [ ] 计数器正确累加
  - [ ] 平均处理时间计算准确
  - [ ] uptime 追踪正常

## Phase 2: 核心业务模块
- [ ] Task 5: 文件扫描器
  - [ ] 递归扫描覆盖所有子目录
  - [ ] max_depth 限制生效
  - [ ] 视频和字幕正确按扩展名过滤
  - [ ] ignore_patterns 排除生效
  - [ ] 视频-字幕分组正确（基于文件名前缀）
- [ ] Task 6: AI 刮削引擎
  - [ ] Prompt 根据 dimensions 配置动态生成
  - [ ] OpenAI 兼容 API 调用成功
  - [ ] 响应 JSON 解析正确
  - [ ] dimensions 值在配置范围内验证通过
  - [ ] 无效 JSON 响应触发重试
  - [ ] 超时触发重试
  - [ ] fallback_model 降级生效
  - [ ] 低置信度标记 low_confidence_warning
- [ ] Task 7: 分类匹配器
  - [ ] path_rules 按顺序匹配
  - [ ] 多 conditions AND 逻辑正确
  - [ ] 不匹配时使用兜底规则
  - [ ] 模板变量全部替换为实际值
- [ ] Task 8: 同名检测
  - [ ] 年份 + title_cn 匹配检测正确
  - [ ] 年份 + title_en 匹配检测正确
  - [ ] 电视剧 season + episode 检测正确
  - [ ] strategy=skip 返回建议跳过
  - [ ] strategy=rename 返回重命名建议
- [ ] Task 9: 文件复制器
  - [ ] 复制到临时目录成功
  - [ ] 关联字幕同时复制
  - [ ] .copying 标记文件机制正常
  - [ ] 启动时清理残留 .copying 文件
  - [ ] 磁盘空间不足时正确阻断
  - [ ] 复制进度回调数据正确
- [ ] Task 10: 文件搬运器
  - [ ] filename_templates 变量替换正确
  - [ ] 入库目录自动创建
  - [ ] 跨设备移动降级为复制+删除
  - [ ] 源文件处理后被删除

## Phase 3: 任务调度
- [ ] Task 11: 任务管理器
  - [ ] 任务 JSON 序列化/反序列化正确
  - [ ] 状态机转换合规（PENDING→PROCESSING→SUCCESS/FAILED/SKIPPED）
  - [ ] FAILED→PENDING 重试路径正常
  - [ ] FIFO 队列顺序执行
  - [ ] 任务清除按状态过滤正确
  - [ ] 进度追踪（step/percentage）正确
  - [ ] 历史任务按 retention_days 清理
- [ ] Task 12: 任务调度器
  - [ ] 9 步流水线完整执行
  - [ ] 每步完成后日志记录
  - [ ] 失败步骤正确标记并通知
  - [ ] 队列暂停/恢复控制
  - [ ] 文件监控轮询正常工作

## Phase 4: 通知与钩子
- [ ] Task 13: Hermes 通知模块
  - [ ] Webhook POST 格式符合 Hermes 规范
  - [ ] HMAC-SHA256 签名正确
  - [ ] 通知失败重试机制正常
  - [ ] 事件过滤按配置生效
  - [ ] task_complete payload 完整
  - [ ] task_failed payload 含错误信息
  - [ ] task_skipped payload 合同名原因
  - [ ] batch_complete payload 含汇总
- [ ] Task 14: 钩子系统
  - [ ] before_process 正确调用
  - [ ] after_success 正确调用
  - [ ] after_failure 正确调用
  - [ ] 钩子失败不中断主流程

## Phase 5: API 服务
- [ ] Task 15: HTTP API
  - [ ] 16 个端点全部响应正常
  - [ ] 统一 JSON 响应格式 {code, message, data}
  - [ ] 错误码与 spec 一致
  - [ ] 请求参数解析正确
  - [ ] 线程安全（多请求并发无数据竞争）
  - [ ] POST /api/run 触发扫描和处理
  - [ ] GET /api/tasks/{id} 包含 progress 字段
  - [ ] GET /api/health 返回6项检查结果
  - [ ] GET /api/metrics 返回指标数据
  - [ ] POST /api/config/reload 重新加载配置

## Phase 6: 测试
- [ ] Task 16: 单元测试
  - [ ] 所有单元测试通过
  - [ ] 测试覆盖率 ≥ 70%
- [ ] Task 17: 集成测试
  - [ ] 端到端流程测试通过
  - [ ] 异常场景覆盖：复制中断/AI失败/同名跳过/磁盘满
  - [ ] HTTP API 端点测试通过
  - [ ] 配置文件兼容性验证通过

## Phase 7: 部署
- [ ] Task 18: 部署配置
  - [ ] systemd unit 文件可用
  - [ ] PyInstaller 打包成功
  - [ ] 安装说明清晰完整
