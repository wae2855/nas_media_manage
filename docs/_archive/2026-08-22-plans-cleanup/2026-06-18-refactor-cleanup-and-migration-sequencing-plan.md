---
title: "refactor: cleanup and migration sequencing"
type: plan
date: 2026-06-18
status: pending-review
confidence: medium
related:
  - docs/_drafts/2026-06-18-spec-code-mismatch-review.md
  - docs/_drafts/2026-06-18-file-flow-cartesian-product.md
  - docs/plans/2026-06-18-refactor-scraper-feature-first-migration-plan.md
  - docs/standards/info-architecture.md
  - docs/standards/scrape-matching.md
  - docs/architecture/task-lifecycle.md
  - docs/decisions/0007-information-responsibility-split.md
  - docs/decisions/0008-scraper-feature-first-migration.md
---

# 清理与迁移执行顺序计划

一行摘要:先建立回归保护,再做前端遗留归档、`confirm_reason` 字段退役、`scraper/` feature-first 迁移和 `core.db -> infrastructure.db` 入口迁移。

> 当前计划只用于评审。未经过用户确认前,不执行实现代码变更。

---

## 1. Problem Statement

当前项目同时存在三类债务:

1. **前台维护债**:任务工作台使用 Cinema 链路,但旧 `tasks-*.js` 仍留在代码树,另有首页“需要确认”筛选值错误。
2. **字段契约债**:ADR-0007 已将 `confirm_reason` 万能胶拆成 6 层职责字段,但 DB/测试仍残留旧字段契约。
3. **架构入口债**:`scraper/` 和 `core.db` 仍是事实实现入口,与 feature-first / infrastructure-first 目标不一致。

这些问题如果一次性重构,风险很高。必须按“可验证切片”推进。

---

## 2. Target End State

完成后应满足:

- 首页“需要确认”能正确进入 `review` 筛选。
- 旧任务 JS 链路移入归档,维护者只看 Cinema 任务链路。
- `confirm_reason` 不再作为业务字段使用;新任务确认原因全部来自 ADR-0007 定义的 6 层信息模型。
- `scraper/` 不再作为新业务事实入口;刮削实现迁入 `features/scraping`、`features/providers`、`features/prompts`。
- `infrastructure.db` 成为 DB import 事实入口;`core.db` 仅保留兼容导出或最终退役。
- 关键用户路径有 Playwright 回归保护。

---

## 3. Scope

### In Scope

- 修复首页任务筛选 bug。
- 将 7 个明确孤立的旧任务 JS 文件移入归档。
- 设计并执行 `confirm_reason` 字段退役。
- 启动 `scraper/` 整包迁移,按 proof slice 推进。
- 启动 `core.db -> infrastructure.db` 迁移,按 proof slice 推进。
- 补足关键 Playwright 和服务级回归测试。
- 同步 docs/architecture、docs/features、docs/testing、ADR 或决策记录。

### Non-Goals

- 不一次性删除 19 个未加载 JS 文件。
- 不在同一阶段同时迁移 scraper 和 DB。
- 不重写整个前端 UI。
- 不改变任务状态模型(status+stage)。
- 不改变刮削匹配语义(AUTO_PASS/CONTEXT_PASS/NEEDS_CONFIRM/FAILED)。

---

## 4. Constraints and Boundaries

- 删除/覆盖影视文件仍必须走回收站。
- `deploy/` 生成副本不参与本次默认改动。
- 每个阶段结束必须保持默认非 UI 测试可运行。
- UI 相关改动必须至少用 Browser/Playwright 做一次真实点击验证。
- `confirm_reason` 删除必须继承 ADR-0007 的 6 层职责模型,不能重新设计字段语义。
- `confirm_reason` 删除必须兼容已有 DB,不能让已有数据库启动失败。
- `scraper/` 迁移期间必须保留旧 import 兼容,直到所有消费者迁完并有 guard。
- `core.db` 迁移期间必须保留 `core.db` 兼容 facade,直到所有消费者迁完并有 guard。

---

## 5. Phased Implementation

### Phase 0: Baseline and Guardrail

目标:先建立当前行为基线,避免迁移中无法判断是否回归。

- [ ] 记录当前 git 状态和 baseline commit。
- [ ] 跑非 UI 回归: `python -m pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py`。
- [ ] 跑编译检查: `PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer tests`。
- [ ] 检查 `.pytest_cache/v/cache/lastfailed`,标记历史失败。
- [ ] 用 Browser 工具或 Playwright 验证当前任务工作台详情能打开(无 Playwright 环境时至少用 Browser 工具完成一次真实点击)。

Exit Criteria:
- 有 baseline 测试记录。
- 已知失败和新增失败能区分。

### Phase 1: Frontend P0 Bug and Minimal UI Protection

目标:先修用户可感知的“点了没反应”。

- [ ] 修 `index.html:131` 的 `data-task-filter="confirm"` 为 `review`。
- [ ] 给 `setTaskFilter` 增加未知 filter 兜底日志或安全 fallback。
- [ ] 增加/修正 Playwright 用例:首页“需要确认”指标卡 -> 任务工作台 `review` chip active。
- [ ] 增加/修正 Playwright 用例:任务详情按钮可打开详情弹窗。

Exit Criteria:
- 用户点击首页“需要确认”进入待确认筛选。
- 任务详情点击不再静默失败。

### Phase 2: Optimization Item 1 - Legacy Task JS Archive

目标:把明确孤立的旧任务前端链路移入归档,保留追溯能力,运行时代码只剩 Cinema 链路。

- [ ] 若 `_archive/` 尚不存在,先创建该目录。
- [ ] 在 `_archive/2026-06-18-legacy-task-ui/` 下建立本次前端遗留归档目录,记录归档原因和原路径。
- [ ] 移入 7 个旧任务 JS 文件: `tasks.js`、`tasks-list.js`、`tasks-detail.js`、`tasks-ops.js`、`tasks-ops-extended.js`、`tasks-actions.js`、`match-trace-detail.js`。
- [ ] 删除 `cinema-app-events.js` 中 `data-task-row-open` 死分支,或确认是否仍有 emit 方。
- [ ] 不处理其余 12 个未加载 JS,只登记到后续清理清单。
- [ ] 跑前端加载 smoke:首页、任务、详情、配置、回收站。

Exit Criteria:
- `index.html` 无 404。
- 任务详情仍可打开。
- 7 个旧文件不再存在于 `media_importer/webui/js/`,但可在归档目录追溯。

### Phase 3: Optimization Item 2 - `confirm_reason` Retirement

目标:执行 ADR-0007:让“需要确认的原因”统一来自 6 层职责字段,退役旧 DB 字段。

步骤 A:契约确认
- [ ] 以 ADR-0007 和 `docs/standards/info-architecture.md` 为唯一契约: L1=`match_level/match_tier`, L2=`tier_short_reason`, L3=`ai_reason`, L4=`selected_candidate`, L5=`concerns[]`, L6=`trace_steps[]`。
- [ ] 明确各视图只读自己职责层:列表 L1+L2,卡片 L1-L4,详情 L1-L6。
- [ ] 更新 `docs/standards/info-architecture.md` 中 `confirm_reason` DB 列状态为“本计划退役”。
- [ ] 将 `tests/test_task_confirm_reason.py` 替换为新字段契约测试,覆盖 `tier_short_reason`、`ai_reason`、`match_concerns`、`match_trace` 持久化与 API 返回。

步骤 B:代码退役
- [ ] 停止在新代码中写 `confirm_reason`。
- [ ] 删除 `_match_tiers_impl.py` 中冗余 `confirm_reason=""` 赋值,但先保留 `MatchResult.confirm_reason` 字段直到兼容完成。
- [ ] 从 `task_repo.py` 的 select 和 valid_columns 移除 `confirm_reason`。
- [ ] 从新建表 schema 移除 `confirm_reason`。

步骤 C:DB migration
- [ ] 在 migration 中用 SQLite 版本守卫 DROP COLUMN。
- [ ] SQLite 低版本时保留列但不读写,记录 warning。
- [ ] 增加旧 DB 升级测试和新 DB schema 测试。

Exit Criteria:
- 新 DB 不含 `confirm_reason`。
- 旧 DB 可启动,高版本 SQLite 可 drop,低版本 SQLite 可兼容保留。
- 前台待确认原因仍按 6 层模型正确显示,不从 `confirm_reason` 反解析。

> **Phase 3/4/5 并行约束**: Phase 3(`confirm_reason` 退役)与 Phase 4(`scraper` 迁移)可并行执行,它们操作不同文件和领域。Phase 5(`core.db` facade)应在 Phase 4 完成后串行执行,因为 scraper 迁移可能改变同时作为 core.db 消费者的模块的 import 结构。

### Phase 4: `scraper/` Migration with Frontend and Backend Coverage

目标:按 scraper 子计划完成整包迁移,同时保证刮削、待确认、重新刮削、模拟器和入库主流程功能正常。

执行事实源:
- 子计划: `docs/plans/2026-06-18-refactor-scraper-feature-first-migration-plan.md`
- ADR: `docs/decisions/0008-scraper-feature-first-migration.md`

本阶段只负责总编排:
- [ ] scraper 子计划已通过评审并进入可执行状态。
- [ ] scraper ADR 已通过评审并进入 `Accepted` 或团队约定的可执行状态。
- [ ] 按子计划完成 cleaner/matcher、provider、LLM/prompt、metadata flow、compat cleanup 五个切片。
- [ ] 每个切片均满足子计划中的 Backend/API Tests 与 Frontend Smoke。
- [ ] 迁移完成后同步父计划验收结果。

Exit Criteria:
- scraper 子计划 Acceptance Criteria 全部满足。
- 生产代码不再 import `media_importer.scraper.*`。
- 前端触发刮削相关功能可点击、可返回结果、无 console error。

### Phase 5: `core.db -> infrastructure.db` Migration Proof Slice

目标:让 DB 层 import 方向与 architecture 对齐。

Phase 5A:入口定义
- [ ] 采用“先明确 facade,后逐步真实入口”的策略:
  - 第一步: `infrastructure.db` 作为唯一推荐 import facade,显式 re-export 当前 `core.db` 能力。
  - 第二步: 所有 feature/API 消费者改 import 到 `infrastructure.db`。
  - 第三步: 视复杂度决定是否把实际 DB repo 文件从 `core/db/` 移到 `infrastructure/db/`。
- [ ] 将 repo exports 明确写入 `infrastructure/db/__init__.py`,避免简单 `import *`。
- [ ] 暂时保留 `core.db` 作为兼容入口,不在第一轮删除。

Phase 5B:第一切片
- [ ] 迁移 `features/tasks/*` import 到 `media_importer.infrastructure.db`。
- [ ] 保持 `core.db` 兼容 re-export。
- [ ] 增加 tasks 领域回归测试。

Phase 5C:import_flow/source_cleaning/API 切片
- [ ] 迁移 `features/import_flow/*` DB import。
- [ ] 迁移 `features/source_cleaning/*` DB import。
- [ ] 迁移 API handler 里的 DB import。

Phase 5D:guard
- [ ] 增加 architecture guard:除 `core/db/*` 和兼容 facade 外,新代码禁止直接 import `media_importer.core.db`。
- [ ] 若第三步实际搬迁 repo 文件,单独制定子计划或 ADR。

Exit Criteria:
- 生产 feature/API 代码不再直接 import `core.db`。
- `core.db` 仅作为兼容入口。
- DB 相关测试通过。
- 迁移后 `features/*` 和 `api/*` 默认从 `infrastructure.db` import。

### Phase 6: Documentation and Acceptance

- [ ] 更新 `docs/architecture/overview.md`、`storage-filesystem.md`、`scraping.md`、`api.md`。
- [ ] 更新 `docs/features/` 中 tasks/import-flow/scraping/provider/source-cleaning 相关文档。
- [ ] 更新 `docs/testing/feature-coverage.md` 和 `test-inventory.md`。
- [ ] 根据落地范围决定文档形式:
  - `confirm_reason` 退役:优先更新 ADR-0007 / info-architecture,通常不需要新 ADR。
  - `scraper/` 整包迁移:单独拆子计划,并补 ADR,作为后续刮削流程与模块边界指导。
  - `core.db -> infrastructure.db`:facade/import 迁移放在本计划;若移动真实 repo 文件,单独拆子计划或 ADR。
- [ ] 将需求状态从 In Progress 移到 Pending Acceptance 或 Completed。
- [ ] 将“scraper compat facade 删除”写入 `docs/tracking/pending-acceptance.md`,避免后续清理计划遗漏。

Exit Criteria:
- 文档、代码、测试矩阵一致。
- 用户完成浏览器验收。

---

## 6. Acceptance Criteria

- [ ] 首页“需要确认”点击后进入待确认任务筛选。
- [ ] 任务详情弹窗可打开,决策路径默认折叠且可展开。
- [ ] 7 个旧任务 JS 文件已归档。
- [ ] `confirm_reason` 不再作为新业务字段读取/写入。
- [ ] 旧 DB 可安全迁移。
- [ ] 生产代码不再 import `media_importer.scraper.*`。
- [ ] 生产 feature/API 代码不再 import `media_importer.core.db`。
- [ ] 非 UI 回归、编译检查、关键 Playwright 用例通过。

---

## 7. Decision Rationale

### 为什么先测试再迁移

`scraper/` 和 `core.db` 都是主流程底层依赖。没有回归保护就迁移,会把“结构变好”变成“行为不可控”。因此先修 P0 UI bug 和建立最小 Playwright 保护。

### 为什么 `confirm_reason` 单独阶段

ADR-0007 已明确 `confirm_reason` 是万能胶反模式。它现在不是业务决策问题,而是迁移执行问题:先把测试和 API 契约改到 6 层信息模型,再删除 DB 列。

### 为什么 DB 迁移先做 facade,再考虑真实文件搬迁

`core.db -> infrastructure.db` 有两个层次:

1. **import 入口迁移**:业务代码从 `media_importer.infrastructure.db` import。此时底层文件仍可在 `core/db/`,风险较低。
2. **真实文件搬迁**:把 repo/connection/constants 等文件移动到 `infrastructure/db/`。这会影响大量 import、测试、迁移脚本和历史兼容,风险更高。

建议先完成第 1 层,让架构依赖方向变正确;第 2 层根据复杂度单独评审。

### 为什么不一次删 19 个未加载 JS

7 个旧任务文件边界明确;其余 12 个可能是历史配置页/未来参考。一次性删除会扩大评审和回滚成本。

---

## 8. Assumptions

| Assumption | Status | Evidence / Verification |
|------------|--------|-------------------------|
| `data-task-filter=confirm` 是 bug | Verified | `TASK_FILTER_META` 只有 `review`,无 `confirm` |
| 7 个旧任务 JS 未被运行时加载 | Verified | `index.html` script 列表不含它们 |
| `confirm_reason` 可最终退役 | Verified by ADR + User-confirmed | ADR-0007 已废弃万能胶,用户确认要做 |
| scraper 迁移可分切片 | Verified | 模块可按 cleaner/matcher/provider/LLM/flow 分类 |
| DB 入口迁移可分切片 | Verified | 可先迁 import facade,再评估真实文件搬迁 |
| 当前 Playwright 能在本地稳定执行 | Unverified | 需要本地服务和浏览器环境验证 |

---

## 9. Risk Analysis

| Risk | Impact | Mitigation |
|------|--------|------------|
| 归档 JS 后隐藏依赖才暴露 | 中 | 先只归档 7 个明确孤立文件,跑页面 smoke |
| `confirm_reason` 删除破坏旧 DB | 高 | SQLite 版本守卫 + 低版本保留列 |
| scraper 迁移破坏刮削 | 高 | proof slice + 保留旧路径 re-export + 匹配测试 |
| core.db 迁移破坏任务/源清理 | 高 | 领域分批迁移 + repository 测试 |
| Playwright 环境不稳定 | 中 | UI 测试 gated,失败区分环境阻塞和产品回归 |
| 文档再次与实现漂移 | 中 | 每阶段 exit criteria 包含 docs/testing 更新 |

---

## 10. Review Decisions

以下决策来自用户对二次评审问题的确认。

| # | 决策 | 状态 | 对计划的影响 |
|---|------|------|--------------|
| 1 | `scraper/` 迁移切片顺序采用 cleaner/matcher -> provider -> LLM client -> metadata flow -> 旧 scraper facade 清理 | 已确认 | Phase 4 按此顺序执行 |
| 2 | `scraper/` 整包迁移单独拆子计划 | 已确认 | 本计划只保留总编排,执行前先产出 scraper 子计划 |
| 3 | `scraper/` 整包迁移补 ADR | 已确认 | ADR 作为后续刮削流程、模块边界和职责规范指导 |
| 4 | 每个 `scraper/` 切片必须同时通过后端契约测试和对应前端触发 smoke | 已确认 | Phase 4 每个切片增加测试门槛,不能只做后端搬迁 |
| 5 | `confirm_reason` 退役时,低版本 SQLite 无法 DROP COLUMN 可保留列但业务不读写 | 已确认 | migration 采用版本守卫,低版本降级为保留列 + warning |
| 6 | DB 迁移采用“先 `infrastructure.db` facade/import 入口,后评估真实文件搬迁”的两阶段方案 | 已确认 | Phase 5 先统一 import 方向,不直接移动 repo 文件 |
| 7 | `core.db -> infrastructure.db` 若涉及真实文件搬迁,另拆子计划/ADR | 已确认 | 本计划只做 facade/import 迁移;文件搬迁另评估 |
| 8 | 7 个旧任务 JS 归档到 `_archive/2026-06-18-legacy-task-ui/` | 已确认 | Phase 2 使用该目录 |

---

## 11. Handoff

该计划当前状态为 `pending-review`。已补充 scraper 子计划和 scraper ADR 草案,建议下一步进入最终计划评审。用户确认前不执行实现。
