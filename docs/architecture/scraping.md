# Scraping Architecture

## Responsibilities

- 从文件名和通过门禁的目录名提取独立标题、年份、季集证据
- 从发布名和相邻 NFO 提取确定性 Provider ID，并在标题检索前解析
- 调用 Provider（如 TMDB）搜索元数据
- 两级匹配策略判断：Provider 自动识别或用户确认
- 映射分类维度

## Entry Points

| Module | Path | Role |
|--------|------|------|
| MetadataScraper | `media_importer/features/scraping/metadata_scraper.py` | 刮削流程编排 |
| MatchEngine | `media_importer/features/scraping/match_engine.py` | 两级匹配引擎（替代 ConfidenceEngine） |
| MatchModels | `media_importer/features/scraping/match_models.py` | 匹配数据模型：MatchResult, MatchConcern |
| ConfidenceEngine | `media_importer/features/scraping/confidence_engine.py` | Legacy 兼容层（deprecated） |
| ConfidenceModels | `media_importer/features/scraping/confidence_models.py` | Legacy 兼容层（deprecated） |
| DimensionManager | `media_importer/features/scraping/dimension_manager.py` | 维度映射和分类归一化 |
| TitleMatcher | `media_importer/features/scraping/title_matcher.py` | 标题匹配 L1-L7 级别（第一级精确匹配依赖；S-Phase 1 已从 `scraper/` 迁入） |
| FilenameCleaner | `media_importer/features/scraping/filename_cleaner.py` | 文件名清洗和 CJK 分离（S-Phase 1 已从 `scraper/` 迁入） |
| ReleaseIdentity | `media_importer/features/scraping/release_identity.py` | 中文薄层、GuessIt 通用发布名解析、保守结果归一化 |
| IdentityEvidence | `media_importer/features/scraping/identity_evidence.py` | 文件主证据、目录辅助证据门禁、多集范围及任务追踪数据 |
| NfoIdentity | `media_importer/features/scraping/nfo_identity.py` | 受控本地 NFO I/O，只输出身份 ID 与校验辅助字段 |
| PathRoles | `media_importer/features/scraping/path_roles.py` | 结构、通用、技术、附加内容目录分类与身份继承边界 |
| DeterministicIdentity | `media_importer/features/scraping/deterministic_identity.py` | Provider ID 优先级、类型/年份冲突和异常降级 |
| TitleNormalizer | `media_importer/features/scraping/title_normalizer.py` | 标题严格/宽松规范化和相似度 |
| Providers | `media_importer/features/providers/` | 元数据 Provider 注册和工厂 |

## 刮削模式

系统只保留 `provider_first` 一种刮削模式（`metadata.scrape_mode`）。旧的 `ai_only` 和 `hybrid` 模式已废弃。

**未配置 Provider 时的降级**：启动时明确提示 Provider 不可用，任务进入用户确认；不启用 AI 刮削兜底。

## 两级匹配策略

发布名解析遵循 ADR-0024；确定性身份遵循 ADR-0025。GuessIt 保留 TMDB/IMDb/TVDB ID，NFO 读取器在受控相邻路径提取 ID，Provider 适配器负责原生/外部 ID 查询。NFO 身份显式区分 `movie/series/episode/unknown`；episode ID 不得作为 series ID 查询。ID 查到后仍须通过明确年份和媒体类型校验；冲突进入人工确认，接口异常留痕后回到标题流程。不确定结果在任何大文件复制前进入人工确认。

> ADR: [0005-three-tier-matching.md](../decisions/0005-three-tier-matching.md)

### 第一级：Provider 精确匹配

```text
文件名结构清洗 → 显式 ID/NFO ID 确定性查询 → 可选目录结构清洗 → 每条标题证据独立查询 Provider
     │
     ├── 全部文件标题候选收集后唯一精确匹配 + 年份/季集一致 → AUTO_PASS（目录不得否决）
     ├── 文件与目录命中同一 Provider ID + 年份一致 → AUTO_PASS
     ├── 弱文件名 + 可信目录精确匹配 → AUTO_PASS
     └── 无结果、证据不足或冲突 → 用户确认
```

文本候选以标题严格/宽松一致、年份、媒体类型、季集和文件/目录收敛形成可解释分数；热度只作同证据分数的平局裁决。第一、第二名过近且没有强 ID 时必须进入人工确认。

**目录门禁**：目录按 structural、generic、technical、supplementary、meaningful 分类。来源根、通用目录、日期/哈希目录、`1080p/2160p/4K/UHD/BluRay/REMUX/WEB-DL/WEBRip/HDTV/Complete` 等技术目录、`BDMV/STREAM/Season xx/Disc` 等结构目录及电影型多视频容器本身不作为片名；清洗后无可信标题也继续向上。`Extras/Trailers/Featurettes/Samples` 等附加内容目录是身份继承边界，不再向作品根借用目录身份或作品级 NFO。

**NFO inheritance boundary**：正常 `Season/BDMV` 结构允许在来源根内有限上溯 `movie.nfo/tvshow.nfo`；一旦路径经过附加内容目录，只允许读取与当前视频同目录、同 basename 的 NFO。`episodedetails` 中的 Provider ID 作为 episode 证据留痕，当前 Provider 未提供 episode→series 解析时跳过确定性 ID 查询并回退标题流程。

### 第二级：用户确认

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
| `AI_UNCERTAIN` | 历史兼容字段，新匹配流程不再生成 |

### 匹配与维度解耦

匹配判断（哪部作品）和维度判断（什么分类）彻底解耦：

- 匹配在刮削时一次性完成，结果为 `match_level`
- 维度在匹配成功后按可编辑的 Provider 映射和显式默认值统一解析
- 分辨率由 ffprobe 文件检测，与刮削无关

## 维度映射

维度映射通过 `map_provider_to_dimension()` 函数实现，支持多种匹配类型：

| 匹配类型 | 说明 | 应用场景 |
|----------|------|----------|
| `genre_ids` | 通过类型 ID 映射 | 纪录片、动画、类型分类 |
| `country_codes` | 通过国家代码映射 | 地区维度 |
| `direct_match` | 直接匹配 | 语言维度 |
| `certification` | 通过分级认证映射 | 分级维度 |

## Extension Points

- **新 Provider**：在 `features/providers/` 实现 `MetadataProvider`，注册到 provider registry
- **新维度映射**：更新 `features/scraping/dimension_manager.py`、DB 维度配置、文档和测试
- **新匹配规则**：更新 `features/scraping/match_engine.py`、`features/import_flow/services/review.py` 和匹配测试
- **新疑虑原因**：更新 `match_models.py` 中的 concern code 定义、前端展示文案和测试

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
MatchEngine.match(filename, video_path)
    ↓ 返回 MatchResult（含 L1-L6 全部字段）
    ↓ MetadataScraper 按 selected_candidate 获取同一作品完整详情
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
| [../standards/scrape-matching.md](../standards/scrape-matching.md) | 两级匹配行为契约 |
| [../standards/info-architecture.md](../standards/info-architecture.md) | 6 层信息职责模型 |
| [../standards/ai-prompt-design.md](../standards/ai-prompt-design.md) | AI 提示词输入/输出契约 |

本架构文档描述"为什么这样设计"，标准文档描述"系统如何工作"。冲突时以标准文档为准。
