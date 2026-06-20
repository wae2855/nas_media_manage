# Scraping Architecture

## Responsibilities

- 清洗文件名，提取标题、年份、季集信息
- 调用 Provider（如 TMDB）搜索元数据
- 调用 LLM 整理和补充结果
- 三级匹配策略判断（替代旧的置信度公式计算）
- 映射分类维度

## Entry Points

| Module | Path | Role |
|--------|------|------|
| MetadataScraper | `media_importer/features/scraping/metadata_scraper.py` | 刮削流程编排 |
| MatchEngine | `media_importer/features/scraping/match_engine.py` | 三级匹配引擎（替代 ConfidenceEngine） |
| MatchModels | `media_importer/features/scraping/match_models.py` | 匹配数据模型：MatchResult, MatchConcern |
| ConfidenceEngine | `media_importer/features/scraping/confidence_engine.py` | Legacy 兼容层（deprecated） |
| ConfidenceModels | `media_importer/features/scraping/confidence_models.py` | Legacy 兼容层（deprecated） |
| DimensionManager | `media_importer/features/scraping/dimension_manager.py` | 维度映射和分类归一化 |
| TitleMatcher | `media_importer/features/scraping/title_matcher.py` | 标题匹配 L1-L7 级别（第一级精确匹配依赖；S-Phase 1 已从 `scraper/` 迁入） |
| FilenameCleaner | `media_importer/features/scraping/filename_cleaner.py` | 文件名清洗和 CJK 分离（S-Phase 1 已从 `scraper/` 迁入） |
| Providers | `media_importer/features/providers/` | 元数据 Provider 注册和工厂 |
| PromptBuilder | `media_importer/features/prompts/prompt_builder.py` | 提示词模板构建 |

## 刮削模式

系统只保留 `provider_first` 一种刮削模式（`metadata.scrape_mode`）。旧的 `ai_only` 和 `hybrid` 模式已废弃。

**未配置 Provider 时的降级**：
- 启动时检测无可用 Provider → 日志 WARNING → 跳过第一级，走第二级（AI辅助）→ 第三级（用户确认）

## 三级匹配策略

> ADR: [0005-three-tier-matching.md](../decisions/0005-three-tier-matching.md)

### 第一级：Provider 精确匹配

```text
文件名清洗 → 提取标题/年份/季集 → Provider 搜索
     │
     ├── 精确匹配 + 年份一致 → AUTO_PASS
     ├── 无年份 + 唯一精确匹配 → AUTO_PASS
     ├── 无年份 + 多个精确匹配 → 进入第二级
     └── 无精确匹配 → 进入第二级
```

**精确匹配定义**：复用 TitleMatcher L1 逻辑，清洗后标题归一化完全相等 + 年份一致。

### 第二级：上下文辅助匹配

```text
收集目录上下文（上级文件夹名 + 同级文件名列表）
     │
     Provider 候选列表 + 上下文 → AI 辅助判断（不联网）
     │
     ├── AI 确定 → AUTO_PASS
     └── AI 不确定 → 进入第三级
```

**降级**：AI 不可用时跳过第二级，直接进入第三级。

### 第三级：用户确认

```text
Provider 搜索结果 Top 5 + 匹配疑虑原因 → 用户选择 → 确认入库
```

### 匹配疑虑原因

| reason_code | 展示文案 |
|-------------|----------|
| `NO_YEAR_MULTI_MATCH` | 无年份信息，找到 N 部同名作品 |
| `YEAR_MISMATCH` | 文件名年份与搜索结果不一致 |
| `FUZZY_TITLE` | 标题不完全匹配 |
| `NO_PROVIDER_RESULT` | 刮削源未找到匹配作品 |
| `NO_TITLE` | 无法从文件名提取有效标题 |
| `CONFLICTING_INFO` | 文件名信息与目录结构信息冲突 |
| `AI_UNCERTAIN` | AI 辅助判断后仍无法确定 |

### 匹配与维度解耦

匹配判断（哪部作品）和维度判断（什么分类）彻底解耦：

- 匹配在刮削时一次性完成，结果为 `match_level`
- 维度在匹配成功后统一映射：TMDB 确定性映射 → AI 补齐缺失维度（可联网搜索）
- 分辨率由 ffprobe 文件检测，与刮削无关

## 维度映射

维度映射通过 `map_provider_to_dimension()` 函数实现，支持多种匹配类型：

| 匹配类型 | 说明 | 应用场景 |
|----------|------|----------|
| `genre_ids` | 通过类型 ID 映射 | 纪录片、动画、类型分类 |
| `country_codes` | 通过国家代码映射 | 地区维度 |
| `direct_match` | 直接匹配 | 语言维度 |
| `certification` | 通过分级认证映射 | 分级维度 |

## AI 触发条件

| 场景 | 是否触发 AI | 原因 |
|------|-----------|------|
| 第一级精确匹配 + 维度完整 | 否 | Provider 数据已足够 |
| 第一级精确匹配 + 维度不完整 | 是 | 补充缺失维度（可联网搜索） |
| 第一级未匹配 → 第二级 | 是 | AI 辅助从候选列表中选择（不联网） |
| 第二级 AI 不确定 → 第三级 | 否 | 等待用户确认 |
| 年份可疑 | 是（可选） | 辅助标题清洗 |
| Provider 无结果 | 是 | 降级为纯 AI 刮削 |

## Extension Points

- **新 Provider**：在 `features/providers/` 实现 `MetadataProvider`，注册到 provider registry
- **新维度映射**：更新 `features/scraping/dimension_manager.py`、DB 维度配置、文档和测试
- **新匹配规则**：更新 `features/scraping/match_engine.py`、`features/import_flow/services/review.py` 和匹配测试
- **新疑虑原因**：更新 `match_models.py` 中的 concern code 定义、前端展示文案和测试
- **新提示词配置**：更新 `features/prompts/prompt_builder.py`、prompts API、配置文档和 UI 测试

## Tests

- `tests/test_match_engine.py`
- `tests/test_review_decision_v2.py`
- `tests/test_config_migration_v3.py`
- `tests/test_match_pipeline_integration.py`
- `tests/test_scrape_preview_api.py`
- `tests/test_feature_entrypoints.py`
- `tests/test_import_flow_services.py`（审核决策边界）
- `tests/test_match_result_fields.py`（MatchResult 字段契约）
- `tests/test_phase_pqr.py`（is_valid / selected_candidate_id / FAILED）
- `tests/test_formal_flow_field_propagation.py`（正式流程字段传递）

---

## 数据流：字段传递路径

> 完整字段契约见 [../standards/info-architecture.md](../standards/info-architecture.md)

### 关键路径

```
MatchEngine.match()
    ↓ 返回 MatchResult（含 L1-L6 全部字段）
    ↓ MatchResult.to_dict() 序列化
match_dict
    ↓
    ├──→ scrape.py（正式任务）
    │     result['match_level'] = match_dict['match_level']
    │     result['match_concerns'] = match_dict['concerns']
    │     result['match_trace'] = match_dict
    │     result['match_tier'] = match_dict['match_tier']           ← 必须透传
    │     result['tier_short_reason'] = match_dict['tier_short_reason']  ← 必须透传
    │     result['ai_reason'] = match_dict['ai_reason']             ← 必须透传
    │     result['selected_candidate'] = match_dict['selected_candidate']  ← 必须透传
    │     ↓
    │     task['scrape_result'] = result
    │     ↓
    │     DB tasks.scrape_result（JSON 列）
    │
    └──→ scrape_preview_job.py（模拟器）
          同样 4 个字段透传到 scrape_result
          ↓
          API /api/scrape/preview/status/{job_id}
          ↓
          前端模拟器渲染

前端统一入口：
    task 对象（来自 API）
        ↓
    buildMatchPathData(task)        ← 唯一装配器，禁止各视图自己拼
        ↓
    renderMatchPathPreview(data)    ← 6 步时间轴渲染
        ↓
    列表行 / 卡片 / 详情 / 追踪弹窗 各取所需字段
```

### 模拟器与正式任务一致性约束

**绝对约束**：`scrape.py` 和 `scrape_preview_job.py` 输出的 `scrape_result` JSON 字段结构必须完全一致。

违反此约束会导致：
- 模拟器显示正确，正式任务显示空白（或反之）
- 前端 `buildMatchPathData` 无法统一处理
- 测试在一边通过但另一边失败

### 失败状态流转

```
AI 返回 is_valid=false
    ↓
MatchResult(match_level="FAILED", match_tier=2)
    ↓
runner.py 检测到 FAILED
    ↓
task.status = "FAILED"
task.error_message = tier_short_reason
    ↓
不进入入库流程
    ↓
前端卡片显示 ❌ + ai_reason + 🔄 重新刮削按钮
    ↓
POST /api/tasks/{id}/rescrape （可选 new_filename）
    ↓
task.status = "PENDING"，重新入队
```

---

## 相关标准（事实源）

修改本架构文档前，必须先查阅：

| 标准 | 范围 |
|------|------|
| [../standards/scrape-matching.md](../standards/scrape-matching.md) | 三级匹配行为契约 |
| [../standards/info-architecture.md](../standards/info-architecture.md) | 6 层信息职责模型 |
| [../standards/ai-prompt-design.md](../standards/ai-prompt-design.md) | AI 提示词输入/输出契约 |

本架构文档描述"为什么这样设计"，标准文档描述"系统如何工作"。冲突时以标准文档为准。
