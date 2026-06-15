---
title: "fix: AI config redesign completion"
type: plan
date: 2026-06-13
status: approved-for-implementation
confidence: high
related:
  - docs/design/2026-06-13-ai-config-redesign.md
  - docs/plans/2026-06-13-ai-config-redesign-implementation-plan.md
  - docs/decisions/0005-three-tier-matching.md
---

# AI 配置重设计完成计划

一行摘要：把 AI 配置重设计从“UI 和基础字段已落地”推进到“后端契约、三级匹配、三级维度确认、提示词运行时、文档和测试全部闭环”。

## Problem Statement

当前 `2026-06-13-ai-config-redesign.md` 和 `2026-06-13-ai-config-redesign-implementation-plan.md` 已完成部分基础开发，但评审发现仍存在以下阻塞验收的问题：

- `ai_search.search_type` 已在 UI 和配置中保存，但运行时请求注入未使用。
- `ai_assist` 和 `ai_search` 职责没有真正分离，部分维度映射会优先走联网搜索模型。
- 第二级匹配仍是 AI 从候选中直接选中，而不是 AI 建议关键词后回到 Provider 搜索。
- `dim_sources` 是临时推断，不是逐维度真实来源追踪。
- Provider-only 结果使用 `media_type`，部分验证逻辑仍只读取 `type`。
- `confirm_reason` 没有作为最终事实字段完整持久化。
- 用户配置的提示词尚未全面接入运行时。
- ADR、方案、计划、API 文档和实现之间存在不一致。

这些问题会导致配置页看似可用，但实际刮削、来源追踪、确认原因和扩展能力无法按方案验收。

## Target End State

- ADR、方案、计划、代码、测试和文档对三级匹配与三级维度确认达成一致。
- `ai_assist` 只负责轻量辅助任务，`ai_search` 只负责缺失维度联网补全。
- `search_type` 真实影响不同 Provider 的联网搜索请求参数。
- 第二级匹配采用“AI 建议关键词 -> Provider 重新搜索 -> 唯一精确匹配才自动通过”。
- 维度来源按维度真实记录为 `provider:tmdb`、`provider:douban`、`ai_assist`、`ai_search`、`file` 或 `unknown`。
- AI 来源维度根据 `trust_ai_assist` / `trust_ai_search` 决定是否进入人工确认。
- `confirm_reason` 能写入 DB、API 返回、UI 展示，并在重启后保留。
- 用户在 UI 中配置的提示词实际进入运行时调用。
- 新增 API、配置字段和流程变更已同步架构文档、API 文档和索引。

## Scope

- 后端 AI 配置运行时接入。
- 三级匹配和三级维度确认核心逻辑。
- 任务确认原因和维度来源持久化。
- 提示词默认值与用户提示词运行时解析。
- AI 配置相关 UI 验收修正。
- ADR、方案、计划和 API 文档同步。
- 单元测试、集成测试和必要 UI 验收测试。

## Non-Goals

- 不重做整个前端配置页视觉设计。
- 不引入新的外部 AI SDK。
- 不实现尚未支持的豆包、OpenAI、自部署搜索 Provider，除非只做扩展点预留。
- 不修改 `deploy/` 生成副本。
- 不修改 `.env*`、`.config*`、`opencode.json*`。
- 不回滚用户已有改动。
- 不重新设计整个 Provider 架构。

## Execution Principles

- 先写失败测试，再修实现。
- 先统一契约，再改业务逻辑。
- 后端核心链路优先于 UI 微调。
- 每一阶段都必须能独立验证。
- `features/` 是业务事实源，`scraper/` 是迁移期旧实现；新增核心策略优先落到 `features/scraping/`。
- 不做大规模无关重构。

## Proposed Solution

按依赖顺序分阶段推进：

1. 冻结 ADR 和字段契约，消除方案冲突。
2. 补充 RED 测试锁住关键缺陷。
3. 修复 AI 搜索配置运行时，尤其是 `search_type` 注入。
4. 统一 `media_type/type` 契约并持久化 `confirm_reason`。
5. 拆分 `ai_assist` 和 `ai_search` 调用路径。
6. 新增正式维度解析服务，替代 `_infer_dim_sources()`。
7. 重构第二级匹配为关键词建议回搜。
8. 接入提示词运行时解析。
9. 清理旧 `ai_only` / 旧置信度 / 旧 `llm` 表面入口的一致性问题。
10. 完成 UI 验收和文档同步。
11. 跑最终回归。

## Decision Rationale

- 选择先冻结契约，是因为当前 ADR 与方案 v6 对第二级匹配定义不同。直接继续实现会导致不同模型按不同理解改代码。
- 选择先补 RED 测试，是因为现有测试只覆盖基础迁移和默认注入，未覆盖 `search_type`、调用顺序、来源追踪、确认原因持久化等关键验收点。
- 选择新增维度解析服务，是因为 `_step_scrape()` 临时推断维度来源违反 feature-first 架构，且无法扩展多 Provider、证据链和信任判断。
- 选择拆分 `ai_assist` / `ai_search` 调用路径，是因为旧 `_retry_with_fallback(use_fast=True)` 把业务顺序藏在 fallback 中，难以测试、难以扩展，也会误调用联网搜索。
- 选择短期兼容 `type` 和 `media_type`，是为了避免一次性破坏旧调用点；长期应统一到 `media_type`。

## Constraints and Boundaries

- 删除或覆盖影视文件必须走回收站，本计划不涉及文件删除逻辑。
- API 返回敏感配置前必须脱敏为 `***`。
- 新增 API 必须同步 `docs/architecture/api.md`、`docs/standards/api.md` 和 `docs/INDEX.md`。
- API handler 只能薄调用 feature service，不能承载复杂业务策略。
- 前端 CSS 使用变量体系，不硬编码颜色。
- 前端 JS 尽量按既有原生模块模式扩展，不引入构建链。

## Assumptions

| Assumption | Status | Evidence |
|---|---|---|
| 当前目标是完成既有方案，而不是重新设计 AI 配置方向 | Verified | 用户明确要求“把这个方案和计划完全落地” |
| `features/scraping/` 可以承载新匹配和维度解析事实源 | Verified | 仓库 AGENTS.md 指定 feature-first，当前已有 `match_engine.py`、`web_search_config.py` |
| `scraper/` 仍可作为迁移期旧实现被调用 | Verified | 当前 `metadata_scrape_flow.py`、`llm_scraper.py` 仍在运行链路中 |
| `media_type` 是更合适的长期字段 | Verified | Provider models 和 Provider-only 结果已使用 `media_type` |
| 所有新增测试都可以 mock LLM 和 Provider，不依赖真实外部 API | Verified | 现有 `tests/test_llm_web_search.py` 已用 mock/直接 payload 检查模式 |
| UI 页签修改状态 `•` 是否必须实现 | Unverified | 方案提到该验收项，但当前实现状态不完整，需要 Phase 9 决定补齐或调整验收口径 |

## Risk Analysis

| Risk | Impact | Mitigation |
|---|---|---|
| 一次性改动过大导致主流程不稳定 | 高 | 按 Phase 分批，每阶段跑对应测试 |
| 新维度解析服务和旧 `metadata_scrape_flow.py` 边界不清 | 中 | 先定义输入输出契约，再最小接入旧流程 |
| 多 Provider 来源格式后续扩展不一致 | 中 | 统一 `provider:{provider_type}` 格式 |
| 提示词配置接入后改变历史刮削行为 | 中 | 留空使用默认值，用户配置才改变行为 |
| AI 二级关键词回搜导致调用次数增加 | 中 | 限制最多 2 次回搜，trace 记录过程 |
| 历史 UI 测试已有失败干扰验收 | 中 | 最终报告区分历史失败和本次新增失败 |

## Phased Implementation

### Phase 0: 冻结架构契约

目标：消除方案、ADR、代码之间的不一致。

任务：

- [ ] 更新或新增 ADR，明确第二级匹配采用“AI 建议关键词 -> Provider 重新搜索 -> 唯一精确匹配才自动通过”。
- [ ] 在 ADR 中明确废弃“AI 从候选中直接选中并自动通过”的旧策略。
- [ ] 定义刮削结果统一字段契约：推荐统一 `media_type`，短期兼容 `type`。
- [ ] 定义 `dim_sources` 最低结构：`{ "dimension_name": "provider:tmdb|provider:douban|ai_assist|ai_search|file|unknown" }`。
- [ ] 定义后续扩展结构：`source_label`、`evidence`、`trusted` 暂不强制，但服务设计要预留。
- [ ] 明确 `ai_assist` 只做标题清洗、匹配关键词建议、复杂维度映射、源目录清理。
- [ ] 明确 `ai_search` 只做缺失维度联网补全，不能作为作品刮削兜底。

验收标准：

- [ ] `docs/decisions/0005-three-tier-matching.md` 或新 ADR 与方案 v6 一致。
- [ ] `docs/design/2026-06-13-ai-config-redesign.md` 不再和 ADR 冲突。
- [ ] 后续执行者不需要猜 `type/media_type`、`dim_sources`、二级匹配策略。

### Phase 1: 补 RED 测试

目标：让关键缺陷先被测试锁住。

建议新增或扩展测试文件：

| 文件 | 目标 |
|---|---|
| `tests/test_ai_config_runtime.py` | AI 配置运行时生效 |
| `tests/test_dimension_resolution.py` | 三级维度来源和信任判断 |
| `tests/test_match_engine_keyword_loop.py` | 第二级关键词建议回搜 |
| `tests/test_task_confirm_reason.py` | `confirm_reason` 持久化 |
| `tests/test_prompt_runtime.py` | 用户提示词实际被使用 |
| `tests/test_scrape_result_contract.py` | `media_type/type` 字段兼容 |

必须覆盖的测试用例：

- [ ] `ai_search.search_type="search_pro"` 时，智谱 payload 包含 `search_type: "search_pro"`。
- [ ] `ai_search.search_type="forced_search"` 时，通义 payload 包含 `enable_search=True` 和 `search_options.forced_search=True`。
- [ ] `ai_search.enabled=false` 时，任何维度补全都不能调用联网搜索模型。
- [ ] 同时配置 `ai_assist` 和 `ai_search` 时，复杂维度映射先调用 `ai_assist.model`。
- [ ] Provider 已给出 `media_type` 但没有 `type` 时，验证服务不能判定媒体类型缺失。
- [ ] `NEEDS_CONFIRM` 最终任务 DB 中 `confirm_reason` 非空。
- [ ] `dim_sources` 必须按维度记录真实来源，不能因为 `ai_invoked=True` 把所有维度推断成 `ai_assist`。
- [ ] 用户配置 `ai_assist.prompt_match_assist` 后，二级匹配调用使用用户提示词。
- [ ] 用户配置 `ai_search.prompt_dimension_supplement` 后，联网维度补全使用用户提示词。
- [ ] 二级匹配中 AI 返回 `suggested_query` 后，系统必须重新调用 Provider 搜索。
- [ ] 二级回搜结果不是唯一精确匹配时，不能自动通过，必须 `NEEDS_CONFIRM`。

验收标准：

- [ ] 新增测试在修复前应失败。
- [ ] 不允许为了通过测试修改测试断言迎合现有错误行为。
- [ ] 测试不依赖真实外部 API，必须 mock LLM 和 Provider。

### Phase 2: 修复 AI 搜索配置运行时

目标：让 UI 保存的 `ai_search` 配置真实影响请求。

涉及文件：

| 文件 | 改动方向 |
|---|---|
| `media_importer/scraper/llm_scraper.py` | `_inject_search()` 使用 `effective_search_type()` |
| `media_importer/features/scraping/web_search_config.py` | 校验和默认搜索类型 |
| `tests/test_llm_web_search.py` | 增补 `search_type` 注入测试 |

任务：

- [ ] 修改 `_inject_search()`，不要只按 provider 注入默认参数。
- [ ] 智谱 `search_std/search_pro` 映射到 `tools.web_search.search_type`。
- [ ] 通义 `enable_search/forced_search` 映射到 `enable_search` 和 `search_options`。
- [ ] Moonshot 保持 `$web_search` 工具注入。
- [ ] 未配置 `search_type` 时使用 `DEFAULT_SEARCH_TYPE`。
- [ ] 未知 provider 或 disabled 时不注入搜索参数。

验收标准：

- [ ] `tests/test_llm_web_search.py` 通过。
- [ ] 新增 `search_type` 测试通过。
- [ ] UI 改“搜索类型”后，后端 payload 可被测试观察到变化。

### Phase 3: 统一刮削结果契约和确认原因

目标：修复 `media_type/type` 混用和 `confirm_reason` 丢失。

涉及文件：

| 文件 | 改动方向 |
|---|---|
| `media_importer/features/import_flow/services/review.py` | 兼容 `media_type` |
| `media_importer/features/import_flow/context.py` | 兼容 `media_type` |
| `media_importer/features/import_flow/steps/scrape.py` | 不覆盖具体确认原因 |
| `media_importer/core/task_lifecycle.py` | `mark_confirming()` 写入 `confirm_reason` |
| `media_importer/core/db/task_repo.py` | 确认读写保持 JSON/文本正确 |

任务：

- [ ] `ReviewDecisionService._validate_required_fields()` 使用 `scraped.get("type") or scraped.get("media_type")`。
- [ ] `TaskContext` 和 `_step_scrape()` 同步兼容 `media_type`。
- [ ] `mark_confirming(task, reason)` 返回字段中加入 `confirm_reason=reason`。
- [ ] `_step_validate()` 不能无条件覆盖 `_confirm_reason` 中已有的 trust 具体原因。
- [ ] `NEEDS_CONFIRM` 时优先使用 `scraped.confirm_reason`，其次 `task._confirm_reason`，最后 concerns 文案。
- [ ] `error_message` 可以保留展示用途，但不能替代 `confirm_reason` 事实字段。

验收标准：

- [ ] Provider-only 结果不会因为缺 `type` 被误判。
- [ ] 待确认任务重启后仍能展示 `confirm_reason`。
- [ ] DB `tasks.confirm_reason` 与 API 返回一致。

### Phase 4: 拆分 AI 辅助和 AI 联网搜索职责

目标：停止用 `_retry_with_fallback(use_fast=True)` 混合 `ai_assist` 和 `ai_search`。

建议新增：

| 文件 | 职责 |
|---|---|
| `media_importer/features/scraping/ai_clients.py` | 可选，封装辅助模型和搜索模型调用 |
| `media_importer/features/scraping/prompt_resolver.py` | 统一解析用户提示词和默认提示词 |
| `media_importer/features/scraping/dimension_resolution.py` | 三级维度确认服务 |

任务：

- [ ] 增加明确的 `call_ai_assist()` 路径，只使用 `ai_assist.base_url/model/api_key`。
- [ ] 增加明确的 `call_ai_search()` 路径，只使用 `ai_search`，且必须检查 `enabled`。
- [ ] `scrape_with_context()` 不再通过 `use_fast=True` 优先尝试搜索模型。
- [ ] 标题清洗、匹配辅助、维度映射、源目录清理默认走 `ai_assist`。
- [ ] 缺失维度联网补全默认走 `ai_search`。
- [ ] `ai_search.enabled=false` 时不能调用联网搜索模型，即使配置了 key/model。

验收标准：

- [ ] 辅助模型和联网搜索模型调用顺序由测试明确验证。
- [ ] 关闭 AI 联网搜索增强后，后端不会注入 web search 参数。
- [ ] 不再通过失败 fallback 实现业务顺序。

### Phase 5: 正式落地三级维度确认

目标：用真实来源追踪替代 `_infer_dim_sources()` 临时推断。

涉及文件：

| 文件 | 改动方向 |
|---|---|
| `media_importer/features/scraping/dimension_resolution.py` | 新业务事实源 |
| `media_importer/scraper/metadata_scrape_flow.py` | 调用维度解析服务 |
| `media_importer/features/import_flow/steps/scrape.py` | 只保存结果，不推断来源 |
| `media_importer/core/db/dimension_repo.py` | 读取信任配置 |
| `media_importer/core/db/task_repo.py` | 保存真实 `dim_sources` |

推荐服务接口：

```python
class DimensionResolutionResult:
    dimensions: dict
    dim_sources: dict
    confirm_reason_parts: list
```

处理顺序：

- [ ] 第一级：Provider 直接映射，成功则来源为 `provider:{provider_type}`。
- [ ] 第二级：Provider 有数据但规则无法确定时，调用 AI 辅助映射，成功则来源为 `ai_assist`。
- [ ] 第三级：仍缺失且 `ai_search.enabled=true` 时，调用 AI 联网搜索补全，成功则来源为 `ai_search`。
- [ ] 文件分析维度优先来源为 `file`。
- [ ] 未得到值的维度来源为 `unknown`。
- [ ] 每个 AI 来源维度都根据 `trust_ai_assist/trust_ai_search` 生成确认原因。
- [ ] 缺失必需维度时生成确认原因。
- [ ] 删除或废弃 `_infer_dim_sources()` 临时逻辑。

验收标准：

- [ ] `dim_sources` 每个维度的来源真实可追踪。
- [ ] 多 Provider 来源格式支持 `provider:tmdb`、`provider:douban`。
- [ ] 不信任 AI 辅助时，AI 辅助补出的维度进入待确认。
- [ ] 不信任 AI 联网搜索时，联网补出的维度进入待确认。
- [ ] Provider 直接映射维度不受 AI 信任开关影响。

### Phase 6: 重构第二级匹配为关键词建议回搜

目标：让匹配流程符合 v6 方案和新 ADR。

涉及文件：

| 文件 | 改动方向 |
|---|---|
| `media_importer/features/scraping/match_engine.py` | 二级流程改成关键词建议回搜 |
| `media_importer/scraper/llm_scraper.py` | `tier2_judge()` 改造或新增 `suggest_search_query()` |
| `media_importer/features/scraping/match_models.py` | 增加建议关键词、`confirm_reason` 等字段 |
| `tests/test_match_engine_keyword_loop.py` | 覆盖二级回搜 |

任务：

- [ ] 将 `tier2_judge()` 改为返回 `{ "suggested_query", "confidence", "reason" }`。
- [ ] `MatchEngine._tier2_context_match()` 调用 AI 获取关键词建议。
- [ ] 使用建议关键词重新调用 Provider 搜索。
- [ ] 只有唯一 L1/L2 精确匹配才 `AUTO_PASS`。
- [ ] 回搜仍无精确匹配时，取候选排名第一进入 `NEEDS_CONFIRM`，不能自动入库。
- [ ] 最多循环 2 次，避免无限搜索。
- [ ] trace 中记录每次建议关键词和回搜结果。
- [ ] concerns 中保留 AI 建议失败、回搜无结果、多候选等原因。

验收标准：

- [ ] AI 不再从候选中直接选中并自动通过。
- [ ] 二级匹配成功必须经过 Provider 回搜验证。
- [ ] trace 能展示“AI 建议关键词 -> Provider 回搜”的过程。
- [ ] 模拟刮削页面能看到新的 trace 信息。

### Phase 7: 提示词运行时接入

目标：让 UI 中的提示词配置真实影响运行时。

建议新增：

| 文件 | 职责 |
|---|---|
| `media_importer/features/scraping/prompt_resolver.py` | 提示词解析 |
| `tests/test_prompt_runtime.py` | 提示词运行时测试 |

提示词优先级：

| 优先级 | 来源 |
|---|---|
| 1 | `ai_assist.prompt_title_clean` 等用户配置 |
| 2 | legacy `config/scraper_prompts.md`，仅维度映射兼容 |
| 3 | `PromptDefaults` |

任务：

- [ ] 标题清洗接入 `prompt_title_clean`。
- [ ] 匹配辅助接入 `prompt_match_assist`。
- [ ] 维度映射接入 `prompt_dimension_mapping`。
- [ ] 源目录清理接入 `prompt_source_clean` 或与 `source_cleaner.ai_prompt` 明确优先级。
- [ ] 缺失维度搜索接入 `prompt_dimension_supplement`。
- [ ] 空字符串视为使用默认值。
- [ ] “恢复默认”填入的是默认值，但保存空字符串仍表示运行时默认值。

验收标准：

- [ ] 用户配置提示词后，mock LLM 调用能观察到实际使用该提示词。
- [ ] 留空时使用 `PromptDefaults`。
- [ ] legacy 维度映射提示词仍兼容。

### Phase 8: 清理旧模式和一致性收尾

目标：移除或隔离旧 `ai_only`、旧置信度、旧 `llm` 表面入口。

任务：

- [ ] `metadata.scrape_mode` 不再作为主动运行入口。
- [ ] `ai_only` 分支若保留，只允许作为兼容保护，不应从 UI 或配置主动触发。
- [ ] 文档中不再描述 AI-only 为正常流程。
- [ ] 前端 `buildLlmConfigPayload()` 仅保留 demo 兼容时，要明确不会写回正式配置。
- [ ] 配置阶段状态 `hasAi` 改为基于 `ai_assist` / `ai_search`，不要只看旧 `llm`。
- [ ] 检查 `confidence` 旧 UI 和文档是否还误导用户。

验收标准：

- [ ] 新用户不用配置旧 `llm` 也能启动和保存配置。
- [ ] 旧配置迁移后新字段生效。
- [ ] UI 不再暗示旧置信度公式仍是主流程。

### Phase 9: UI 和模拟刮削验收

目标：确认前端展示和后端真实数据一致。

任务：

- [ ] 配置页不再出现可编辑“刮削模式”下拉。
- [ ] AI 辅助保存后刷新保留 `base_url/model/api_key`。
- [ ] AI 联网搜索增强保存后刷新保留 `enabled/provider/model/search_type/api_key`。
- [ ] 开关关闭后禁用下方输入，并且后端不调用搜索。
- [ ] 维度配置保存 `trust_ai_assist/trust_ai_search` 后刷新保留。
- [ ] 任务卡片“刮削过程”显示真实 `dim_sources`。
- [ ] 模拟刮削展示每个维度来源，不再只展示维度值。
- [ ] 页签修改状态 `•` 如方案要求未实现，则补齐或从验收标准中删除。
- [ ] 无 JS 控制台错误。

验收标准：

- [ ] 后端 API 返回和 UI 展示一致。
- [ ] UI 不展示后端尚未实现的能力。
- [ ] 模拟刮削能覆盖 Provider-only、AI辅助补维度、AI搜索补维度、待确认四类场景。

### Phase 10: 文档同步

目标：满足仓库 Change Impact Rules。

必须更新：

| 文件 | 内容 |
|---|---|
| `docs/INDEX.md` | 收录新方案和计划 |
| `docs/architecture/api.md` | 新增 `/api/config/prompt-defaults` |
| `docs/standards/api.md` | 记录敏感字段、prompt-defaults、config section 规范 |
| `docs/architecture/scraping.md` | 同步三级匹配和三级维度确认 |
| `docs/design/2026-06-13-ai-config-redesign.md` | 更新真实完成状态 |
| `docs/plans/2026-06-13-ai-config-redesign-implementation-plan.md` | 勾选真实完成项，移除过期 Hot Fix 状态 |

验收标准：

- [ ] 文档不引用归档内容作为当前事实。
- [ ] 文档状态和代码状态一致。
- [ ] 新 API 已记录。
- [ ] 新配置字段已记录。
- [ ] ADR 与实现一致。

### Phase 11: 最终回归

建议命令：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer tests
python -m pytest tests/test_config_migration_v3.py
python -m pytest tests/test_llm_web_search.py
python -m pytest tests/test_architecture_guards.py
python -m pytest tests/test_ai_config_runtime.py
python -m pytest tests/test_dimension_resolution.py
python -m pytest tests/test_match_engine_keyword_loop.py
python -m pytest tests/test_task_confirm_reason.py
python -m pytest tests/test_prompt_runtime.py
python -m pytest tests/test_scrape_result_contract.py
```

非 UI 回归建议：

```bash
python -m pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py
```

UI 验收建议：

- [ ] 启动本地服务。
- [ ] 打开配置页。
- [ ] 保存 AI 辅助配置。
- [ ] 保存 AI 联网搜索增强配置。
- [ ] 切换搜索类型并保存。
- [ ] 关闭 AI 联网搜索增强并保存。
- [ ] 保存维度信任开关。
- [ ] 运行模拟刮削。
- [ ] 查看任务卡片刮削过程。
- [ ] 检查浏览器控制台无错误。

## Acceptance Criteria

- [ ] ADR、方案、计划、实现一致。
- [ ] `ai_assist` / `ai_search` 运行时职责完全分离。
- [ ] `search_type` 真实影响请求参数。
- [ ] AI 联网搜索增强关闭后不会调用联网搜索。
- [ ] Provider-only 结果不会因 `type/media_type` 混用失败。
- [ ] 维度来源逐维度真实可追踪。
- [ ] 不信任 AI 来源会生成并持久化 `confirm_reason`。
- [ ] 第二级匹配通过 Provider 回搜验证，而不是 AI 直接选候选。
- [ ] 用户提示词配置真实进入运行时。
- [ ] 新 API 和配置字段已同步文档。
- [ ] 编译、核心单测、架构护栏通过。
- [ ] 已知历史失败与本次变更无关，并在测试报告中说明。

## References

- `docs/design/2026-06-13-ai-config-redesign.md`
- `docs/plans/2026-06-13-ai-config-redesign-implementation-plan.md`
- `docs/decisions/0005-three-tier-matching.md`
- `media_importer/features/scraping/match_engine.py`
- `media_importer/features/scraping/web_search_config.py`
- `media_importer/scraper/llm_scraper.py`
- `media_importer/scraper/metadata_scrape_flow.py`
- `media_importer/features/import_flow/steps/scrape.py`

## Handoff Prompt

可直接给执行模型使用：

```text
请按 docs/plans/2026-06-13-ai-config-redesign-completion-plan.md 执行。先写 RED 测试，再实现。不要修改 deploy/、.env*、.config*、opencode.json*。不要回滚用户已有改动。优先修后端核心契约：search_type 注入、ai_assist/ai_search 职责分离、media_type/type 兼容、confirm_reason 持久化、真实 dim_sources、二级关键词回搜。每完成一个 Phase 跑对应测试，并在最终回复列出测试命令和结果。
```
