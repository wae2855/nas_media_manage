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
| TitleMatcher | `media_importer/scraper/title_matcher.py` | 标题匹配 L1-L7 级别（第一级精确匹配依赖） |
| FilenameCleaner | `media_importer/scraper/filename_cleaner.py` | 文件名清洗和 CJK 分离 |
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
