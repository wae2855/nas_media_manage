# 状态简化方案 v2

## 一、状态变更

| 现有状态 | 新方案 | 说明 |
|---------|--------|------|
| PENDING | 保留 | 待处理 |
| PROCESSING | 保留 | 处理中 |
| SUCCESS | 保留 | 成功 |
| CONFIRMING | 保留 | 确认中（人工确认模式） |
| FAILED | 保留 | 失败 |
| SKIPPED | 保留 | 跳过 |
| NEEDS_REVIEW | 移除 | 合并到 FAILED |
| ROLLBACK | 移除 | 合并到 FAILED（file_location=quarantine） |
| DUPLICATE_REVIEW | 移除 | 合并到 SKIPPED（quality 判定保留现有文件时） |

## 二、新状态机

```
PENDING → PROCESSING → SUCCESS（源文件删除，file_location=import）
                     → CONFIRMING（manual_review=true，刮削分类后暂停）
                                  → SUCCESS（确认入库）
                                  → SKIPPED（忽略→隔离区）
                                  → CONFIRMING（修改分类，重走分类后流程）
                     → FAILED（异常→隔离区，file_location=quarantine）
                     → SKIPPED（去重判定质量不如→隔离区，file_location=quarantine）

FAILED → PENDING（重试，从隔离区拷贝到temp继续）
SKIPPED → PENDING（重试，从隔离区拷贝到temp继续）
CONFIRMING → CONFIRMING（修改分类，只重走 classify→dedup→rename→import→notify→record）
任何状态 → 可删除任务（仅删DB记录，不删文件）
```

## 三、核心逻辑变更

### 3.1 修改分类（reclassify）

**现状**：修改分类后状态设 CONFIRMING，需要再点确认入库
**新逻辑**：修改分类后，直接重走分类后流程（classify → dedup → rename → import → notify → record），不再需要人工再点确认

### 3.2 temp 区域保留

文件始终从源目录/隔离区拷贝到 temp 目录做后续动作：
- 新任务：source → copy to temp → scrape → classify → ...
- 重试（隔离区）：quarantine → copy to temp → scrape → classify → ...
- 修改分类：文件已在 temp，直接从 classify 步骤开始

### 3.3 FAILED/SKIPPED 一律隔离

不再区分"达到重试上限才隔离"，失败/跳过即移入隔离区。
移除 max_auto_retries 配置。

### 3.4 入库同名检测始终启用

移除 duplicate_handling.enabled 配置，所有文件一律做入库同名检测，只保留策略选择。

### 3.5 移除 rollback

确认中任务不想入库 → 点"忽略"→ SKIPPED → 文件进隔离区

### 3.6 移除 DUPLICATE_REVIEW

去重完全由策略自动处理，不需要人工确认重复

## 四、配置变更

| 配置项 | 变更 |
|--------|------|
| source_policy.max_auto_retries | 移除 |
| duplicate_handling.enabled | 移除 |
| duplicate_handling.strategy | 保留 |

## 五、数据库变更

- VALID_STATUSES: 9 → 6
- _migrate_schema: NEEDS_REVIEW→FAILED, ROLLBACK→FAILED, DUPLICATE_REVIEW→SKIPPED

## 六、前端变更

- 移除 NEEDS_REVIEW/ROLLBACK/DUPLICATE_REVIEW 筛选 tab
- 卡片 section 标题样式优化（字体放大、加粗、加装饰线）
- 配置面板移除"最大自动重试次数"和"启用入库同名检测"
- 任务操作按钮按新状态调整

## 七、变更文件清单

| 文件 | 变更 |
|------|------|
| db.py | VALID_STATUSES 缩减 + 迁移逻辑 |
| task_manager.py | retry/ignore/quarantine 逻辑调整 |
| pipeline.py | 删 rollback/dup_review, reclassify 重走分类后流程 |
| api_server.py | 删 2 路由, 扩展 ignore/retry |
| config_loader.py | 移除 max_auto_retries 默认值 |
| config.yaml | 移除 max_auto_retries 和 duplicate_handling.enabled |
| tasks.js | 状态映射/按钮/详情/筛选 |
| tasks.css | 删 3 状态样式 + 标题样式优化 |
| index.html | 筛选 tab + 配置面板 + 流程图 |
| config.js | 移除相关配置项 |
