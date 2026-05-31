---
title: "refactor: 源目录清理器重构"
type: plan
date: 2026-05-29
status: complete
brainstorm: docs/方案/源目录清理器重构方案.md
confidence: high
---

# 源目录清理器重构实施计划

## 问题陈述

当前 `SourceCleaner` 实现存在后缀名体系分裂、AI 分类空壳、文件夹处理不完整、回收站不支持目录、权限检测缺失等问题，需要重构。

## 目标终态

1. 清理器与扫描器共享全局后缀名定义
2. AI 以目录为单位整体分析，与规则结果按用户选择的合并策略合并
3. 所有删除操作统一走回收站（包括目录），回收站按来源分区
4. 清理器启用时 source_dir 权限检测升级为读写
5. 前端配置面板完整可用，高级配置不再有交互 bug

## 范围与非目标

**范围内**：source_cleaner.py 重构、safety.py 回收站扩展（含浏览/恢复）、permission_checker.py 权限检测、前端配置面板重构、回收站 Tab

**非目标**：不改动任务流（pipeline/steps.py）的清理逻辑；不改动扫描器核心逻辑；不引入新依赖

## 实施任务

### Phase 1: 回收站结构重构

- [ ] 1.1 `safety.py`: 新增 `move_dir_to_recycle()` 函数，支持目录整体移入回收站，创建 `.dir.meta` 元信息
- [ ] 1.2 `safety.py`: 修改 `_recycle_subpath()`，reason 以 `source_cleaner:` 开头时使用 `[清理器-源目录]` 分区
- [ ] 1.3 `safety.py`: 修改 `recycle_cleanup()` 兼容 `.dir.meta`，过期时 `shutil.rmtree()` 删除整个目录
- [ ] 1.4 单元测试：`move_dir_to_recycle` 基本功能、分区路径、过期清理

### Phase 2: 权限检测扩展

- [ ] 2.1 `permission_checker.py`: `check_config_permissions()` 新增清理器启用时 source_dir 写权限检测
- [ ] 2.2 `config.js`: 清理器配置保存时增加 source_dir + recycle_dir 写权限校验
- [ ] 2.3 `source_cleaner_handlers.py`: execute 端点执行前校验 recycle_dir 写权限
- [ ] 2.4 单元测试：清理器启用/未启用时权限检测行为差异

### Phase 3: 后缀名统一 + 清理模式重定义

- [ ] 3.1 `source_cleaner.py`: 删除硬编码 `VIDEO_EXTENSIONS`/`SUBTITLE_EXTENSIONS`，改为从全局配置读取
- [ ] 3.2 `source_cleaner.py`: 重写 `_classify_file()`，实现 `media_only` 和 `media_and_related` 两种模式的完整语义
- [ ] 3.3 `source_cleaner.py`: 实现同名关联文件匹配（`_is_companion_file()`）
- [ ] 3.4 `config_loader.py`: 新增 `merge_strategy`、`ai_prompt` 默认值；`cleanup_mode` 值迁移
- [ ] 3.5 `config_validator.py`: 新增 `merge_strategy` 校验
- [ ] 3.6 单元测试：两种模式分类逻辑、同名关联匹配、配置迁移

### Phase 4: AI 分析层实现

- [ ] 4.1 `source_cleaner.py`: 实现 `_build_cleaner_prompt()` 构造目录级 AI 分析提示词
- [ ] 4.2 `source_cleaner.py`: 实现 `_ai_analyze_directory()` 调用 LLM（复用 LLMScraper 的 urllib + OpenAI 模式，优先使用 fast_model）
- [ ] 4.3 `source_cleaner.py`: 实现 `_parse_ai_response()` 解析 AI 返回的 JSON
- [ ] 4.4 `source_cleaner.py`: 实现 `_merge_results()` 合并规则和 AI 结果（union/intersection 策略）
- [ ] 4.5 `source_cleaner.py`: 重写 `preview()` 和 `execute()`，整合规则+AI+合并流程
- [ ] 4.6 单元测试：AI 提示词构造、响应解析、合并策略（并集/交集）

### Phase 5: 文件夹处理完善

- [ ] 5.1 `source_cleaner.py`: 实现黑名单目录整目录标记删除（`_scan_blacklist_dirs()`）
- [ ] 5.2 `source_cleaner.py`: 空目录处理改为 `move_dir_to_recycle()` 而非 `os.rmdir()`
- [ ] 5.3 单元测试：黑名单目录匹配、空目录入回收站

### Phase 6: 回收站浏览与恢复

- [ ] 6.1 `safety.py`: 新增 `list_recycle_dir()` 扫描回收站，解析 `.meta`/`.dir.meta`，返回文件列表+分区统计
- [ ] 6.2 `safety.py`: 新增 `restore_from_recycle()` 恢复文件/目录到原位置，处理冲突（跳过/覆盖/重命名）
- [ ] 6.3 `safety.py`: 新增 `delete_from_recycle()` 永久删除回收站文件/目录
- [ ] 6.4 `api/recycle_handlers.py`: 新建，实现 `recycle_list`/`recycle_restore`/`recycle_delete` 三个端点
- [ ] 6.5 `handler.py`: 注册回收站路由（GET /api/recycle/list、POST /api/recycle/restore、POST /api/recycle/delete）
- [ ] 6.6 单元测试：浏览（分区/过滤）、恢复（正常/冲突/目录）、永久删除

### Phase 7: 清理器 API 变更

- [ ] 7.1 `source_cleaner_handlers.py`: execute 端点支持 `merge_strategy` 参数，响应新增统计字段
- [ ] 7.2 `source_cleaner_handlers.py`: 新增 `ai-preview` 端点（仅 AI 分析不执行规则）
- [ ] 7.3 `handler.py`: 注册清理器新路由
- [ ] 7.4 `cleaner_repo.py`: 记录新增 `merge_strategy`、`rule_only_count`、`ai_only_count`、`both_count` 字段
- [ ] 7.5 `config.yaml.example`: 新增 `merge_strategy`、`ai_prompt` 配置项

### Phase 8: 前端改造

- [ ] 8.1 `index.html`: 重构清理器配置面板，删除 `toggleInfoPanel` 方式，高级配置直接展示
- [ ] 8.2 `index.html`: 新增合并策略选择器（AI 启用时显示）
- [ ] 8.3 `index.html`: 新增"预览清理结果"按钮和弹窗
- [ ] 8.4 `config.js`: 新增 `merge_strategy` 读写；修复 `onSourceCleanerToggle()` 高级配置联动
- [ ] 8.5 `config.js`: 清理器保存时增加权限检测（source_dir 写权限 + recycle_dir 写权限）
- [ ] 8.6 `index.html`: 新增回收站一级页签（与"任务"、"配置"并列），包含统计栏+筛选栏+文件列表+批量操作
- [ ] 8.7 `recycle.js`: 新建，回收站浏览/恢复/删除前端逻辑
- [ ] 8.8 `recycle.css`: 新建，回收站样式

### Phase 9: 测试与同步

- [ ] 9.1 集成测试：完整清理流程（规则+AI+合并+回收站+权限）
- [ ] 9.2 集成测试：回收站浏览+恢复+永久删除
- [ ] 9.3 回归测试：确保现有测试不受影响
- [ ] 9.4 deploy 目录同步

## 验收标准

1. 清理器读取全局 `video_extensions`/`subtitle_extensions`，不再硬编码
2. AI 分析以目录为单位，能看到文件大小对比并正确识别广告视频
3. 合并策略（交集/并集）行为正确，前端可切换
4. 空目录和黑名单目录整体移入回收站，`.dir.meta` 记录元信息
5. 回收站新增 `[清理器-源目录]` 分区，与任务流产生的 `[源目录]` 隔离
6. `recycle_cleanup` 正确处理 `.dir.meta` 过期清理
7. 清理器启用时 source_dir 权限检测升级为读写
8. 前端高级配置启用时直接展示，不再有交互 bug
9. 回收站 Tab 可浏览所有回收文件，显示原始路径、来源、原因
10. 回收站恢复功能可将文件/目录恢复到原位置，冲突时有处理选项
11. 回收站永久删除功能需二次确认
12. 所有现有测试通过

## 决策理由

- **回收站优先实现**：所有删除操作统一走回收站，是后续清理器重构的基础设施
- **权限检测前置**：避免用户配置了清理器但运行时因权限不足失败
- **AI 复用 LLMScraper 模式**：不引入新依赖，使用 `fast_model` 降低成本
- **交集默认**：保守策略减少误删，回收站恢复机制作为安全网

## 风险分析

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| AI 分析延迟过高 | 中 | 清理器执行慢 | 使用 fast_model；目录级批量分析减少调用次数 |
| AI 返回格式不稳定 | 中 | 解析失败 | 严格 JSON 格式要求 + 容错解析（解析失败时跳过 AI 结果） |
| 回收站目录结构变更影响现有数据 | 低 | 旧回收站文件无法过期清理 | `_recycle_subpath` 向后兼容，旧分区仍可识别 |
| 权限检测误报 | 低 | 用户无法保存配置 | `is_app_managed_path` 免检 fnOS 管理路径 |
