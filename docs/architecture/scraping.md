# Scraping Architecture

## Responsibilities

- 清洗文件名，提取标题、年份、季集信息
- 调用 Provider（如 TMDB）搜索元数据
- 调用 LLM 整理和补充结果
- 计算置信度评分
- 映射分类维度

## Entry Points

| Module | Path | Role |
|--------|------|------|
| MetadataScraper | `media_importer/features/scraping/metadata_scraper.py` | 刮削流程编排 |
| ConfidenceEngine | `media_importer/features/scraping/confidence_engine.py` | 置信度计算引擎 |
| ConfidenceModels | `media_importer/features/scraping/confidence_models.py` | 置信度配置和数据模型 |
| DimensionManager | `media_importer/features/scraping/dimension_manager.py` | 维度映射和分类归一化 |
| Providers | `media_importer/features/providers/` | 元数据 Provider 注册和工厂 |
| PromptBuilder | `media_importer/features/prompts/prompt_builder.py` | 提示词模板构建 |

## 刮削模式

系统支持两种刮削模式，通过配置 `metadata.scrape_mode` 控制：

| 模式 | 说明 | AI依赖 |
|------|------|--------|
| `provider_first` | Provider 优先，AI 仅补充缺失维度 | 可选 |
| `ai_only` | 纯 AI 刮削，跳过 Provider | 需要 AI |

### 模式降级规则

当配置了 `ai_only` 但 AI 未启用时：
- `ai_only`：返回错误提示

## 核心流程

### Provider First 模式

```text
文件名清洗 → Provider搜索 → 维度完整性检查
     ↓                ↓                ↓
  AI清洗(可选)    获取详情       完整?
                          ↓       ↓
                        是       否
                        ↓       ↓
                 直接返回    AI补充维度
                          ↓
                     返回结果
```

**关键步骤：**
1. **文件名清洗**：正则提取标题、年份、季集信息
2. **AI 清洗（可选）**：年份可疑时调用 AI 辅助清洗
3. **Provider 搜索**：优先 CJK 标题，失败则尝试英文标题
4. **维度映射**：通过 `map_provider_to_dimension()` 将 Provider 数据转换为系统维度
5. **完整性检查**：验证所有启用维度是否有值
6. **AI 补充**：仅当维度不完整时调用 AI

### AI Only 模式

```text
文件名清洗 → AI刮削 → 置信度计算 → 返回结果
```

## 置信度计算规范

### 置信度组成

置信度由两部分组成，最终结果为两者的乘积：

```
final_confidence = search_confidence × data_gate
```

#### 搜索置信度 (search_confidence)

仅在 Provider 优先模式且 AI 补充时计算，由 `T × R` 组成：

| 分量 | 含义 | 计算方式 |
|------|------|----------|
| T | 标题匹配度 | 根据匹配级别计算（L1-L6） |
| R | 结果数惩罚因子 | 根据搜索结果数量动态调整 |

**T 值含义：**
- 1.0：精确匹配 + 年份一致（L1）
- 0.9：精确匹配 + 有季号（L2）
- 0.7：精确匹配无年份（L3）
- 0.4：精确匹配年份不同（L4）
- <0.7：模糊匹配（L5/L6）

**R 值规则：**
- 搜索结果越多，R 值越小
- T 值较高时，R 会动态提升

#### 数据门控 (data_gate)

用于验证维度来源的可信度：
- 值为 1：所有维度来源可信
- 值为 0：任一维度来源不可信（触发审核流程）

### 纯 AI 模式置信度

```
final_confidence = ai_cap × data_gate
```

其中 `ai_cap` 是 AI 置信度上限，基于清洗标题与 AI 返回标题的相似度计算。

### 置信度阈值

| 阈值 | 含义 | 默认值 | 任务状态 |
|------|------|--------|----------|
| `pass_threshold` | 自动通过 | 0.8 | 自动入库 |
| `confirm_threshold` | 需确认 | 0.5 | 待确认队列 |
| `review_threshold` | 需审核 | 0.3 | 待审核队列 |
| < 0.3 | 失败 | - | 人工处理 |

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
| `provider_first` + 维度完整 | 否 | Provider 数据已足够 |
| `provider_first` + 维度不完整 | 是 | 补充缺失维度 |
| `provider_first` + Provider 无结果 | 是 | 降级为纯 AI |
| `ai_only` | 是 | 纯 AI 模式 |
| 年份可疑 | 是（可选） | 辅助标题清洗 |

## Extension Points

- **新 Provider**：在 `features/providers/` 实现 `MetadataProvider`，注册到 provider registry
- **新维度映射**：更新 `features/scraping/dimension_manager.py`、DB 维度配置、文档和测试
- **新置信度规则**：更新 `features/scraping/confidence_engine.py`、`features/import_flow/services/review.py` 和置信度测试
- **新提示词配置**：更新 `features/prompts/prompt_builder.py`、prompts API、配置文档和 UI 测试

## Tests

- `tests/test_confidence_engine.py`
- `tests/test_feature_entrypoints.py`
- `tests/test_confidence_config_ui.py`
- `tests/test_import_flow_services.py`（审核决策边界）