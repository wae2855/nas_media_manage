---
title: "规范、代码与历史方案关系复核"
type: review
date: 2026-06-18
status: pending-review
confidence: high
related:
  - docs/standards/architecture.md
  - docs/standards/coding.md
  - docs/standards/info-architecture.md
  - docs/architecture/overview.md
  - docs/architecture/task-lifecycle.md
  - docs/plans/2026-06-16-optimization-items-plan.md
  - docs/plans/2026-06-16-confirm-workflow-overhaul-plan.md
  - docs/tracking/requirements-board.md
---

# 规范、代码与历史方案关系复核

> 本文不是执行清单,而是评审前的事实核验。历史 plan 只代表当时意图,不自动视为当前可信事实源。需要以当前代码、当前事实文档、需求看板和用户决策为准。

---

## 0. 事实源分级

| 等级 | 来源 | 使用方式 |
|------|------|----------|
| 强事实 | 当前代码、当前测试、`docs/standards/`、`docs/architecture/`、`docs/tracking/requirements-board.md` | 可直接作为判断依据 |
| 中事实 | `docs/features/`、`docs/testing/feature-coverage.md`、ADR | 作为约束与设计意图,需与代码交叉验证 |
| 弱事实 | 历史 plan、未勾选验收清单、未进入 requirements-board 的计划 | 只作为历史意图,必须重新评估是否仍有效 |

---

## 1. 业务级结论

### 1.1 首页“需要确认”跳转确实有 bug

- **事实**: `media_importer/webui/index.html:131` 使用 `data-task-filter="confirm"`,而当前任务筛选合法 key 是 `review`。
- **业务影响**: 用户点击首页“需要确认”,期望进入待确认任务列表,实际会回到全部任务,看起来像点击没反应。
- **建议**: 立即修复为 `data-task-filter="review"`,并给未知 filter 增加轻量兜底日志。
- **风险**: 低。纯前端字符串修正。

### 1.2 当前存在一批未加载前端旧文件,但删除范围要分级

- **事实**: 目前有 19 个 JS 文件未被 `index.html` 加载。
- **业务影响**: 用户运行时不受影响,但维护者排查问题时容易看错文件,尤其是任务详情相关旧文件。
- **建议**: 分两批处理。
- **第一批**: 按用户决策,将 7 个旧任务链路文件移入归档: `tasks.js`、`tasks-list.js`、`tasks-detail.js`、`tasks-ops.js`、`tasks-ops-extended.js`、`tasks-actions.js`、`match-trace-detail.js`。
- **第二批**: 其余 12 个未加载文件先登记为“未加载候选”,等前端清理阶段统一处理,避免误删未来参考。
- **风险**: 第一批运行时低风险,维护风险中低。第二批风险中等。

### 1.3 `confirm_reason` 不是简单死字段,要先做字段契约决策

- **事实**: DB 建表、task_repo 查询/更新白名单、`tests/test_task_confirm_reason.py` 仍在保护 `confirm_reason`。
- **业务问题**: 系统现在存在两套“为什么需要确认”的表达:
  - 旧字段: `tasks.confirm_reason`
  - 新信息模型: `match_level`、`tier_short_reason`、`ai_reason`、`match_concerns`、`match_trace`
- **用户决策**: 优化项 2 要做,即最终要删除 `confirm_reason`。
- **建议**: 删除前先明确迁移规则:前台与 API 以后只使用新信息模型;老 DB 字段只作为迁移期兼容,不再写入新业务含义。
- **风险**: 中高。直接删会打破现有测试和可能的旧 DB 字段读取。

### 1.4 `scraper/` 整包迁移应启动,但必须放在回归保护之后

- **事实**: `features/scraping`、`features/providers`、`features/source_cleaning`、`api/connectivity_handlers.py` 仍直接引用 `media_importer.scraper.*`。
- **业务影响**: 刮削能力表面在 feature-first 目录,但真实实现仍分散在旧 `scraper/`,后续维护会混乱。
- **用户决策**: 启动整包迁移。
- **建议**: 先做 proof slice,不要一次性搬空。优先迁移 `filename_cleaner` / `title_matcher` / `tmdb_client` 这类边界清晰模块,再迁移 LLM 和 `metadata_scrape_flow`。
- **风险**: 高。刮削是主链路,必须有 API + Playwright + 单测保护。

### 1.5 `core.db -> infrastructure.db` 迁移应启动,但现在 `core.db` 仍是真实入口

- **事实**: `media_importer/infrastructure/db/__init__.py` 当前是反向 re-export `core.db`;features/API 大量直接 import `core.db`。
- **业务影响**: 数据库层名义上 infrastructure-first,实际仍 core-first,架构认知不统一。
- **用户决策**: 迁移到 `infrastructure.db`。
- **建议**: 先让 `infrastructure.db` 成为真实入口或稳定 facade,然后分批改 import。迁移期间保留 `core.db` 兼容导出。
- **风险**: 高。涉及任务、刮削、源清理、API、DB migration。

---

## 2. 历史方案复核

### 2.1 `optimization-items-plan.md` 不能当作已完成承诺

- **事实**: 该计划没有进入 `docs/INDEX.md` Current Plans,验收清单未勾选,也没有 `status: complete`。
- **修正**: 不应写“计划声称完成但未执行”。应写“历史优化建议仍未落地,其中部分仍有效,用户已确认要做”。
- **仍有效部分**: 7 个旧任务 JS 归档、`confirm_reason` 删除方向。
- **需要重评部分**: 19 个未加载 JS 全部删除、直接 DROP COLUMN 的低风险判断。

### 2.2 `confirm-workflow-overhaul-plan.md` 是“实现大体落地,但待验收”

- **事实**: 代码中已看到 `/preview`、`reclassify_task` preview-only、决策路径折叠、`buildMatchPathData` 透传 `status/confirmed_*` 等实现。
- **同时事实**: `docs/tracking/requirements-board.md` 里 `REQ-20260616-000001` 仍在 In Progress。
- **业务判断**: 不能只按 plan 里的 `Status: ✅ 已实施` 标完成。应按“实现已落地,等待浏览器主流程验收”。
- **建议**: 在下一轮计划里把它作为 baseline 验收项,而不是重新设计项。

### 2.3 ADR 0008/0009 缺失不应作为阻塞

- **事实**: plan 曾建议补 0008/0009,但实际只存在 0007。
- **业务判断**: 如果确认界面内嵌重刮和决策路径折叠已经成为长期设计,应补 ADR;如果只是局部交互实现,可以在架构文档中记录,不必强制补 ADR。
- **建议**: 放入计划的文档同步阶段,不是 P0 阻塞。

---

## 3. 代码与规范偏差复核

### 3.1 `scraper/` 仍是刮削事实实现的一部分

- **事实**: 多处 `features/*` 直接 import `media_importer.scraper.*`。
- **业务语言**: 刮削能力还没有真正完成 feature-first 迁移。用户看到的是新任务工作台和新匹配路径,但底层还有旧刮削实现。
- **处理策略**: 进入迁移计划,但先补回归保护。

### 3.2 `core.db` 仍是数据库事实入口

- **事实**: 大量 modules 直接 import `media_importer.core.db`;`infrastructure.db` 当前只是 re-export。
- **业务语言**: 数据持久化层的命名和架构意图不一致。现在不能强行说“core.db 违规”,因为它就是实际入口。
- **处理策略**: 新计划中把 `infrastructure.db` 迁移设为独立阶段。

### 3.3 `core.safety` 是兼容面,不是当前业务入口

- **事实**: 生产代码基本不从 `core.safety` import;测试仍验证 `from media_importer.core import safety as core_safety`。
- **业务语言**: 它是老 public import 的兼容层。是否删除取决于是否还承诺旧导入可用。
- **建议**: 暂不删除。等兼容面清理阶段统一处理。

### 3.4 大文件拆分是维护性问题,不是主流程阻塞

- **事实**: `_match_tiers_impl.py` 702 行,`metadata_scrape_flow.py` 527 行。
- **业务语言**: 匹配/刮削逻辑过集中,后续修改容易互相影响。
- **建议**: 跟随 scraper 迁移做自然拆分。不要为满足行数单独重构。

### 3.5 `_match_tiers_impl.py` docstring 不是错误

- **事实**: `match_engine.py` 明确 import `_match_tiers_impl.py` 中的 tier 实现函数。
- **修正**: 删除原评审中“MatchEngine 实际不从该文件 import”的说法。

---

## 4. 测试覆盖复核

### 4.1 不是“没有 Playwright”,而是“不系统”

- **事实**: 当前已有 `test_ai_config_ui.py`、`test_scrape_ui.py`、`test_cinema_ui_smoke.py`、`test_frontend_recycle.py` 等 UI/Playwright 相关脚本。
- **问题**: 它们命名混杂、运行方式不统一、覆盖的是点状功能,没有按当前 Cinema 信息架构保护完整主流程。
- **业务语言**: 现在前台不是没有测试,而是缺一套“用户真实点击路径”的系统化回归。

### 4.2 建议优先补的前台流程

| 优先级 | 流程 | 业务价值 |
|--------|------|----------|
| P0 | 首页指标卡 -> 任务筛选 | 防止“点了没反应” |
| P0 | 任务卡片详情 -> 待确认编辑 -> 预览 -> 确认入库 | 保护主流程 |
| P0 | FAILED/SKIPPED/CANCELLED -> 重试/重新投入 | 保护恢复路径 |
| P1 | AI 配置三区域 + 提示词保存 | 保护配置入口 |
| P1 | Provider 测试/搜索/详情 | 保护刮削外部依赖入口 |
| P1 | 回收站恢复/删除 | 保护危险操作 |

---

## 5. 用户已确认的方向

1. 优化项 1 要做:7 个遗留任务 JS 移入归档。
2. 优化项 2 要做:删除 `confirm_reason`,但按字段契约迁移方式执行。
3. `scraper/` 整包迁移要启动。
4. `core.db -> infrastructure.db` 要迁移。
5. 先制定方案和计划,再评审,暂不执行实现。

---

## 6. 风险分级

| 项 | 风险 | 说明 |
|----|------|------|
| 修 `data-task-filter=review` | 低 | 1 行前端 bugfix |
| 归档 7 个旧任务 JS | 中低 | 运行时低风险,且保留历史追溯 |
| 删除全部 19 个未加载 JS | 中 | 范围过大,建议第二阶段处理 |
| 删除 `confirm_reason` | 中高 | 需要迁移测试和字段契约 |
| `scraper/` 迁移 | 高 | 刮削主链路,必须分阶段 |
| `core.db` 迁移 | 高 | 持久化主链路,必须分阶段 |
| 大文件拆分 | 中 | 应随迁移自然发生,不要单独硬拆 |

---

## 7. 建议进入计划的执行顺序

1. Baseline:跑当前非 UI 回归 + 记录已知失败。
2. 前台 P0 修复:修首页“需要确认”跳转。
3. 建立最小 Playwright 主流程保护。
4. 优化项 1:归档 7 个旧任务 JS。
5. 优化项 2:迁移并删除 `confirm_reason`。
6. `scraper/` 迁移 proof slice,逐模块推进。
7. `core.db -> infrastructure.db` proof slice,逐 import 推进。
8. 文档同步与 ADR/architecture 更新。

---

## 8. 评审结论

- [ ] 同意该复核文档作为下一步计划依据
- [ ] 同意按 `docs/plans/2026-06-18-refactor-cleanup-and-migration-sequencing-plan.md` 继续评审
- [ ] 暂不执行实现,等待计划二次评审确认
