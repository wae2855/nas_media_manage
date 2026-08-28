# ADR-0010: 移除 AI 刮削，刮削链路收敛为 TMDB 主导

Date: 2026-08-22
Status: Accepted
Requirement: REQ-20260822-000001

## Context

当前刮削链路是「三级匹配」：Tier 1 TMDB 标题匹配、Tier 2 AI 辅助匹配（LLM 从文件名刮削元数据 + 纠错）、Tier 3 文件名兜底。AI 相关面包括 `llm_scraper`（元数据刮削+解析）、`llm_match_assist`（Tier 2）、`prompt_resolver`/`scene_strategy`（5 场景提示词策略）、`web_search_config`、`features/prompts`（提示词模板管理）以及 AI 配置三区域界面（场景策略 5×2 下拉、提示词 tab 等）。

用户业务判断（2026-08-22）：

- AI 刮削存在意义不大，过于复杂，直接去掉。
- AI 的真实价值在源目录清理器（LLM 辅助预览），需保留。
- AI 做维度判断的意义存疑 → 评估结论见 Decision 3。
- 项目方向为功能简洁化，公开发布 fpk。

技术事实：AI 相关代码约占 features/scraping 一半体量；测试面（match_engine/prompt/ai_config 系列）随之一半失效于真实用途；提示词/场景策略配置是配置面复杂度的主要来源之一。

## Decision

1. **移除 AI 刮削（Tier 2）**：删除/退役 `llm_scraper` 元数据刮削路径、`llm_match_assist`、`web_search_config`；`metadata_scrape_flow` 收敛为 TMDB 主流程；匹配模型从三级收敛为两级——
   - Tier A：TMDB 标题匹配（`title_matcher` L1-L7 分级保留用于展示与置信展示）
   - Tier B：文件名清理结果兜底 → 无匹配进 NEEDS_CONFIRM，由人工确认（含任务卡手动 TMDB 检索 scrape-search）兜底
2. **保留清理器最小 LLM 通路**：`llm_client`（HTTP client）保留并迁移至 `infrastructure/`；源目录清理器改用 llm_client + 自有清理提示词（从 `PromptResolver` 5 场景中仅保留 source-clean 场景语义，实现收敛到 `features/source_cleaning/` 内部）；`features/prompts` 收缩为清理器提示词服务或并入 source_cleaning。
3. **AI 维度判断退役**：维度来源收敛为 TMDB provider 数据（genre/certification）+ `dimension_manager` 规则映射 + 默认值/人工确认兜底（用户拍板 A+B 组合，2026-08-22）：
   - 规则增强：`_map_restricted_level` 从只消费 US/GB 两国分级扩展到 9 国（US>GB>DE>FR>CN>JP>KR>AU>CA），`CERTIFICATION_TO_LEVEL` 扩充各国分级符号；
   - B：维度表新增 `default_value` 可配置默认值，映射为空时采用（标记 source=default）；
   - A：无默认值的维度留空 → completeness 不完整 → NEEDS_CONFIRM 人工下拉选择；留空维度路径走 fallback_dir，不猜测。
   - 评估结论：AI 维度判断无不可替代性——TMDB 已提供权威 genre/certification，AI 推断仅在不完整文件名场景有边际收益，且猜错维度会导致入库路径错误（错比缺更糟）。
4. **AI 配置界面收缩**：三区域（连接/场景策略/提示词）→ 两块（LLM 连接 + 清理器提示词）。刮削提示词 tab、场景策略 5×2 下拉、维度 AI 相关设置全部移除。
5. **行为标准同步重写**：`standards/scrape-matching.md`（三级→两级）、`standards/ai-prompt-design.md`（仅保留清理器 AI 契约，其余退役归档）、`features/ai-config.md`/`features/prompts.md`/`features/scraping.md` 同步。

## Consequences

- 正向：刮削链路复杂度减半；配置面显著简化；prompt/场景/维度 AI 的测试面大幅收缩；AI 调用成本下降（仅清理器使用）。
- 负向/风险：无 TMDB 匹配或 TMDB 不可用时，兜底从「AI 猜测」变为「直接 NEEDS_CONFIRM 人工处理」，自动化率下降——接受（公开发布场景下人工确认是更可靠的兜底）。
- 文件名极度不规范（无英文名/年份）时识别率下降——由 title_matcher 模糊匹配 + 人工检索弥补。
- `confidence_models.py` 的候选排序阈值保留（TitleMatcher 内部），与任务状态判定解耦的既有设计不变。

## Alternatives

- 仅简化 AI 提示词而不删除：保留两套兜底复杂度，与简洁化方向冲突，否决。
- 用 TMDB 关键词搜索替代 AI 推断：可作为 Tier A 内的检索增强候选项，不作为本 ADR 范围，后续按需评估。

## Links

- [评估提案（已归档）](../_archive/2026-08-27-simplification-complete/2026-08-22-simplification-assessment.md)
- [执行路线图（已归档）](../_archive/2026-08-27-simplification-complete/2026-08-22-simplification-roadmap.md)
- 替代的标准：[0005-three-tier-matching](0005-three-tier-matching.md)（三级匹配决策，本 ADR 部分取代其 Tier 2 设定）
