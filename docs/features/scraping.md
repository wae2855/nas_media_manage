# Scraping Feature

刮削负责根据文件名、路径、AI 识别、TMDB/Provider 结果和置信度规则生成可入库的媒体元数据。

## Current Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/scraping/__init__.py` | Feature public API for metadata scraper, LLM scraper, confidence engine, and matcher/model helpers. |
| `media_importer/features/scraping/metadata_scraper.py` | High-level metadata scraping orchestration. |
| `media_importer/features/scraping/confidence_engine.py` | Confidence scoring and review threshold decisions. |
| `media_importer/features/scraping/confidence_models.py` | Confidence config, result dataclasses, and shared parsing patterns. |
| `media_importer/features/scraping/dimension_manager.py` | Dimension mapping, tier checks, and category normalization. |
| `media_importer/features/scraping/dimensions_service.py` | Dimension CRUD/tier-gated application service for API callers. |
| `media_importer/scraper/metadata_scraper.py` | Thin legacy import wrapper for `MetadataScraper`. |
| `media_importer/scraper/confidence_models.py` | Thin legacy import wrapper for confidence models. |
| `media_importer/scraper/confidence_engine.py` | Thin legacy import wrapper for `ConfidenceEngine`. |
| `media_importer/scraper/dimension_manager.py` | Thin legacy import wrapper for dimension helpers. |
| `media_importer/scraper/llm_scraper.py` | LLM prompt and parsing behavior. |
| `media_importer/scraper/tmdb_client.py` | TMDB client and error type, exposed through the scraping feature. |
| `media_importer/features/providers/` | External metadata provider registry, interface, and implementations. |
| `media_importer/scraper/providers/` | Thin legacy import wrappers for provider modules. |

## Current Consumers

- TMDB API handlers import `TMDbClient` and `TMDbError` from `media_importer.features.scraping`.
- Dimension API handlers import dimension query/update services from `media_importer.features.scraping`.
- Import-flow scrape steps import file-dimension lookup from `media_importer.features.scraping`.
- `MetadataScraper`, `ConfidenceEngine`, confidence models, and dimension mapping have moved under `media_importer/features/scraping/`; remaining `media_importer/scraper/` files are implementation details until migrated.

## Target Shape

- Continue moving LLM and provider-adjacent scraping implementation into `media_importer/features/scraping/`.
- Keep provider implementations under `features/providers/`; keep lower-level external clients as explicit adapters until separately migrated.
- Keep confidence/review decisions aligned with `features/import_flow/services/review.py`.

## Related Areas

- Config: AI provider keys, TMDB keys, confidence thresholds, dimension rules.
- API: scrape config and manual task actions.
- Database: scrape result JSON and trace/debug fields.
- Frontend: scrape settings, task result display, review/confirm flows.

## Tests

- `tests/test_confidence_engine.py`
- `tests/test_feature_entrypoints.py`
- Scrape-related API and import-flow tests.
- Provider tests when external calls are mocked.

## Migration Notes

- New app/API/import-flow code should import from `media_importer.features.scraping`.
- Until implementation files move, `media_importer/scraper/` remains implementation detail but is not the preferred feature entry.
- New scraping behavior must update `docs/architecture/scraping.md` and this feature doc.

---

## 刮削流程规范

### 两种刮削模式

系统支持两种刮削模式，通过配置 `metadata.scrape_mode` 控制：

| 模式 | 说明 | AI依赖 |
|------|------|--------|
| `provider_first` | Provider 优先，AI 仅补充缺失维度 | 可选 |
| `ai_only` | 纯 AI 刮削，跳过 Provider | 需要 AI |

### 模式降级规则

当配置了 `ai_only` 但 AI 未启用时：
- `ai_only`：返回错误提示

### 核心流程

#### 1. provider_first 模式流程

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

**详细步骤：**

1. **文件名清洗**：使用正则表达式提取标题、年份、季集信息
2. **AI 清洗（可选）**：若检测到年份可疑（`year_suspect`）且 AI 可用，调用 AI 辅助清洗
3. **Provider 搜索**：
   - 优先使用 CJK 标题搜索
   - 若匹配度低于阈值，尝试英文标题搜索
   - 选择匹配度更高的结果
4. **获取详情**：根据搜索结果获取完整元数据
5. **维度映射**：将 Provider 返回的原始数据转换为系统维度
6. **维度完整性检查**：验证是否所有启用的维度都有值
7. **结果生成**：
   - 维度完整且无 AI：直接返回 Provider 数据
   - 维度完整且有 AI：仍直接返回（AI 未调用）
   - 维度不完整：调用 AI 补充缺失维度

#### 2. ai_only 模式流程

```text
文件名清洗 → AI刮削 → 置信度计算 → 返回结果
```

**详细步骤：**

1. **文件名清洗**：正则提取基础信息
2. **AI 刮削**：直接调用 LLM 获取所有元数据
3. **置信度计算**：基于 AI 返回结果计算置信度上限
4. **返回结果**：包含 AI 生成的所有维度

### AI 触发条件汇总

| 场景 | 是否触发 AI | 原因 |
|------|-----------|------|
| `provider_first` + 维度完整 | 否 | Provider 数据已足够 |
| `provider_first` + 维度不完整 | 是 | 补充缺失维度 |
| `provider_first` + Provider 无结果 | 是 | 降级为纯 AI |
| `provider_first` + Provider 详情失败 | 是 | 降级为纯 AI |
| `ai_only` | 是 | 纯 AI 模式 |
| 年份可疑 | 是（可选） | 辅助标题清洗 |
| Provider 匹配度低 | 是（可选） | 重新清洗后重试搜索 |

---

## 置信度计算规范

### 置信度组成

置信度由两部分组成，最终结果为两者的乘积：

```
final_confidence = search_confidence × data_gate
```

#### 1. 搜索置信度 (search_confidence)

仅在 Provider 优先模式且 AI 补充时计算，由 `T × R` 组成：

| 分量 | 含义 | 计算方式 |
|------|------|----------|
| T | 标题匹配度 | 根据匹配级别计算（L1-L6） |
| R | 结果数惩罚因子 | 根据搜索结果数量动态调整 |

**T 值含义：**

| 值范围 | 含义 |
|--------|------|
| 1.0 | 精确匹配 + 年份一致（L1） |
| 0.9 | 精确匹配 + 有季号（L2） |
| 0.7 | 精确匹配无年份（L3） |
| 0.4 | 精确匹配年份不同（L4） |
| <0.7 | 模糊匹配（L5/L6） |

**R 值规则：**
- 搜索结果越多，R 值越小（匹配越不确定）
- 当 T 值较高时，R 会动态提升（匹配质量越高，结果数惩罚越轻）

#### 2. 数据门控 (data_gate)

用于验证维度来源的可信度：

| 值 | 含义 |
|----|------|
| 1 | 所有维度来源可信 |
| 0 | 任一维度来源不可信 |

**触发条件：**
- 当 `data_gate = 0` 时，最终置信度为 0，触发审核流程

### 纯 AI 模式置信度

在 `ai_only` 模式下，置信度计算方式不同：

```
final_confidence = ai_cap × data_gate
```

其中 `ai_cap` 是 AI 置信度上限，基于清洗标题与 AI 返回标题的相似度计算。

### 置信度阈值

系统使用以下阈值决定任务流向：

| 阈值 | 含义 | 默认值 |
|------|------|--------|
| `pass_threshold` | 自动通过阈值 | 0.8 |
| `confirm_threshold` | 需确认阈值 | 0.5 |
| `review_threshold` | 需审核阈值 | 0.3 |

**决策逻辑：**

| 置信度范围 | 结果 | 任务状态 |
|-----------|------|----------|
| ≥ 0.8 | 自动通过 | 自动入库 |
| 0.5 ~ 0.8 | 需确认 | 待确认队列 |
| 0.3 ~ 0.5 | 需审核 | 待审核队列 |
| < 0.3 | 失败 | 人工处理 |

### 置信度追踪

每次刮削都会生成详细的追踪信息（`scrape_trace`），包含：

- `scrape_mode`：刮削模式
- `ai_invoked`：是否调用了 AI
- `ai_invoke_reason`：AI 调用原因
- `search_enhanced`：是否使用了联网搜索增强
- 各步骤的详细计算过程

---

## 联网搜索增强

### 功能说明

AI 刮削支持联网搜索增强，通过配置 `llm.web_search.enabled` 启用。启用后，AI 在处理刮削请求时会先进行联网搜索，获取最新的影视信息。

### 支持的 Provider

联网搜索增强目前支持以下 AI Provider：
- Zhipu（智谱）
- Qwen（通义千问）
- Moonshot（月之暗面）

### 标识位置

系统在以下位置显示搜索增强状态：

1. **置信度计算详情弹窗**：在 AI 相关步骤中显示标识
2. **模拟测试结果**：在纯 AI 和 Provider 优先步骤中显示
3. **任务详情决策路径**：在决策路径标题旁显示

### 状态标识

| 状态 | 图标 | 颜色 |
|------|------|------|
| 联网搜索增强 | 🔍 | 青色 (#06B6D4) |
| 纯本地分析 | 📴 | 灰色 (#94A3B8) |