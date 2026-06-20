# Scraping Feature

> **行为契约事实源**：本文件描述代码组织。系统行为（匹配流程、字段定义、信息职责）以标准文档为准：
> - [../standards/scrape-matching.md](../standards/scrape-matching.md) — 三级匹配行为契约
> - [../standards/info-architecture.md](../standards/info-architecture.md) — 6 层信息职责模型
> - [../standards/ai-prompt-design.md](../standards/ai-prompt-design.md) — AI 提示词输入/输出契约
> - [../architecture/scraping.md](../architecture/scraping.md) — 字段传递路径与设计理由

刮削负责根据文件名、路径、AI 识别、TMDB/Provider 结果和三级匹配策略生成可入库的媒体元数据。

## Current Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/scraping/__init__.py` | Feature public API for metadata scraper, LLM scraper, match engine, and matcher/model helpers. |
| `media_importer/features/scraping/metadata_scraper.py` | High-level metadata scraping orchestration. |
| `media_importer/features/scraping/match_engine.py` | Three-tier matching engine (replaces confidence_engine). |
| `media_importer/features/scraping/match_models.py` | Match result dataclasses: MatchResult, MatchConcern (replaces confidence_models). |
| `media_importer/features/scraping/confidence_engine.py` | Legacy re-export compatibility layer (deprecated). |
| `media_importer/features/scraping/confidence_models.py` | Legacy compatibility layer (deprecated). |
| `media_importer/features/scraping/dimension_manager.py` | Dimension mapping, tier checks, and category normalization. |
| `media_importer/features/scraping/dimensions_service.py` | Dimension CRUD/tier-gated application service for API callers. |
| `media_importer/features/scraping/llm_scraper.py` | LLM prompt and parsing behavior (migrated from `scraper/`). |
| `media_importer/features/scraping/title_matcher.py` | Title matching L1-L7 levels (migrated from `scraper/`). |
| `media_importer/features/scraping/filename_cleaner.py` | Filename cleaning and CJK separation (migrated from `scraper/`). |
| `media_importer/features/scraping/llm_match_assist.py` | LLM match assist helpers (migrated from `scraper/`). |
| `media_importer/features/scraping/llm_client.py` | LLM HTTP client implementation (migrated from `scraper/`). |
| `media_importer/features/scraping/errors.py` | LLM exception classes (migrated from `scraper/`). |
| `media_importer/features/scraping/metadata_scrape_flow.py` | Metadata scrape flow orchestration (migrated from `scraper/`). |
| `media_importer/scraper/metadata_scraper.py` | Compat re-export (迁移期,保留一个版本周期). |
| `media_importer/scraper/match_engine.py` | Compat re-export (迁移期,保留一个版本周期). |
| `media_importer/scraper/confidence_engine.py` | Compat re-export (deprecated,迁移期保留). |
| `media_importer/scraper/confidence_models.py` | Compat re-export (deprecated,迁移期保留). |
| `media_importer/scraper/dimension_manager.py` | Compat re-export (迁移期,保留一个版本周期). |
| `media_importer/scraper/llm_scraper.py` | Compat re-export (迁移期,保留一个版本周期). |
| `media_importer/scraper/title_matcher.py` | Compat re-export (迁移期,保留一个版本周期). |
| `media_importer/scraper/filename_cleaner.py` | Compat re-export (迁移期,保留一个版本周期). |
| `media_importer/scraper/tmdb_client.py` | Compat re-export (迁移期,保留一个版本周期). |
| `media_importer/scraper/exceptions.py` | Compat re-export (迁移期,保留一个版本周期). |
| `media_importer/scraper/_llm_client_impl.py` | Compat re-export (迁移期,保留一个版本周期). |
| `media_importer/scraper/_llm_match_assist.py` | Compat re-export (迁移期,保留一个版本周期). |
| `media_importer/scraper/metadata_scrape_flow.py` | Compat re-export (迁移期,保留一个版本周期). |
| `media_importer/features/providers/` | External metadata provider registry, interface, and implementations. |
| `media_importer/features/providers/tmdb_client.py` | TMDB client and error type (migrated from `scraper/tmdb_client.py`). |
| `media_importer/scraper/providers/` | Compat re-export wrappers (迁移期,保留一个版本周期). |

## Current Consumers

- TMDB API handlers import `TMDbClient` and `TMDbError` from `media_importer.features.scraping`.
- Dimension API handlers import dimension query/update services from `media_importer.features.scraping`.
- Import-flow scrape steps import file-dimension lookup from `media_importer.features.scraping`.
- `MetadataScraper`, `MatchEngine`, match models, and dimension mapping are under `media_importer/features/scraping/`; remaining `media_importer/scraper/` files are migration-period compat re-exports, retained for one release cycle (see S-Phase 5).

## Target Shape

- Continue moving LLM and provider-adjacent scraping implementation into `media_importer/features/scraping/`.
- Keep provider implementations under `features/providers/`; keep lower-level external clients as explicit adapters until separately migrated.
- Keep match/review decisions aligned with `features/import_flow/services/review.py`.
- `confidence_engine.py` and `confidence_models.py` are deprecated; new code must use `match_engine.py` and `match_models.py`.

## Related Areas

- Config: AI provider keys, TMDB keys, matching config (optional), dimension rules.
- API: scrape config, scrape preview (three-tier path), manual task actions.
- Database: scrape result JSON, match_level/match_concerns/match_trace fields.
- Frontend: task card match status labels, match concern display, scrape preview three-tier path.

## Tests

- `tests/test_match_engine.py`
- `tests/test_review_decision_v2.py`
- `tests/test_config_migration_v3.py`
- `tests/test_match_pipeline_integration.py`
- `tests/test_scrape_preview_api.py`
- `tests/test_feature_entrypoints.py`
- Scrape-related API and import-flow tests.
- Provider tests when external calls are mocked.

## Migration Notes

- New app/API/import-flow code should import from `media_importer.features.scraping` (architecture guard `test_no_production_code_imports_scraper_package` 阻止新增 `media_importer.scraper.*` 引用).
- `media_importer/scraper/` files are migration-period compat re-exports, retained for one release cycle. They are not the preferred entry; production code must not import from them.
- New scraping behavior must update `docs/architecture/scraping.md` and this feature doc.
- Code referencing `confidence_engine` or `confidence_models` should migrate to `match_engine` and `match_models`.

---

## 三级匹配策略规范

> ADR: [0005-three-tier-matching.md](../decisions/0005-three-tier-matching.md)
> Plan: [2026-06-12-refactor-three-tier-matching-plan.md](../plans/2026-06-12-refactor-three-tier-matching-plan.md)

系统使用离散的三级匹配策略替代旧的数学公式化置信度体系（T×R×data_gate）。匹配判断回答「这个文件是哪部作品」，维度判断回答「这部作品属于什么分类」，两者彻底解耦。

### 刮削模式

系统只保留 `provider_first` 一种刮削模式（`metadata.scrape_mode`）。旧的 `ai_only` 和 `hybrid` 模式已废弃，配置迁移时自动转为 `provider_first`。

**未配置 Provider 时的降级**：

1. 启动时检测：`scrape_mode=provider_first` 但无可用 Provider
2. 日志打印 WARNING：「未配置元数据 Provider（TMDB），刮削将降级为 AI-only 模式」
3. 自动降级：跳过第一级，所有文件走第二级（AI辅助）→ 第三级（用户确认）
4. 前端配置页提示：「建议配置 TMDB API Key 以获得更精确的自动匹配」

### 三级匹配流程

#### 第一级：Provider 精确匹配

```text
文件名清洗 → 提取中文名/英文名/年份/季/集
        │
        ├── 用中文名+年份查 Provider
        │     → 精确匹配到唯一结果 → AUTO_PASS
        │
        ├── 用英文名+年份查 Provider
        │     → 精确匹配到唯一结果 → AUTO_PASS
        │
        ├── 无年份，只用名字查
        │     → 唯一精确匹配 → AUTO_PASS
        │     → 多个精确匹配 → 进入第二级（原因：无年份导致多个同名结果）
        │
        └── 无精确匹配 → 进入第二级
```

**精确匹配定义**（复用 TitleMatcher L1 逻辑）：
- 清洗后标题与 Provider 返回标题归一化后完全相等
- 年份精确一致（如果文件名有年份）
- 或者无年份但搜索结果只返回 1 条精确标题匹配

#### 第二级：上下文辅助匹配

```text
收集上下文信息：
  ├── 同级目录文件名列表（同一文件夹下的其他视频）
  ├── 上级文件夹名
  ├── 上两级文件夹名
  │
  将以下信息交给 AI：
  ├── 文件名清洗结果（标题/年份/季集）
  ├── Provider 搜索候选列表（Top 5-10，含标题/年份/简介）
  ├── 目录上下文
  │
  AI 辅助判断（无需联网搜索增强）：
  ├── 能确定匹配 → AUTO_PASS（附 AI 判断理由）
  └── 无法确定 → 进入第三级（附 AI 不确定的原因）
```

**AI 不确定的判定规则**：
- AI 返回 `confidence < 0.7` → 不确定
- AI 返回 `selected_index = -1` → 无匹配
- AI 返回格式错误/调用失败 → 降级

**降级策略**：AI 不可用时跳过第二级，直接进入第三级，疑虑原因附加 `AI_UNCERTAIN + "AI 辅助不可用，降级为人工确认"`。

#### 第三级：用户确认

```text
准备用户确认数据：
  ├── Provider 搜索结果 Top 5（按热度排序，默认选中第 1 个）
  ├── 匹配疑虑原因（为什么无法自动匹配）
  ├── 已提取的文件信息（标题/年份/季集）
  │
  展示给用户：
  ├── 疑虑原因标签（如"无年份，同名作品3部"）
  ├── 候选列表（可切换选择）
  └── 确认入库按钮
```

### 匹配疑虑原因体系

每个进入用户确认的任务必须携带明确的疑虑原因：

| 疑虑类型 | reason_code | 展示文案 | 示例 |
|----------|-------------|----------|------|
| 无年份多同名 | `NO_YEAR_MULTI_MATCH` | 「无年份信息，找到 N 部同名作品」 | "Inception" 无年份 → 2010 版 vs 其他 |
| 年份不匹配 | `YEAR_MISMATCH` | 「文件名年份与搜索结果不一致」 | 文件名 2023，搜索结果只有 2022 版 |
| 标题模糊匹配 | `FUZZY_TITLE` | 「标题不完全匹配，相似度 N%」 | 文件名 "Wandering Earth"，TMDB 是 "The Wandering Earth" |
| Provider 无结果 | `NO_PROVIDER_RESULT` | 「刮削源未找到匹配作品」 | 极小众影片 |
| 标题缺失 | `NO_TITLE` | 「无法从文件名提取有效标题」 | 文件名全是乱码 |
| 多信息冲突 | `CONFLICTING_INFO` | 「文件名信息与目录结构信息冲突」 | 文件名暗示电影，目录结构暗示剧集 |
| AI 不确定 | `AI_UNCERTAIN` | 「AI 辅助判断后仍无法确定」 | 候选列表中有两个非常接近的结果 |

**疑虑原因数据结构**：

```python
@dataclass
class MatchConcern:
    code: str              # reason_code
    message: str           # 用户可读文案
    detail: str            # 详细技术说明
    candidates: list       # 候选列表（用于第三级展示）
```

### 匹配结果数据结构

```python
@dataclass
class MatchResult:
    level: str           # AUTO_PASS / CONTEXT_PASS / NEEDS_CONFIRM
    provider_id: int     # 匹配到的 Provider 条目 ID
    provider_title: str
    confidence_reason: str  # 为什么匹配成功或失败
    concerns: List[MatchConcern]  # 疑虑原因列表
    trace: dict          # 匹配路径追踪
```

### 维度处理策略（与匹配解耦）

维度判断和匹配判断彻底解耦：

| 维度来源 | 策略 | 是否需要配置 |
|----------|------|-------------|
| TMDB 结构化数据 | 直接用，确定性映射 | 否（预置映射规则） |
| TMDB genre_ids → 维度 | 确定性映射（如 genre_id=99 → 纪录片=true） | 否（代码内预置） |
| TMDB 不提供的维度 | AI 补齐（带联网搜索增强） | 否（自动触发） |
| 分辨率 | ffprobe 文件检测，与刮削无关 | 否（预置阈值） |

**AI 补齐维度的时机**：在匹配成功后（无论是哪一级匹配成功），统一检查维度完整性。TMDB 映射完仍有缺失的维度，一次性交给 AI 补齐，此时 AI 可以使用联网搜索增强。

### AI 触发条件汇总

| 场景 | 是否触发 AI | 原因 |
|------|-----------|------|
| 第一级精确匹配 + 维度完整 | 否 | Provider 数据已足够 |
| 第一级精确匹配 + 维度不完整 | 是 | 补充缺失维度（可联网搜索） |
| 第一级未匹配 → 第二级 | 是 | AI 辅助从候选列表中选择（不联网） |
| 第二级 AI 不确定 → 第三级 | 否 | 等待用户确认 |
| 年份可疑 | 是（可选） | 辅助标题清洗 |
| Provider 无结果 | 是 | 降级为纯 AI 刮削 |

### 配置

#### 移除的配置

以下配置已移除，不再需要用户配置：

- `confidence` 区块全部参数（20+ 参数）
- `llm.confidence_threshold`
- `metadata.scrape_mode` 的 `ai_only` 和 `hybrid` 选项

#### 保留的配置

```yaml
metadata:
  scrape_mode: "provider_first"     # 唯一模式

manual_review:
  enabled: false                    # 强制所有任务走用户确认
```

#### 新增的配置（可选，有合理默认值）

```yaml
matching:
  exact_match_t_threshold: 1.0      # 第一级精确匹配的 T 值阈值，默认 1.0
  context_match_enabled: true       # 是否启用第二级上下文辅助，默认 true
  max_candidates_for_user: 5        # 用户确认时展示的最大候选数，默认 5
```

绝大多数用户不需要改任何配置。`matching` 区块甚至可以不出现，全部用默认值。

### DB 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `match_level` | TEXT | AUTO_PASS / CONTEXT_PASS / NEEDS_CONFIRM |
| `match_concerns` | TEXT | JSON array of MatchConcern |
| `match_trace` | TEXT | JSON 匹配路径追踪 |
| `scrape_confidence` | TEXT | 保留，兼容历史数据，新任务不写入 |

### 前端展示

| 任务状态 | match_level | 前端展示 |
|----------|-------------|----------|
| 新任务 | AUTO_PASS | "自动匹配" |
| 新任务 | CONTEXT_PASS | "AI辅助匹配" |
| 新任务 | NEEDS_CONFIRM | "需确认" + 疑虑原因标签 |
| 历史任务（旧引擎） | NULL | 按终态展示（已入库/失败），不展示置信度数值 |

---

## 联网搜索增强

### 功能说明

AI 刮削支持联网搜索增强，通过配置 `llm.web_search.enabled` 启用。

### 使用场景

联网搜索增强在以下场景使用：
- **维度补齐**：TMDB 映射完仍有缺失维度时，AI 可联网搜索获取最新信息
- **新上映影片**：AI 训练数据可能不包含
- **限制级分级**：依赖各国官方分级机构数据，TMDB 可能不完整

注意：第二级上下文辅助匹配中的 AI 判断**不使用**联网搜索，因为候选列表已由 Provider 提供。

### 支持的 Provider

联网搜索增强目前支持以下 AI Provider：
- Zhipu（智谱）
- Qwen（通义千问）
- Moonshot（月之暗面）

### 标识位置

系统在以下位置显示搜索增强状态：
1. **匹配路径展示**：在 AI 相关步骤中显示标识
2. **模拟测试结果**：在维度补齐步骤中显示
3. **任务详情匹配路径**：在决策路径标题旁显示

### 状态标识

| 状态 | 图标 | 颜色 |
|------|------|------|
| 联网搜索增强 | 🔍 | 青色 (#06B6D4) |
| 纯本地分析 | 📴 | 灰色 (#94A3B8) |
