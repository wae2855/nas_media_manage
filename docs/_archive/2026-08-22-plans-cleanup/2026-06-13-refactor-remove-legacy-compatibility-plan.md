---
title: "refactor: remove legacy compatibility surfaces"
type: plan
date: 2026-06-13
status: approved-for-implementation
confidence: high
related:
  - docs/plans/2026-06-13-ai-config-redesign-completion-plan.md
  - docs/decisions/0005-three-tier-matching.md
---

# 去历史兼容化清理计划

一行摘要：在产品尚未投入使用、没有历史用户和历史数据负担的前提下，删除为旧配置、旧 API、旧 UI、旧 DB 字段和旧导入路径保留的兼容逻辑，让代码和产品只保留当前事实。

## Problem Statement

近期重构为了降低风险保留了多处历史兼容入口，例如旧 AI 刮削提示词文件、旧 `llm` 配置、旧置信度 shim、旧同步 preview、`type/media_type` 双字段、旧任务状态别名、旧 Provider 返回契约等。

这些兼容层在已有用户产品中是合理的，但当前项目仍是新产品，尚未投入使用。继续保留会导致：

- 前端出现多个配置入口，用户不知道哪个生效。
- 运行时有多套 fallback 和优先级，低性能模型容易改错。
- 测试继续保护旧行为，阻碍新方案收敛。
- 文档出现“当前事实”和“历史兼容”并存，执行模型难以判断边界。
- 后续开发会把旧 shim 当成仍支持的能力。

因此本计划的目标是把兼容逻辑当作技术债一次性清理，只保留新产品当前事实。

## Target End State

- AI 提示词只通过 AI 配置中的 `ai_assist.prompt_*` / `ai_search.prompt_dimension_supplement` 管理。
- 运行时不再读取 `scraper_prompts.md`、`tmdb_prompts.md`、`{provider}_prompts.md`。
- 旧置信度相关代码、字段、API 和 UI 全部删除；系统只展示 `match_level`、`match_concerns`、`match_trace`、`confirm_reason`、`dim_sources`。
- Preview 只保留异步 job 接口：`POST /api/scrape/preview/start` 和 `GET /api/scrape/preview/status/{job_id}`。
- AI 配置只保留 `ai_assist` / `ai_search`，删除旧 `llm` 配置 fallback 和迁移。
- 刮削结果只使用 `media_type`，删除旧 `type` 兼容。
- 任务状态只使用当前 status/stage 模型，删除旧状态别名。
- Provider 搜索契约统一为 `SearchResult(items=...)`，删除 list 兼容。
- 配置和 DB 初始化直接面向当前最终 schema，不再保留尚未上线版本之间的长迁移链。
- 运行时代码 `media_importer/**` 中不再出现 `legacy` / `deprecated` / `兼容` 入口，除非是非功能性注释且有明确删除任务。

## Scope

- 后端配置模型、配置加载、配置保存和迁移逻辑。
- API 路由和 handler。
- 刮削、匹配、导入任务状态和维度来源相关运行时逻辑。
- 前端高级配置、AI 配置、Preview、任务卡片和匹配路径展示。
- 测试、文档和 guard。

## Non-Goals

- 不修改 `.env*`、`.config*`、`opencode.json*`。
- 不修改 `deploy/` 生成副本。
- 不做大规模视觉重设计。
- 不引入新外部依赖。
- 不保留向旧版本升级的迁移路径。
- 不处理真实线上数据迁移，因为当前前提是产品未投入使用。

## Execution Principles For Low-Performance Models

- 严格按阶段顺序执行，不要跨阶段并行改大范围代码。
- 每阶段只处理该阶段列出的文件和 grep 命中。
- 每阶段完成后先运行该阶段测试和 grep，再进入下一阶段。
- 删除优先于兼容；不要新增 shim、alias、fallback。
- 如果某个旧字段仍被测试依赖，优先改测试到新事实，而不是保留旧字段。
- 不清楚某处是否仍有产品必要时，默认删除旧入口，保留新事实源。
- 所有新 guard 测试必须扫描运行时代码，而不是只扫描文档。

## Proposed Solution

按依赖顺序执行 10 个阶段：

1. 建立 legacy baseline 和 guard。
2. 删除旧 AI 刮削提示词体系。
3. 删除旧 preview 同步接口和占位 helper。
4. 删除旧置信度 shim 和 `scrape_confidence`。
5. 删除旧 `llm` 配置兼容。
6. 删除 `type/media_type` 双字段兼容。
7. 删除旧任务状态别名。
8. 统一 Provider `SearchResult` 契约。
9. Squash 配置和 DB 迁移链。
10. 清理旧前端占位文件、legacy wrappers 和文档。

## Decision Rationale

- 选择删除而不是隐藏：当前没有历史用户，保留隐藏入口仍会误导后续模型和开发者。
- 选择分阶段：每类兼容层都有独立测试和风险，分阶段更容易定位回归。
- 选择 guard：历史兼容最容易通过“临时兜底”回归，源码扫描能低成本阻止旧词和旧接口重新出现。
- 选择先清提示词和 preview：它们是用户最容易直接触达的双入口和旧路径。
- 选择最后 squash 迁移：配置/DB 迁移影响范围最大，必须在运行时旧依赖清掉后再做。

## Assumptions

| Assumption | Status | Evidence |
|------------|--------|----------|
| 产品尚未投入使用，无需兼容历史用户配置和 DB | Verified by user | 用户明确说明“不考虑历史因素，这还是新产品，还没投入使用” |
| AI 配置页已经承接全部提示词管理 | Verified | `PromptResolver` 读取 `ai_assist.prompt_*` / `ai_search.prompt_dimension_supplement`，运行时优先使用 |
| 旧 preview 同步接口已可替换为异步 job | Verified | 当前已有 `/api/scrape/preview/start` 和 `/api/scrape/preview/status/{job_id}` |
| 删除迁移链可接受重建开发 DB | Assumed | 需执行模型在 Phase 9 前确认本地开发数据可丢弃或备份 |
| 所有 Provider 可统一到 `SearchResult` | Mostly verified | 当前真实 Provider 已返回 `SearchResult`，但测试中可能仍有 list mock |

## Risk Analysis

| Risk | Impact | Mitigation |
|------|--------|------------|
| 删除过多导致测试大面积失败 | 中 | 每阶段独立提交级别验证，先改测试契约再删代码 |
| `config.js` / `cinema-config.js` 中旧前端逻辑难以区分 | 中 | 使用 grep 定位入口，删除无 HTML 引用的函数；保留当前 AI 配置页必要函数 |
| DB migration squash 影响本地开发数据 | 中 | Phase 9 前备份或明确可重建；不改 deploy |
| 文档仍引用旧事实 | 中 | 最后执行文档 grep，当前事实文档不得保留旧入口 |
| 低性能模型误把业务 fallback 当 legacy | 中 | 区分：`fallback_dir`、图片加载 fallback、Provider 语言 fallback 是业务能力，不属于历史兼容，不删除 |

## Phase 0: Baseline And Guard

### Goal

建立要清理的 legacy surface 清单，并新增总 guard 测试，之后每阶段持续收紧。

### Tasks

- [ ] 运行 baseline grep：

```bash
rg "legacy|deprecated|向后兼容|历史兼容|旧版|旧 |scraper_prompts|tmdb_prompts|ConfidenceEngine|ConfidenceResult|scrape_confidence|LLMConfig|STATUS_CONFIRMING|STATUS_NEEDS_REVIEW|STATUS_PROCESSING|body_before_params|pass_self|provider_ai|ai_only|prompt-config|prompt-tmdb" media_importer tests docs
```

- [ ] 新增 `tests/test_no_legacy_compat_surface.py`，扫描运行时代码。
- [ ] 首版 guard 只扫描 `media_importer/**` 和 `tests/**`，不扫描 `docs/_archive/**`。
- [ ] Guard 中区分业务 fallback 和 legacy fallback：不要禁止 `fallback_dir`、图片 fallback、Provider 搜索 fallback。

### Acceptance Criteria

- [ ] Guard 测试存在。
- [ ] Guard 能发现至少一个当前 legacy 命中，作为后续阶段 RED 目标。
- [ ] 文档中记录允许例外和禁止例外。

## Phase 1: Remove Legacy AI Scraping Prompt Feature

### Goal

删除“高级配置 > AI刮削提示词”和文件级 prompt fallback。AI 提示词只来自 AI 配置。

### Files

- `media_importer/webui/partials/advanced-pages.html`
- `media_importer/webui/js/prompts.js`
- `media_importer/webui/js/cinema-app.js`
- `media_importer/webui/js/config.js`
- `media_importer/webui/js/cinema-config.js`
- `media_importer/api/routes.py`
- `media_importer/api/prompt_handlers.py`
- `media_importer/features/prompts/application_service.py`
- `media_importer/features/prompts/prompt_builder.py`
- `media_importer/scraper/llm_scraper.py`
- prompt 相关测试

### Tasks

- [ ] 从高级配置入口删除 `prompt-config` 卡片和页面。
- [ ] 删除 `prompts.js` 中旧提示词编辑、保存、重置、预览逻辑；如果整个文件只服务旧页面，删除文件和 script 引用。
- [ ] 删除 `/api/config/prompts`、`/api/config/prompts/reset` 路由。
- [ ] 删除 `/api/providers/{provider_type}/prompts`、`/api/providers/{provider_type}/prompts/reset` 路由。
- [ ] 删除 `PromptHandlersMixin` 中旧 prompt get/save/reset 方法。
- [ ] 删除 `application_service.py` 中 `scraper_prompts.md` / provider prompt 文件读写服务。
- [ ] 从 `LLMPromptBuilder` 删除：
  - `_load_prompts_from_file`
  - `_load_provider_prompts_from_files`
  - `_load_prompt_file`
  - `_load_tmdb_prompts_from_file`
  - `custom_system_prompt`
  - `_provider_prompts`
- [ ] 保留 `LLMPromptBuilder` 内置默认 prompt 和维度/schema 拼接能力。
- [ ] `llm_scraper.py` 保持：用户配置 prompt -> 内置默认 prompt，不再回退文件 prompt。
- [ ] 删除或更新依赖旧文件 prompt 的测试。

### Acceptance Criteria

```bash
rg "scraper_prompts|tmdb_prompts|config/prompts|providers/.*/prompts|prompt-tmdb|prompt-config|LLM\+Provider 刮削提示词|LLM 直接刮削提示词" media_importer tests
```

- [ ] 运行时代码无命中。
- [ ] AI 配置页 prompt 保存/加载仍通过测试。
- [ ] `tests/test_prompt_resolver_integration.py` 和 `tests/test_prompt_runtime.py` 通过。

## Phase 2: Remove Legacy Preview Endpoint And Helpers

### Goal

只保留异步 preview job，删除旧同步 `/api/scrape/preview` 和兼容占位 helper。

### Files

- `media_importer/api/routes.py`
- `media_importer/api/tmdb_handlers.py`
- `media_importer/webui/js/cinema-config.js`
- `media_importer/webui/js/prompts.js`（若 Phase 1 未删除）
- `tests/test_scrape_preview_api.py`
- `tests/test_scrape_preview_job.py`

### Tasks

- [ ] 删除 `POST /api/scrape/preview` 路由。
- [ ] 删除 `TMDbHandlersMixin._scrape_preview()`。
- [ ] 删除 `_decorate_scrape_preview_mode()`。
- [ ] 删除 `_build_scrape_preview_recommendation()`。
- [ ] 删除 `_resolve_import_paths()` 兼容占位，如果只服务旧 preview。
- [ ] 前端所有 preview 只调用 `/scrape/preview/start` + `/scrape/preview/status/{job_id}`。
- [ ] 删除旧 preview API 假响应测试，或改为测试新 job response。

### Acceptance Criteria

```bash
rg "scrape/preview\"|_scrape_preview\(|_decorate_scrape_preview_mode|_build_scrape_preview_recommendation|_resolve_import_paths|provider_ai|ai_only" media_importer tests
```

- [ ] 除 `/scrape/preview/start` 和 `/scrape/preview/status` 外无旧 preview 命中。
- [ ] `tests/test_scrape_preview_job.py` 通过。

## Phase 3: Remove Legacy Confidence Shim And scrape_confidence

### Goal

彻底删除旧置信度代码和 DB/API/UI 字段。系统只使用三级匹配状态。

### Files

- `media_importer/features/scraping/confidence_engine.py`
- `media_importer/features/scraping/confidence_models.py`
- `media_importer/scraper/trace_builder.py`
- `media_importer/features/import_flow/steps/scrape.py`
- `media_importer/features/import_flow/services/review.py`
- `media_importer/core/db/*`
- `media_importer/webui/js/tasks.js`
- 旧置信度测试

### Tasks

- [ ] 删除 `confidence_engine.py`。
- [ ] 从 `confidence_models.py` 删除 `ConfidenceResult`、`_calc_R`、`_aggregate` 和旧 config 常量；保留 `CleanResult` 和 TitleMatcher 需要的内部 `MatchResult`。
- [ ] 删除 `trace_builder.py`，或改为当前新 trace builder 并重命名；不得保留旧公式占位。
- [ ] 从 DB schema 删除 `scrape_confidence` 列（若 Phase 9 决定 squash schema，可在 Phase 9 实施）。
- [ ] 删除 `steps/scrape.py` 对 `scrape_confidence` 的赋值。
- [ ] 删除 `ReviewDecisionService(confidence_engine=...)` 兼容参数。
- [ ] 删除前端任务卡片对 `scrape_confidence` 的读取和注释。
- [ ] 删除旧置信度相关测试，保留 `match_level` 行为测试。

### Acceptance Criteria

```bash
rg "ConfidenceEngine|ConfidenceResult|scrape_confidence|confidence_engine|confidence_detail|final_confidence|search_conf|data_gate|_calc_R|_aggregate" media_importer tests
```

- [ ] 运行时代码无命中。
- [ ] `tests/test_no_legacy_confidence_surface.py` 可删除或并入总 guard。
- [ ] ReviewDecision 只测 `match_level`、`match_concerns`、`dim_sources`。

## Phase 4: Remove Legacy llm Config Compatibility

### Goal

AI 模型配置只保留 `ai_assist` / `ai_search`。删除旧 `llm` 配置和迁移。

### Files

- `media_importer/core/config_view.py`
- `media_importer/core/config_loader.py`
- `media_importer/core/config_migrations.py`
- `media_importer/scraper/llm_scraper.py`
- `media_importer/features/scraping/web_search_config.py`
- `media_importer/webui/js/config.js`
- `media_importer/webui/js/cinema-config.js`
- config tests

### Tasks

- [ ] 删除 `LLMConfig` dataclass。
- [ ] 删除 `ConfigView.llm`。
- [ ] 删除 `llm -> ai_assist / ai_search` 迁移。
- [ ] `llm_scraper.py` 构造函数只读取 `ai_assist` / `ai_search`。
- [ ] 删除 `llm.fallback_model`、`llm.confidence_threshold`、`llm.source_cleaner_model` 等旧字段。
- [ ] 如果仍需要备用模型，作为新字段单独设计；本计划默认不保留。
- [ ] 删除所有旧 `llm` 配置保存/加载 UI。

### Acceptance Criteria

```bash
rg "LLMConfig|fallback_model|source_cleaner_model|confidence_threshold|llm\.api_key|llm\[|get\(\"llm\"|get\('llm'" media_importer tests
```

- [ ] 运行时代码无旧 `llm` 配置读取。
- [ ] AI assist/search 运行时测试通过。

## Phase 5: Remove Provider Config Legacy

### Goal

Provider 配置只保留当前结构，删除旧 `metadata.tmdb` 等迁移和 fallback。

### Files

- `media_importer/features/configuration/application_service.py`
- `media_importer/core/config_loader.py`
- `media_importer/core/config_migrations.py`
- `media_importer/api/config_handlers.py`
- `media_importer/api/provider_handlers.py`
- provider/config tests

### Tasks

- [ ] 确认当前唯一 Provider 配置结构。
- [ ] 删除 `legacy_metadata` / `legacy_configs` 读取和迁移。
- [ ] 删除 `metadata.tmdb` fallback。
- [ ] 删除 `_get_real_config_value()` 中旧结构 fallback，如果存在。
- [ ] 文档只保留当前 Provider 配置契约。

### Acceptance Criteria

```bash
rg "legacy_metadata|legacy_configs|metadata.*tmdb|metadata\]\[|_get_real_config_value" media_importer tests docs
```

- [ ] 运行时代码无旧 Provider 配置兼容。

## Phase 6: Remove type/media_type Compatibility

### Goal

刮削结果统一使用 `media_type`，删除旧 `type` alias。

### Files

- `media_importer/features/import_flow/services/review.py`
- `media_importer/features/import_flow/context.py`
- `media_importer/features/import_flow/steps/scrape.py`
- `media_importer/api/*`
- `media_importer/webui/js/*`
- `tests/test_scrape_result_contract.py`
- API docs

### Tasks

- [ ] 删除所有 `result.get("type") or result.get("media_type")`。
- [ ] 删除写入 `type` 的代码。
- [ ] 删除旧 `type` 兼容测试。
- [ ] API 文档只声明 `media_type`。
- [ ] 注意不要误删 HTML input `type` 或 TMDB 原始返回中的非业务字段。

### Acceptance Criteria

```bash
rg "get\(\"type\"|get\('type'|\[\"type" media_importer tests docs
```

- [ ] 只允许非刮削媒体类型语义的前端 HTML/DOM 用法。
- [ ] `tests/test_scrape_result_contract.py` 改为只验证 `media_type`。

## Phase 7: Remove Legacy Task Status Aliases

### Goal

任务状态只使用当前 status/stage 模型，删除旧状态别名。

### Files

- `media_importer/core/task_lifecycle.py`
- `media_importer/core/db/constants.py`
- `media_importer/core/db/migrations.py`
- task/status tests
- task lifecycle docs

### Tasks

- [ ] 删除 `STATUS_PROCESSING`、`STATUS_CONFIRMING`、`STATUS_NEEDS_REVIEW` 旧别名。
- [ ] 删除 legacy status migration。
- [ ] 删除测试中的 legacy status 输入。
- [ ] 更新文档，只描述当前状态模型。

### Acceptance Criteria

```bash
rg "STATUS_PROCESSING|STATUS_CONFIRMING|STATUS_NEEDS_REVIEW|legacy status|旧状态|CONFIRMING|NEEDS_REVIEW" media_importer tests docs
```

- [ ] 运行时代码不再引用旧状态常量。

## Phase 8: Enforce Provider SearchResult Contract

### Goal

Provider `search()` 必须返回 `SearchResult(items=...)`，删除 list 返回兼容。

### Files

- `media_importer/features/providers/base.py`
- `media_importer/features/providers/*_provider.py`
- `media_importer/features/scraping/match_engine.py`
- provider/match tests

### Tasks

- [ ] 更新 Provider base docstring，声明 `search()` 返回 `SearchResult`。
- [ ] 删除 `match_engine.py` 中对 list 返回的兼容分支。
- [ ] 修改所有 mock Provider 测试，统一返回 `SearchResult`。
- [ ] 删除“兼容旧 list 格式返回”测试。

### Acceptance Criteria

```bash
rg "兼容 SearchResult|旧 list|list 格式返回|isinstance\(.*SearchResult" media_importer tests
```

- [ ] 不再有 list 兼容逻辑。
- [ ] 真实 SearchResult 测试通过。

## Phase 9: Squash Config And DB Migrations

### Goal

既然没有历史用户，配置和 DB 初始化直接创建当前最终结构，删除尚未上线版本之间的迁移链。

### Preconditions

- [ ] 明确本地开发 DB 可删除或已备份。
- [ ] Phase 1-8 已完成，旧字段不再被运行时读取。

### Files

- `media_importer/core/config_loader.py`
- `media_importer/core/config_migrations.py`
- `media_importer/core/db/connection.py`
- `media_importer/core/db/migrations.py`
- `media_importer/core/db/constants.py`
- config/db migration tests

### Tasks

- [ ] 删除旧配置迁移函数。
- [ ] 默认 config 直接包含当前最终字段。
- [ ] DB `CREATE TABLE` 直接是最终 schema。
- [ ] 删除为旧列补 ALTER 的迁移。
- [ ] 保留未来可用的 `schema_version` 框架，若当前已有且简单可保留。
- [ ] 删除旧迁移测试，新增“空库初始化就是最终 schema”测试。

### Acceptance Criteria

```bash
rg "migrate|migration|v2|v3|旧配置|历史配置|backward|compat" media_importer/core tests docs
```

- [ ] 只允许当前 schema 初始化和未来版本框架，不允许旧版本迁移链。

## Phase 10: Remove Frontend Placeholders And Legacy Wrappers

### Goal

清理无入口的旧前端文件、占位 JS、legacy wrapper 包和文档说明。

### Files

- `media_importer/webui/js/cinema-confidence.js`
- `media_importer/webui/js/confidence-detail.js`
- `media_importer/webui/index.html`
- `media_importer/webui/partials/advanced-pages.html`
- `media_importer/storage/**`
- `media_importer/core/recycle/**`
- `docs/INDEX.md`
- `docs/legacy.md`

### Tasks

- [ ] 删除 `cinema-confidence.js` 和 script 引用。
- [ ] 将 `confidence-detail.js` 重命名为 `match-trace-detail.js`，更新所有引用。
- [ ] 删除无 HTML 引用的旧 JS/CSS。
- [ ] 检查 `storage/` 和 `core/recycle/` wrapper 是否仍被 import。
- [ ] 如果无运行时 import，删除 wrapper 包。
- [ ] 更新 docs/INDEX，把 legacy wrapper 描述移除。

### Acceptance Criteria

```bash
rg "cinema-confidence|confidence-detail|legacy wrapper|compatibility wrapper|core/recycle|media_importer\.storage" media_importer tests docs
```

- [ ] 运行时代码无旧占位文件引用。

## Final Validation

执行完整验证：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer tests

python -m pytest tests/test_no_legacy_compat_surface.py
python -m pytest tests/test_prompt_resolver_integration.py tests/test_prompt_runtime.py
python -m pytest tests/test_scrape_preview_job.py tests/test_match_engine_real_search_result.py
python -m pytest tests/test_match_engine.py tests/test_match_pipeline_integration.py
python -m pytest tests/ --ignore=tests/test_scrape_ui.py --ignore=tests/test_frontend_config.py
```

最终 grep：

```bash
rg "legacy|deprecated|向后兼容|历史兼容|scraper_prompts|tmdb_prompts|ConfidenceEngine|ConfidenceResult|scrape_confidence|LLMConfig|STATUS_CONFIRMING|STATUS_NEEDS_REVIEW|STATUS_PROCESSING|body_before_params|pass_self|prompt-config|prompt-tmdb|provider_ai|ai_only" media_importer tests
```

期望：

- `media_importer/**` 无旧兼容入口。
- `tests/**` 不再保护旧行为，只允许 guard 中出现禁止词。
- `docs/_archive/**` 可保留历史说明。
- 当前事实文档只描述新方案。

## Handoff Instructions For Execution Model

执行模型必须遵守：

1. 先读本计划和 `AGENTS.md`。
2. 从 Phase 0 开始，按顺序执行。
3. 每完成一个 Phase，运行该 Phase 的 grep 和相关测试。
4. 不要一次性做全部阶段的大 diff；如果某阶段失败，先修该阶段。
5. 不要新增兼容层替代旧兼容层。
6. 不要修改 `deploy/`、`.env*`、`.config*`、`opencode.json*`。
7. 遇到业务 fallback 时不要误删：`fallback_dir`、Provider 语言 fallback、图片 fallback、搜索 fallback 是业务能力，不是历史兼容。
8. 完成后报告：每个 Phase 的完成状态、删除的入口、剩余 grep 命中及理由、测试结果。
