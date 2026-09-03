# Scraping Feature

> **行为契约事实源**：本文件描述代码组织。系统行为（匹配流程、字段定义、信息职责）以标准文档为准：
> - [../standards/scrape-matching.md](../standards/scrape-matching.md) — 两级匹配行为契约
> - [../standards/info-architecture.md](../standards/info-architecture.md) — 6 层信息职责模型
> - [../standards/ai-prompt-design.md](../standards/ai-prompt-design.md) — AI 提示词输入/输出契约
> - [../architecture/scraping.md](../architecture/scraping.md) — 字段传递路径与设计理由

刮削负责根据文件名、受控目录证据和 TMDB/Provider 结果生成可入库的媒体元数据；AI 不参与作品身份匹配。

## Current Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/scraping/__init__.py` | Feature public API for metadata scraper, LLM scraper, match engine, and matcher/model helpers. |
| `media_importer/features/scraping/metadata_scraper.py` | High-level metadata scraping orchestration. |
| `media_importer/features/scraping/match_engine.py` | Three-tier matching engine (replaces confidence_engine). |
| `media_importer/features/scraping/match_models.py` | Match result dataclasses: MatchResult, MatchConcern (replaces confidence_models). |
| `media_importer/features/scraping/confidence_models.py` | `DEFAULT_CONFIDENCE_CONFIG` 候选排序阈值配置（TitleMatcher 内部用，不作任务状态判定）。 |
| `media_importer/features/scraping/dimension_manager.py` | Dimension mapping, tier checks, and category normalization. |
| `media_importer/features/scraping/dimensions_service.py` | Dimension CRUD/tier-gated application service for API callers. |
| `media_importer/features/scraping/title_matcher.py` | Title matching L1-L7 levels. |
| `media_importer/features/scraping/filename_cleaner.py` | 发布名结构清洗和多语言标题候选。 |
| `media_importer/features/scraping/release_identity.py` | 中文发布说明薄层、GuessIt 通用语法和结构化字段归一化。 |
| `media_importer/features/scraping/identity_evidence.py` | 文件名主证据、目录辅助证据门禁和可序列化识别依据。 |
| `media_importer/features/scraping/nfo_identity.py` | 受来源根约束的相邻 NFO 身份 ID 读取。 |
| `media_importer/features/scraping/deterministic_identity.py` | 显式 Provider ID/NFO ID 的优先解析、冲突校验和降级轨迹。 |
| `media_importer/features/scraping/title_normalizer.py` | 标题严格/宽松归一化与相似度事实源。 |
| `media_importer/features/scraping/errors.py` | LLM exception classes. |
| `media_importer/features/scraping/metadata_scrape_flow.py` | Metadata scrape flow orchestration. |
| `media_importer/features/providers/` | External metadata provider registry, interface, and implementations. |
| `media_importer/features/providers/tmdb_client.py` | TMDB client and error type (migrated from `scraper/tmdb_client.py`). |

## Current Consumers

- TMDB API handlers import `TMDbClient` and `TMDbError` from `media_importer.features.scraping`.
- Dimension API handlers import dimension query/update services from `media_importer.features.scraping`.
- Import-flow scrape steps import file-dimension lookup from `media_importer.features.scraping`.
- `MetadataScraper`, `MatchEngine`, match models, and dimension mapping are under `media_importer/features/scraping/`.

## Target Shape

- Continue moving LLM and provider-adjacent scraping implementation into `media_importer/features/scraping/`.
- Keep provider implementations under `features/providers/`; keep lower-level external clients as explicit adapters until separately migrated.
- Keep match/review decisions aligned with `features/import_flow/services/review.py`.
- Formal import flow must let `MatchEngine` select one Provider candidate first and let `MetadataScraper` fetch that same candidate's details; the two paths must not independently choose different works.
- `confidence_engine.py` and `confidence_models.py` are deprecated; new code must use `match_engine.py` and `match_models.py`.

## Related Areas

- Config: AI provider keys, TMDB keys, matching config (optional), dimension rules.
- API: scrape config, scrape preview (three-tier path), manual task actions.
- Database: scrape result JSON, match_level/match_concerns/match_trace fields.
- Frontend: task card match status labels, match concern display, scrape preview three-tier path.

## Tests

- `tests/test_match_engine.py`
- `tests/test_identity_evidence.py`
- `tests/test_media_identity_resolution_v2.py`
- `tests/test_review_decision_v2.py`
- `tests/test_match_result_fields.py`
- `tests/test_tier2_match_engine.py`
- `tests/test_scrape_preview_api.py`
- `tests/test_feature_entrypoints.py`
- Scrape-related API and import-flow tests.
- Provider tests when external calls are mocked.

## Migration Notes

> `media_importer/scraper/` 兼容层已于 2026-08-22 删除（简洁化 Phase 0）；guard 拦截旧导入。

- New app/API/import-flow code should import from `media_importer.features.scraping` (architecture guard `test_no_production_code_imports_scraper_package` 阻止新增 `media_importer.scraper.*` 引用).
- New scraping behavior must update `docs/architecture/scraping.md` and this feature doc.
- GuessIt 版本固定在运行与 fnOS 离线依赖中；升级必须覆盖真实发布名语料并复核自动通过边界。
- Code referencing `confidence_engine` or `confidence_models` should migrate to `match_engine` and `match_models`.

---

## 两级匹配策略规范

> ADR: [0005-three-tier-matching.md](../decisions/0005-three-tier-matching.md)
> Plan（已归档）：[2026-06-12-refactor-three-tier-matching-plan.md](../_archive/2026-06-17-plans-cleanup/2026-06-12-refactor-three-tier-matching-plan.md)

系统使用“Provider 自动识别 → 用户确认”的两级策略。匹配判断回答「这个文件是哪部作品」，维度判断回答「这部作品属于什么分类」，两者彻底解耦。

### 刮削模式

系统只保留 `provider_first` 一种刮削模式（`metadata.scrape_mode`）。旧的 `ai_only` 和 `hybrid` 模式已废弃，配置迁移时自动转为 `provider_first`。

**未配置 Provider 时的降级**：

1. 启动时检测：`scrape_mode=provider_first` 但无可用 Provider
2. 日志和配置检查明确提示 Provider 不可用
3. 自动任务进入用户确认，不启用 AI 刮削兜底
4. 前端配置页提示配置 TMDB API Key

### 两级匹配流程

#### 第一级：Provider 精确匹配

```text
文件名结构清洗 → 文件主证据 + 通过门禁的目录辅助证据
        │
        ├── 每个中文/英文标题分别查询并用自身复核
        ├── 收集全部文件标题候选后，唯一作品+年份/季集精确匹配 → AUTO_PASS
        ├── 文件标题精确命中 Provider 官方别名且年份/类型一致 → AUTO_PASS
        ├── 文件和目录命中同一 Provider ID → AUTO_PASS
        ├── 弱文件名由可信目录标题+年份/季集补足 → AUTO_PASS
        └── 无结果、无年份歧义或证据冲突 → 第二级用户确认
```

**精确匹配定义**（复用 TitleMatcher L1 逻辑）：
- 清洗后标题与 Provider 返回标题归一化后完全相等
- 年份精确一致（如果文件名有年份）
- 无年份的唯一结果仍需确认；不得因为 Provider 只返回一条就自动入库

#### 目录辅助证据门禁

```text
文件 basename 始终是主证据；必须完成全部中文/英文标题候选的强匹配收集，同一作品才自动通过，指向不同作品则人工确认。目录不得否决唯一强文件身份。
来源根、通用下载目录、日期/哈希目录、技术规格目录和电影型多视频容器不作为片名；未知目录清洗后无可信标题时继续向上。
BDMV/STREAM/Season xx/Specials/Disc 等结构目录只允许在来源根内有限向上寻找有效标题目录；TV `Specials` 等价于 Season 00。
Extras/Trailers/Featurettes/Samples/Special Features 等附加内容目录是继承边界：不继承作品根 `movie.nfo/tvshow.nfo`，只读取当前视频同 basename 的 NFO；`Special Features` 不得与 `Specials` 混同。
NFO 标记 `movie/series/episode/unknown` scope；episode NFO ID 保留为解释证据，但绝不当作 series ID 查询。
目录与文件分别查询，禁止拼接原始字符串；冲突一律交给用户确认。
```

#### 第二级：用户确认

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
| AI 不确定 | `AI_UNCERTAIN` | 历史兼容字段 | 新流程不再生成 |

**疑虑原因数据结构**：

```python
@dataclass
class MatchConcern:
    code: str              # reason_code
    message: str           # 用户可读文案
    detail: str            # 详细技术说明
    candidates: list       # 候选列表（用于用户确认级展示）
```

### 匹配结果数据结构

```python
@dataclass
class MatchResult:
    level: str           # AUTO_PASS / NEEDS_CONFIRM / FAILED
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
| TMDB 不提供的维度 | 显式默认值或留空待确认 | 可选 |
| 分辨率 | ffprobe 文件检测，与刮削无关 | 否（预置阈值） |

维度映射结果必须记录 Provider、命中规则和默认值来源；缺失维度不得通过 AI 猜测。

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
  max_candidates_for_user: 5        # 用户确认时展示的最大候选数，默认 5
```

绝大多数用户不需要改任何配置。`matching` 区块甚至可以不出现，全部用默认值。

### DB 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `match_level` | TEXT | AUTO_PASS / NEEDS_CONFIRM / FAILED |
| `match_concerns` | TEXT | JSON array of MatchConcern |
| `match_trace` | TEXT | JSON 匹配路径追踪 |
| `scrape_confidence` | TEXT | 保留，兼容历史数据，新任务不写入 |

### 前端展示

| 任务状态 | match_level | 前端展示 |
|----------|-------------|----------|
| 新任务 | AUTO_PASS | "自动匹配" |
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
