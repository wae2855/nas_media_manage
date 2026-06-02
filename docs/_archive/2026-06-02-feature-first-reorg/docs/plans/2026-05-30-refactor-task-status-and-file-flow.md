---
title: "refactor: 任务状态模型与文件流转重构"
type: plan
date: 2026-05-30
status: complete
confidence: high
---

## 问题陈述

6 状态模型语义不清、FAILED 自动移源文件剥夺用户决策权、临时文件处理不一致、删除任务无安全网、回收站无过期、配置设计混合了任务流和源目录清理两个独立关注点。详见 [方案文档](../方案/任务状态模型与文件流转重构.md)。

## 目标终态

1. 前端展示 4 业务状态（待处理/处理中/失败/完成），技术状态作为内部子状态保留
2. FAILED 时源文件保留在源目录，等用户决策
3. 临时文件统一规则：非处理中状态一律 rm 删除，不入回收站
4. 删除任务时关联文件移入回收站而非直接删除
5. 回收站有过期自动清理机制
6. 配置简化：`cleanup_source_after_done` 布尔值替代 `cleanup_mode`+`delete_source_after_import`
7. 源目录清理器独立为 `source_cleaner` 配置段，与任务流解耦
8. 所有架构文档、测试用例文档对齐新模型

## 范围与非目标

**范围内**：
- 后端：runner.py FAILED 分支、task_handlers.py 忽略/删除逻辑、配置重构、回收站过期、源目录清理器
- 前端：4 业务状态展示、状态筛选分组、配置页面改造
- 文档：6 份架构文档 + 1 份测试用例文档更新
- 配置：新增 cleanup_source_after_done / recycle_retention_days / source_cleaner

**非目标**：
- 不改变 DB 中存储的技术状态值
- 不改变 API 接口中的 status 字段值
- 不改变刮削/分类/去重等核心处理逻辑
- 源目录清理器 AI 辅助判断后续迭代

## 实施任务

### Phase 1：配置重构（优先级 P0，其他任务依赖此阶段）

- [ ] 1.1 修改 `core/config_loader.py`：
  - 新增 `cleanup_source_after_done` 默认 true（从旧 cleanup_mode+delete_source_after_import 迁移）
  - 新增 `recycle_retention_days` 默认 30
  - 新增顶层 `source_cleaner` 配置段（从 source_policy.smart_cleanup 迁移）
  - 保留旧配置读取兼容（自动迁移到新配置）
- [ ] 1.2 修改 `core/config_validator.py`：
  - 新增 cleanup_source_after_done / recycle_retention_days / source_cleaner 校验
  - 旧配置项标记为 deprecated 但仍接受
- [ ] 1.3 修改 `api/config_handlers.py`：
  - 新增配置项读写
  - 返回新配置结构（旧字段兼容返回）
- [ ] 1.4 更新 `config.yaml.example`：
  - 新配置结构示例
  - 旧配置注释说明迁移

### Phase 2：后端核心逻辑（优先级 P0）

- [ ] 2.1 修改 `pipeline/steps.py` import 步骤：
  - 源文件清理逻辑改为读 `cleanup_source_after_done`
  - true → move_to_recycle_with_companions
  - false → 保留源目录
  - 移除 cleanup_mode 分支判断
- [ ] 2.2 修改 `pipeline/runner.py`：
  - FAILED 分支不再自动移源文件入回收站，仅清理临时文件，file_location 保持 "source"
  - run_all 预清理逻辑：移除 smart_cleanup 分支，full_cleanup 预清理移到 source_cleaner
- [ ] 2.3 修改 `api/task_handlers.py` `_task_ignore`：
  - file_location=temp → 临时文件 rm 删除 + 源文件按 cleanup_source_after_done 处理
  - file_location=source → 源文件按 cleanup_source_after_done 处理
  - 不再将临时文件移入回收站
- [ ] 2.4 修改 `api/task_handlers.py` `_delete_task`：
  - delete_files=True + file_location=source → move_to_recycle()
  - delete_files=True + file_location=temp → rm 删除
  - delete_files=True + file_location=import → move_to_recycle()
  - delete_files=True + file_location=recycle → 不动
- [ ] 2.5 新增 `core/safety.py` `recycle_cleanup()` 函数：
  - 扫描回收站目录
  - 读取 .meta 侧车文件获取移入时间
  - 删除超期文件+.meta
- [ ] 2.6 修改 `monitor/file_watcher.py`：
  - 轮询中增加回收站过期清理调用
- [ ] 2.7 新增 `storage/source_cleaner.py`：
  - 源目录清理器独立模块
  - 两级清理模式：keep_media_only / keep_media_related
  - 规则引擎：后缀名删除/保护 + 黑名单模式 + 垃圾视频检测(size阈值)
  - AI 辅助判断（可选，规则+AI联合，规则优先）
  - 清理记录生成（路径+分类+原因+回收站路径）
  - 清理文件统一移入回收站，不直接删除
- [ ] 2.8 新增 `core/db/cleaner_repo.py`：
  - 清理记录表(cleaner_records)建表
  - 清理记录 CRUD 操作
- [ ] 2.9 新增 `api/source_cleaner_handlers.py`：
  - GET /api/source-cleaner/preview：预览清理列表
  - GET /api/source-cleaner/records：查询历史清理记录
  - POST /api/source-cleaner/execute：执行清理
  - GET /api/source-cleaner/status：清理器状态
- [ ] 2.10 修改 `api/handler.py`：注册 source_cleaner 路由
- [ ] 2.11 修改 `monitor/file_watcher.py`：
  - 源目录清理器定时触发（按 schedule 配置）
  - 清理完成后 Hermes 通知

### Phase 3：前端改造（优先级 P1）

- [ ] 3.1 修改 `webui/js/tasks.js` `getStatusText()`：4 业务状态映射
  - PENDING → "待处理"
  - PROCESSING → "处理中"
  - CONFIRMING → "处理中 · 需确认"
  - FAILED → "失败"
  - SUCCESS → "完成"
  - SKIPPED → "完成 · 跳过"
- [ ] 3.2 修改 `webui/js/tasks.js` 状态筛选：改为 4 组
  - 待处理(PENDING) / 处理中(PROCESSING+CONFIRMING) / 失败(FAILED) / 完成(SUCCESS+SKIPPED)
- [ ] 3.3 修改 `webui/js/tasks.js` `showDeleteConfirm()`：提示文案改为"移入回收站"
- [ ] 3.4 修改 `webui/js/config.js`：
  - 新增 recycle_retention_days 输入框（说明"超期文件将永久删除"）
  - cleanup_source_after_done 开关（说明"仅清理创建任务的视频和字幕文件"）
  - source_cleaner 配置区域：
    - 清理模式两个选项按钮（①仅保留影视+字幕 ②保留影视+字幕+相关文件）
    - AI辅助勾选框（说明"规则+AI联合判断"）
    - 高级配置折叠区（垃圾视频阈值、删除/保护后缀名、黑名单）
    - 清理记录查看区
    - 清理预览按钮
- [ ] 3.5 修改 `webui/index.html`：状态筛选下拉+配置页面+清理器页面

### Phase 4：文档更新（优先级 P1）

- [ ] 4.1 更新 `docs/系统架构总览.md`：状态模型+文件流转+配置参考
- [ ] 4.2 更新 `docs/架构/任务管理.md`：状态机改为 4 状态模型
- [ ] 4.3 更新 `docs/架构/流水线处理.md`：步骤说明+数据流对齐
- [ ] 4.4 更新 `docs/架构/配置系统.md`：配置重构（废弃项+新增项）
- [ ] 4.5 更新 `docs/架构/文件操作.md`：文件流转+源目录清理器
- [ ] 4.6 更新 `docs/测试/文件处理端到端测试用例.md`：对齐 4 状态+新配置

### Phase 5：测试验证（优先级 P0）

- [ ] 5.1 更新 `tests/test_e2e_file_processing.py`：对齐新配置名和行为
- [ ] 5.2 新增测试：FAILED 时源文件保留在源目录
- [ ] 5.3 新增测试：忽略时临时文件 rm + 源文件按 cleanup_source_after_done 处理
- [ ] 5.4 新增测试：删除任务时文件移入回收站
- [ ] 5.5 新增测试：回收站过期清理功能
- [ ] 5.6 新增测试：配置迁移（旧 cleanup_mode → 新 cleanup_source_after_done）
- [ ] 5.7 新增测试：源目录清理器规则引擎（两级模式+后缀名+黑名单+垃圾视频检测）
- [ ] 5.8 新增测试：源目录清理器 API（preview/records/execute/status）
- [ ] 5.9 新增测试：源目录清理器 AI 辅助判断
- [ ] 5.10 运行完整测试套件，确保无回归

## 验收标准

1. FAILED 任务源文件保留在源目录，不自动移入回收站
2. 忽略操作：临时文件 rm 删除，源文件按 cleanup_source_after_done 处理
3. 删除任务：关联文件移入回收站，不直接删除
4. 前端展示 4 业务状态，CONFIRMING 显示为"处理中 · 需确认"
5. 回收站过期清理功能正常工作
6. 配置迁移：旧 cleanup_mode/delete_source_after_import 自动转为新配置
7. 源目录清理器作为独立功能可启用/禁用
8. 源目录清理器支持两级模式（keep_media_only / keep_media_related）
9. 源目录清理器支持规则+AI联合判断
10. 清理记录 API 可查看清理路径清单和详细信息
11. 清理文件统一移入回收站，不直接删除
12. 所有现有测试通过，无回归
13. 所有架构文档和测试用例文档已对齐

## 决策理由

- **cleanup_source_after_done 布尔值**：任务完成后源文件处理本质是二选一，3 值枚举增加了不必要的复杂度
- **源目录清理器独立**：与任务流是完全不同的关注点，耦合在一起导致配置混乱和代码分支复杂
- **保留技术状态值不变**：避免数据迁移和 API 破坏性变更，4 状态是前端展示层映射
- **临时文件不入回收站**：临时文件是工作副本，源文件仍在源目录，入回收站增加存储负担
- **FAILED 不自动移源文件**：用户可能想重试，自动移走打断工作流
- **删除任务用回收站**：安全网原则，误操作可恢复

## 风险分析

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 配置迁移兼容性 | 中 | 高 | config_loader 自动迁移旧配置，保留旧字段读取兼容 |
| 前端状态筛选兼容性 | 中 | 低 | API 返回技术状态，前端做分组映射 |
| FAILED 源文件保留导致源目录积压 | 低 | 中 | 忽略操作触发 cleanup_source_after_done 清理 |
| 回收站过期误删 | 低 | 高 | 默认 30 天；.meta 记录来源；首次上线可设 0 |
| 源目录清理器误删文件 | 中 | 高 | confirm_before_cleanup 默认 true；清理移入回收站不直接删除 |
