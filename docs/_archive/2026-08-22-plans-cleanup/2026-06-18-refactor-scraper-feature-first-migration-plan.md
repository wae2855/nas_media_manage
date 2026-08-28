---
title: "refactor: scraper feature-first migration"
type: plan
date: 2026-06-18
status: pending-review
confidence: medium
parent_plan: docs/plans/2026-06-18-refactor-cleanup-and-migration-sequencing-plan.md
adr: docs/decisions/0008-scraper-feature-first-migration.md
related:
  - docs/decisions/0004-feature-first-architecture-restructure.md
  - docs/decisions/0005-three-tier-matching.md
  - docs/decisions/0007-information-responsibility-split.md
  - docs/standards/scrape-matching.md
  - docs/standards/info-architecture.md
  - docs/architecture/scraping.md
  - docs/features/scraping.md
---

# Scraper Feature-First 迁移子计划

一行摘要:把 `media_importer/scraper/` 中仍承担真实刮削职责的模块按能力迁入 `features/scraping`、`features/providers`、`features/prompts`,并用后端契约测试与前端触发 smoke 保护每个切片。

> 本计划只定义迁移方案。未经过用户确认前,不执行代码移动、导入替换或测试命令。

---

## 1. Problem Statement

当前项目名义上已经采用 feature-first 架构,但刮削能力仍有大量真实实现位于旧目录 `media_importer/scraper/`。这导致:

- 维护者查找刮削逻辑时需要同时看 `features/scraping`、`features/providers` 和 `scraper`。
- 三级匹配、AI 提示词、Provider 客户端、元数据流程的职责边界不直观。
- 后续修改可能绕过 ADR-0007 的 6 层信息职责契约。
- 前端“重新刮削 / Provider 测试 / 模拟器”等入口难以和后端模块建立稳定映射。

---

## 2. Target End State

迁移完成后应满足:

- 生产代码不再直接 import `media_importer.scraper.*`。
- `features/scraping` 是刮削匹配、LLM 辅助、元数据编排事实源。
- `features/providers` 是 TMDB/Provider 客户端事实源。
- `features/prompts` 是提示词与 prompt 组装事实源。
- 旧 `scraper/` 本阶段只保留明确标记的兼容 re-export,并用架构 guard 防止新增依赖;最终删除另走后续清理计划。
- 正式任务、模拟器、Provider 测试、任务详情重新刮削都通过前后端测试验证。

---

## 3. Scope

### In Scope

- 迁移 `filename_cleaner.py`、`title_matcher.py`。
- 迁移 `tmdb_client.py` 和 Provider 相关异常类型。
- 迁移 LLM 客户端与 LLM 刮削辅助逻辑。
- 迁移并拆分 `metadata_scrape_flow.py`。
- 迁移 source cleaning 中复用的 prompt 组装依赖。
- 增加架构 guard,禁止新生产代码 import `media_importer.scraper.*`。
- 增加或修正后端契约测试、API 测试、Playwright 前端触发 smoke。

### Non-Goals

- 不改变三级匹配业务语义。
- 不改变 `MatchResult.to_dict()` 字段契约。
- 不改变 AI prompt 的输出 schema,除非标准文档同步更新。
- 不重做前端 UI。
- 不迁移 `core.db`。DB 入口迁移由父计划 Phase 5 管理。

---

## 4. Migration Map

| 当前模块 | 目标模块 | 迁移类型 | 业务职责 |
|----------|----------|----------|----------|
| `scraper/filename_cleaner.py` | `features/scraping/filename_cleaner.py` | move + compat re-export | 文件名清洗 |
| `scraper/title_matcher.py` | `features/scraping/title_matcher.py` | move + compat re-export | 标题相似度与匹配等级 |
| `scraper/tmdb_client.py` | `features/providers/tmdb_client.py` | move + compat re-export | TMDB HTTP 客户端 |
| `scraper/providers/*` | `features/providers/*` | consolidate | Provider 抽象与实现 |
| `scraper/_llm_client_impl.py` | `features/scraping/llm_client.py` | move + rename | LLM HTTP 调用执行能力 |
| `scraper/llm_scraper.py` | `features/scraping/llm_scraper.py` | move + compat re-export | LLM 标题/维度辅助 |
| `scraper/_llm_match_assist.py` | `features/prompts/match_assist.py` + `features/scraping/llm_match_assist.py` | split | Prompt 组装 + match assist 执行 |
| `scraper/metadata_scrape_flow.py` | `features/scraping/metadata_flow/` | split | 正式任务元数据刮削编排 |
| `scraper/metadata_scraper.py` | compare with `features/scraping/metadata_scraper.py`, then merge/archive | audit + merge/archive | 旧元数据刮削包装 |
| `scraper/dimension_manager.py` | compare with `features/scraping/dimension_manager.py`, then merge/archive | audit + merge/archive | 旧维度管理包装 |
| `scraper/exceptions.py` | 按归属迁到 `features/scraping/errors.py` / `features/providers/errors.py` | split | 异常类型 |
| `scraper/__init__.py` | 改造为 compat re-export 集散点,不移动文件内容 | refactor in place | 旧包兼容入口 |

目标命名在执行前可微调,但必须保持“业务能力归属清晰”。

---

## 5. Phased Implementation

> **注意**: 本子计划的 Phase 编号(Phase 0-5)独立于父计划。执行时请确认当前处于父计划 Phase 4(scraper 迁移),子计划内部再按 S-Phase 0 → S-Phase 5 推进。

### Phase 0: Inventory and Baseline

目标:迁移前明确所有依赖和测试基线。

- [ ] 列出所有生产 import: `media_importer.scraper.*`。
- [ ] 列出 `media_importer/scraper/` 下所有 `.py` 文件,包括当前无生产引用的文件。
- [ ] 按消费者分组: `features/scraping`、`features/providers`、`features/source_cleaning`、`features/prompts`、`api/connectivity_handlers.py`。
- [ ] 对每个 scraper 文件建立处置表: move / split / merge / compat re-export / archive / delete。
- [ ] 对当前无生产引用文件单独标注处置理由,不得在整包迁移中遗漏。
- [ ] 确认 `media_importer/scraper/` 内部文件间的导入方式(相对 import 还是绝对 import),用于决定各模块迁移时需更新哪些消费者路径。
- [ ] 建立测试基线:匹配、刮削预览、Provider、正式任务字段传递、前端触发 smoke。
- [ ] 标记历史失败,避免迁移时误判。

Exit Criteria:
- 有完整 import inventory。
- 有完整 scraper 文件处置表,无“未分类文件”。
- 每个迁移切片有对应测试清单。

### Phase 1: Cleaner and Matcher Slice

目标:先迁移纯逻辑模块,证明兼容 re-export 与 import 更新方式可行。

- [ ] 移动 `filename_cleaner.py` 到 `features/scraping/filename_cleaner.py`。
- [ ] 移动 `title_matcher.py` 到 `features/scraping/title_matcher.py`。
- [ ] 旧路径保留兼容 re-export,并标注 deprecated。
- [ ] 更新 `features/scraping/match_engine.py` 等消费者 import。
- [ ] 补 architecture guard 的 allowlist,迁移期间允许旧 compat 文件自身引用。

Backend Tests:
- [ ] filename cleaner 单测。
- [ ] title matcher 单测。
- [ ] `tests/test_match_engine.py`。

Frontend Smoke:
- [ ] 模拟器输入文件名后能展示清洗结果和匹配路径。

Exit Criteria:
- 纯逻辑模块迁移完成。
- 旧 import 兼容,新 import 生效。

### Phase 2: Provider Client Slice

目标:迁移 TMDB/Provider 客户端,保护外部数据入口。

- [ ] 移动 `tmdb_client.py` 到 `features/providers/tmdb_client.py`。
- [ ] 先对比 `scraper/providers/*` 与 `features/providers/*`,形成保留/合并/删除清单。
- [ ] 按清单合并或迁移 `scraper/providers/*` 到 `features/providers/*`,不得直接覆盖现有 feature 实现。
- [ ] 更新 `features/providers/tmdb_provider.py` 和 `api/connectivity_handlers.py`。
- [ ] 旧路径保留兼容 re-export。

Backend/API Tests:
- [ ] Provider 配置读取测试。
- [ ] TMDB 客户端 mock 测试。
- [ ] `/api/connectivity/provider` 或等价连通性测试。
- [ ] `tests/test_scrape_provider_first_e2e.py` 在环境允许时执行。

Frontend Smoke:
- [ ] 配置页 Provider 测试按钮可点击。
- [ ] 刮削与搜索测试入口可打开。
- [ ] Provider 搜索结果区域可渲染空态或结果态,无 console error。

Exit Criteria:
- Provider 客户端不再从 `scraper` 作为事实入口。
- 前端 Provider 入口仍可用。

### Phase 3: LLM Client and Prompt Slice

目标:迁移 LLM 调用与 prompt 组装,保持 AI 输出契约不变。

- [ ] 移动 `llm_scraper.py` 到 `features/scraping/llm_scraper.py`。
- [ ] 移动 `_llm_client_impl.py` 到 `features/scraping/llm_client.py`。
- [ ] 拆分 `_llm_match_assist.py`:prompt 组装进入 `features/prompts/match_assist.py`,匹配辅助执行逻辑进入 `features/scraping/llm_match_assist.py`。
- [ ] 更新 source cleaning 中对 prompt 组装的引用。
- [ ] 保持 AI prompt 输出 schema 与 `docs/standards/ai-prompt-design.md` 一致。

Backend/API Tests:
- [ ] LLM scraper mock 测试。
- [ ] AI prompt resolver/defaults 测试。
- [ ] source cleaning AI assist 测试。
- [ ] Tier 2 certainty/is_valid 测试。

Frontend Smoke:
- [ ] AI 配置页可加载 ai_assist / ai_search / prompts 区域。
- [ ] 提示词保存/重置入口无 JS error。
- [ ] 任务详情“重新刮削”在 mock/fixture 下能打开搜索弹窗。

Exit Criteria:
- LLM 相关生产 import 不再指向 `scraper`。
- AI 输出字段仍满足 6 层信息职责模型。

### Phase 4: Metadata Flow Slice

目标:迁移正式任务元数据刮削编排,并自然拆分大文件。

- [ ] 将 `metadata_scrape_flow.py` 迁到 `features/scraping/metadata_flow/`。
- [ ] 拆为以下职责文件:
  - `provider_only.py`:Provider-only 结果构建。
  - `ai_assisted.py`:AI 辅助结果构建。
  - `dimensions.py`:维度补充/映射衔接。
  - `orchestrator.py`:正式任务 scrape orchestration。
  - `models.py` 或 `errors.py`:局部数据结构/异常。
- [ ] 更新 `features/import_flow/steps/scrape.py` 等正式任务消费者。
- [ ] 保持正式任务与模拟器字段结构一致。

Backend/API Tests:
- [ ] `tests/test_formal_flow_field_propagation.py`。
- [ ] `tests/test_scrape_result_contract.py`。
- [ ] `tests/test_scrape_preview_job.py`。
- [ ] `tests/test_feature_import_flow.py` 中 provider-only/AI-assisted 路径。

Frontend Smoke:
- [ ] 模拟器 6 步路径正常。
- [ ] 任务卡片显示 L1-L4 关键字段。
- [ ] 任务详情显示 L1-L6 决策路径。
- [ ] 待确认任务可预览并确认入库。

Exit Criteria:
- `metadata_scrape_flow.py` 不再作为旧 scraper 事实入口。
- 正式任务与模拟器字段契约一致。

### Phase 5: Legacy Wrapper Audit, Compatibility Cleanup and Guard

目标:收尾旧路径,防止迁移倒退。

- [ ] 全仓生产代码 grep 确认无 `from media_importer.scraper`。
- [ ] 处理 `scraper/metadata_scraper.py` 与 `scraper/dimension_manager.py`:与 feature 同名模块对比后,合并有价值逻辑,其余归档或删除。
- [ ] 旧 `scraper/` 目录保留一轮兼容 re-export,并在文件头标注 deprecated 和目标 import。
- [ ] 增加 `tests/test_architecture_guards.py` 规则:新生产代码不得 import `media_importer.scraper.*`。
- [ ] 更新 docs/features/scraping.md、docs/architecture/scraping.md、docs/ai-map.md、docs/INDEX.md。
- [ ] 在后续清理计划中删除兼容 facade。

Exit Criteria:
- 新事实源为 `features/scraping`、`features/providers`、`features/prompts`。
- `scraper/` 不再作为业务事实入口,只作为一个版本周期的兼容 facade。

---

## 6. Test Matrix

| 层级 | 必测内容 | 目的 |
|------|----------|------|
| 单元 | cleaner、matcher、MatchResult、Tier 1/2/3 | 防止匹配语义变化 |
| API | scrape preview、Provider connectivity、task rescrape/preview/confirm | 防止接口契约变化 |
| 集成 | formal import flow、field propagation | 防止正式任务与模拟器分叉 |
| Playwright | 配置页 Provider 测试、刮削搜索测试、任务详情重新刮削、模拟器、确认入库 | 防止前端触发入口失效 |
| 架构 guard | 禁止新 `media_importer.scraper.*` import | 防止倒退 |

### UI Smoke Execution Contract

前端 smoke 不是手工口头确认,必须满足以下至少一种形式:

1. 使用 Playwright/Browser 工具真实点击本地服务页面。
2. 使用 gated pytest Playwright 脚本,例如:

```bash
python -m pytest tests/test_e2e_cinema_workflow.py --run-e2e-cinema -v
```

前置条件:
- 服务运行在 `http://127.0.0.1:9855` 或通过 `MEDIA_IMPORTER_BASE_URL` 指定。
- 用例需要 fixture 任务时,必须通过 API 或测试 fixture 创建,不能依赖生产 DB 中“刚好有任务”。
- 环境缺少 Playwright/browser/service 时,必须记录为环境跳过,不能当作功能通过。

每个切片至少要覆盖一个对应前端入口:
- cleaner/matcher:模拟器输入文件名并展示清洗/匹配路径。
- provider:配置页 Provider 测试/搜索入口。
- LLM/prompt:AI 配置页、提示词保存/重置、任务详情重新刮削弹窗。
- metadata flow:任务卡片/详情 L1-L6 展示、待确认预览与确认入库。

---

## 7. Acceptance Criteria

- [ ] 生产代码无直接 `media_importer.scraper.*` import。
- [ ] 旧 scraper 路径仅作为一个版本周期的兼容 re-export,后续删除另走清理计划。
- [ ] 刮削字段仍满足 `info-architecture.md` 6 层职责模型。
- [ ] 正式任务和模拟器 scrape_result 字段结构一致。
- [ ] Provider 测试、刮削预览、任务详情重新刮削、确认入库前端入口可点击且无 JS error。
- [ ] 非 UI 回归、编译检查、关键 Playwright 用例通过或有明确环境跳过说明。

---

## 8. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| 移动 LLM 逻辑导致 AI 输出字段变化 | 高 | 保持 prompt schema 不变,用 contract tests 锁字段 |
| Provider 客户端迁移导致连通性失败 | 高 | mock tests + connectivity API + 前端按钮 smoke |
| metadata flow 拆分改变正式任务字段 | 高 | formal flow field propagation 测试 |
| 旧路径兼容过久导致新代码继续引用 | 中 | architecture guard + deprecation 注释 |
| Playwright 环境不可用 | 中 | gated tests,记录环境跳过,至少保留 API 层验证 |

---

## 9. Final Review Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | 目录名采用 `features/scraping/metadata_flow/` | 表达正式任务元数据刮削编排流程,避免与旧 `metadata_scraper.py` 混淆 |
| 2 | LLM 执行能力放 `features/scraping`,prompt 组装放 `features/prompts` | LLM 在本系统中服务刮削决策,不是通用 Provider;prompt 职责单独归 prompts |
| 3 | 旧 `scraper/` 保留一个版本周期兼容 re-export,后续计划删除 | 降低迁移风险,同时用 guard 防止新依赖继续增长 |

---

## 10. Handoff

该子计划当前状态为 `pending-review`。用户确认前不执行实现。
