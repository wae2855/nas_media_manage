# Source Cleaner Architecture

源目录清理器独立于主任务流，用于识别并清理源目录中的垃圾文件、广告文件、Sample、无关文本等。

## Entry Points

| Module | Path | Role |
|--------|------|------|
| SourceCleaner | `media_importer/features/source_cleaning/cleaner.py` | 清理决策预览和执行 |
| ApplicationService | `media_importer/features/source_cleaning/application_service.py` | Feature 应用入口 |
| Records | `media_importer/features/source_cleaning/records.py` | 清理记录仓库 |
| API Handlers | `media_importer/api/source_cleaner_handlers.py` | HTTP 接口 |
| DB Repository | `media_importer/core/db/cleaner_repo.py` | 数据库访问 |

## Boundaries

- 主任务流处理视频和字幕任务
- 源目录清理器处理任务之外的源目录维护
- 删除行为必须遵守回收站安全规则
- 旧 `storage/source_cleaner.py` public import 保持可用，不能删除

## 清理模式

系统支持两种清理模式：

| 模式 | 说明 | 清理范围 |
|------|------|----------|
| `media_only` | 仅清理非媒体文件 | 删除所有非视频、非字幕文件 |
| `media_and_related` | 清理非影视相关文件 | 删除与视频文件无关的文件，保留关联元数据 |

## 核心清理流程

```text
预览模式:
┌─────────────────────────────────────────────────────────────┐
│  规则分类 → AI分析(可选) → 结果合并 → 空目录检测 → 返回预览列表  │
└─────────────────────────────────────────────────────────────┘

执行模式:
┌─────────────────────────────────────────────────────────────┐
│  预览 → 遍历列表 → 移动到回收站 → 记录执行结果                │
└─────────────────────────────────────────────────────────────┘
```

## 规则分类机制

规则分类按以下顺序执行：

1. **黑名单模式匹配**：文件名匹配黑名单模式 → 删除
2. **保护扩展名**：文件扩展名在保护列表 → 保留
3. **小视频检测**：视频文件小于阈值 → 删除（垃圾视频）
4. **字幕文件**：扩展名在字幕列表 → 保留
5. **删除扩展名**：扩展名在删除列表 → 删除
6. **模式判断**：根据 `cleanup_mode` 决定是否删除非媒体文件

### 分类类别

| 类别 | 说明 | 来源 |
|------|------|------|
| `blacklist_pattern` | 匹配黑名单模式 | 规则 |
| `junk_video` | 小视频文件 | 规则 |
| `delete_extension` | 扩展名在删除列表 | 规则 |
| `non_media` | 非媒体/非相关文件 | 规则 |
| `ai_delete` | AI 判定删除 | AI |
| `empty_dir` | 空目录 | 规则 |
| `blacklist_dir` | 黑名单目录 | 规则 |

## AI 智能分析

AI 分析在规则分类基础上提供额外的智能判断：

### AI 分析原则

1. **整体视角**：分析整个目录的文件构成，而非孤立判断单个文件
2. **容量对比**：同一目录下，视频文件大小差异显著时，小文件大概率是广告/样本/预告
3. **命名模式**：文件名含 sample、trailer、预告、花絮、广告等关键词的应删除
4. **关联识别**：与视频同名的 .nfo、.jpg、.png 等是影视元数据/海报，应保留
5. **字幕文件**：.srt、.ass 等字幕文件应保留
6. **保守原则**：无法确定时倾向于保留，避免误删

### AI 输出格式

```json
{
    "analysis": "简要分析说明",
    "decisions": {
        "文件名": {"action": "keep或delete", "reason": "判断理由"}
    }
}
```

## 结果合并策略

| 策略 | 说明 | 适用场景 |
|------|------|----------|
| `intersection` | 规则和 AI 都判定删除才删除 | 最保守，误删风险最低 |
| `union` | 规则或 AI 任一判定删除即删除 | 清理最彻底 |
| `rule_only` | 仅使用规则判定 | 不依赖 AI |
| `ai_only` | 仅使用 AI 判定 | 完全依赖 AI |

## 配置参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `enabled` | 是否启用源目录清理 | false |
| `cleanup_mode` | 清理模式 | media_only |
| `ai_enabled` | 是否启用 AI 辅助分析 | false |
| `merge_strategy` | 结果合并策略 | intersection |
| `junk_video_max_size_mb` | 垃圾视频最大阈值(MB) | 0（不检测） |
| `delete_extensions` | 强制删除的扩展名列表 | [] |
| `protect_extensions` | 强制保留的扩展名列表 | [] |
| `blacklist_patterns` | 黑名单文件名模式 | [] |
| `cleanup_empty_dirs` | 是否清理空目录 | false |
| `schedule` | 定时清理计划（cron） | "" |

## 安全保障

### 回收站机制

所有删除操作都通过回收站执行：

```text
删除 → 移动到回收站 → 保留指定天数 → 自动清理/手动恢复
```

**回收站配置**：
- `source_policy.recycle_dir`：回收站目录路径
- `source_policy.recycle_retention_days`：保留天数

### 保护机制

1. **任务文件保护**：正在处理的任务文件不会被清理
2. **路径限制**：清理范围仅限于 `source_dir` 内
3. **预览机制**：执行前必须先预览，确认后再执行
4. **恢复能力**：误删文件可从回收站恢复

## 执行记录

每次清理执行后生成记录，包含：

| 字段 | 说明 |
|------|------|
| `executed_at` | 执行时间 |
| `mode` | 清理模式 |
| `merge_strategy` | 合并策略 |
| `total_files` | 清理文件数量 |
| `total_size_mb` | 清理总大小(MB) |
| `rule_only_count` | 仅规则判定删除数量 |
| `ai_only_count` | 仅 AI 判定删除数量 |
| `both_count` | 两者共同判定删除数量 |
| `items` | 清理文件详情列表 |

## 最佳实践

1. **初始配置**：
   - 使用 `media_and_related` 模式保护关联文件
   - 设置合理的 `junk_video_max_size_mb`（建议 50-100MB）
   - 启用 AI 辅助分析提升准确性

2. **安全第一**：
   - 初始使用 `intersection` 合并策略
   - 定期检查回收站确保无误删
   - 设置合理的回收站保留天数

3. **性能优化**：
   - 对于大型目录，禁用 AI 分析可提升速度
   - 合理设置黑名单模式减少误判
   - 定时清理建议在低峰时段执行