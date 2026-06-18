# ADR-0008: Scraper Feature-First Migration

Date: 2026-06-18
Status: Proposed
Plan: [2026-06-18-refactor-scraper-feature-first-migration-plan.md](../plans/2026-06-18-refactor-scraper-feature-first-migration-plan.md)
Related:
- [0004-feature-first-architecture-restructure.md](0004-feature-first-architecture-restructure.md)
- [0005-three-tier-matching.md](0005-three-tier-matching.md)
- [0007-information-responsibility-split.md](0007-information-responsibility-split.md)
- [../standards/scrape-matching.md](../standards/scrape-matching.md)
- [../standards/info-architecture.md](../standards/info-architecture.md)

## Context

项目已经确立 feature-first 架构方向,但刮削相关真实实现仍大量位于旧目录 `media_importer/scraper/`。当前实际依赖包括:

- `features/scraping` 复用旧 `title_matcher`、`filename_cleaner`、`llm_scraper`、`metadata_scrape_flow`。
- `features/providers` 复用旧 `tmdb_client`。
- `features/source_cleaning` 复用旧 LLM prompt 组装逻辑。
- `api/connectivity_handlers.py` 直接调用旧 LLM scraper。

同时 ADR-0005 和 ADR-0007 已经把刮削流程的行为语义固定下来:

- 三级匹配:Provider 精确匹配 -> AI 上下文辅助 -> 用户确认。
- AI 输出 `is_valid` 与 `certainty` 分离。
- 刮削描述信息拆为 L1-L6 六层职责字段。
- `confirm_reason` 万能胶废弃。

因此,迁移目标不是重新设计刮削行为,而是让代码组织与已接受的行为规范一致。

## Decision

将 `media_importer/scraper/` 中仍承担真实业务职责的模块迁入 feature-first 目录:

| 能力 | 目标事实源 |
|------|------------|
| 文件名清洗、标题匹配、三级匹配辅助 | `media_importer/features/scraping/` |
| Provider 客户端与 Provider 实现 | `media_importer/features/providers/` |
| Prompt 默认值、prompt 组装、prompt 场景契约 | `media_importer/features/prompts/` |
| 正式任务元数据刮削编排 | `media_importer/features/scraping/metadata_flow/` |

补充决策:

- `metadata_flow/` 是正式任务元数据刮削编排的目标目录名。
- LLM HTTP 调用执行能力归入 `features/scraping`;prompt 组装归入 `features/prompts`。
- `scraper/providers/*` 迁移前必须先与 `features/providers/*` 做差异对比,形成保留/合并/删除清单,不得直接覆盖现有 feature 实现。
- `scraper/dimension_manager.py` 与 `scraper/metadata_scraper.py` 即使当前无生产引用,也必须在迁移 inventory 中明确处置:合并、归档、删除或兼容 re-export。
- `scraper/__init__.py` 迁移后改造为 compat re-export 集散点,不移动文件内容;所有外部兼容入口经此文件转发到新 feature 模块。
- 旧 `scraper/` 路径迁移完成后保留一个版本周期兼容 re-export,后续单独删除。

迁移采用分阶段 proof slice:

1. cleaner/matcher
2. provider client
3. LLM client and prompt assist
4. metadata flow
5. compatibility cleanup and architecture guard

每个切片必须同时具备:

- 后端契约测试。
- API 或集成测试。
- 对应前端触发 smoke,例如 Provider 测试按钮、刮削搜索测试、任务详情重新刮削、模拟器、待确认确认入库。

旧 `scraper/` 路径在迁移期只允许作为兼容 re-export。迁移完成后,架构 guard 禁止新增生产代码 import `media_importer.scraper.*`。
所有 `media_importer/scraper/` 下的 `.py` 文件必须有最终处置结论,不得出现“未分类遗留文件”。

## Consequences

### Positive

- 刮削能力事实源与 feature-first 架构一致。
- 维护者可以按业务能力定位代码,不再在 `scraper/` 与 `features/` 之间跳转。
- ADR-0005/0007 的行为规范更容易被代码结构承载。
- 前端触发入口与后端模块形成稳定映射,有利于 Playwright 回归。

### Negative

- 迁移期间会存在新旧路径兼容 facade,短期内 import 图更复杂。
- metadata flow 拆分会触碰正式任务主流程,回归成本高。
- 如果测试不充分,可能出现字段透传或前端展示回归。

### Risk Mitigation

| Risk | Mitigation |
|------|------------|
| 刮削行为被迁移误改 | 以 `scrape-matching.md` 和 `info-architecture.md` 为不可变契约,先测后迁 |
| 正式任务与模拟器字段分叉 | 保留/强化字段一致性测试 |
| 前端入口断裂 | 每个切片必须跑对应 Playwright smoke |
| 旧路径继续被新代码引用 | architecture guard 禁止新增 `media_importer.scraper.*` import |

## Compliance

迁移完成后必须满足:

- 生产代码不再直接 import `media_importer.scraper.*`。
- `MatchResult.to_dict()` 字段契约不变。
- 正式任务与模拟器 `scrape_result` 结构一致。
- Provider 测试、刮削搜索测试、任务详情重新刮削、模拟器、确认入库等前端入口可用。
- 文档同步更新 `docs/architecture/scraping.md`、`docs/features/scraping.md`、`docs/INDEX.md`、`docs/ai-map.md`。

推荐前端 smoke 命令:

```bash
python -m pytest tests/test_e2e_cinema_workflow.py --run-e2e-cinema -v
```

若 Playwright、浏览器或本地服务不可用,必须记录为环境跳过,不能当作功能通过。

## Alternatives Considered

### Alternative 1: Keep `scraper/` as permanent implementation package

Rejected. This preserves current ambiguity and conflicts with feature-first architecture direction.

### Alternative 2: Move all files at once

Rejected. The blast radius is too large: Provider, LLM, formal import flow, source cleaning and frontend trigger paths can all regress at once.

### Alternative 3: Only re-export from features without moving implementation

Rejected as final state. It may be a temporary bridge, but it does not solve ownership or maintainability.

## Follow-up

- 迁移完成并稳定一个版本周期后,单独制定旧 `scraper/` compat facade 删除计划。
- 若迁移过程中发现 LLM client 需要成为跨 feature 通用外部服务能力,再另提 ADR;当前决策保持在 scraping/prompts 边界内。
