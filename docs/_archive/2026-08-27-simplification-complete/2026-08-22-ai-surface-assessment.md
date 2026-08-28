---
title: "AI 面全量梳理与必要性评估"
type: proposal
date: 2026-08-22
status: approved
requirement: REQ-20260822-000003
---

# AI 面全量梳理与必要性评估

> 背景：用户要求在删码前先梳理全部 AI 参与点、评估必要性、给出建议。本文是 ADR-0010 的执行前深化，全部基于代码实证（文件:行号）。

## 1. AI 参与全景（7 个场景）

### A. 刮削主链路（每个视频文件处理时）

| # | 场景 | 触发条件 | 做什么 | 代码位置 |
|---|------|----------|--------|----------|
| A1 | **AI 标题清洗**（title_clean） | 正则清洗后 `year_suspect`，或 TMDB 匹配等级 L4/L6/L7 | AI 从文件名重新提取标题/年份 → 用清洗结果重搜 TMDB | `metadata_scrape_flow.py:129,252,290`（3 处调用点） |
| A2 | **Tier2 AI 纠错**（match_assist） | MatchEngine 第 2 级：TMDB 模糊匹配（标题不完全一致） | AI 从文件名+路径上下文纠正标题，输出 `corrected_title`+`certainty` | `_match_tiers_impl.py:505` |
| A3 | **AI 维度补全**（dimension_mapping） | TMDB 详情维度不完整（典型缺 restricted/documentary） | AI 按 Provider 上下文补全缺失维度 | `metadata_scrape_flow.py:404-431`（scrape_with_context） |
| A4 | **纯 AI 刮削 fallback** | A3 失败时 | 全量 AI 刮削（标题+维度） | `metadata_scrape_flow.py:433-436` |

### B. 整剧链路

| # | 场景 | 触发条件 | 做什么 | 代码位置 |
|---|------|----------|--------|----------|
| B1 | **整剧 AI 维度刮削**（series_scrape） | 剧集处理时维度不全 | 按剧名整体调 AI 刮维度（这是「AI 维度判断」的主体入口） | `import_flow/steps/scrape.py:287` |

### C. 源目录清理器（用户已拍板保留）

| # | 场景 | 做什么 | 代码位置 |
|---|------|--------|----------|
| C1 | **LLM 清理建议**（source_clean） | 目录文件列表给 LLM → 判断哪些可删/保留 | `source_cleaning/cleaner.py:314-330` |

### D. 边缘功能

| # | 场景 | 现状 | 代码位置 |
|---|------|------|----------|
| D1 | **ai-demo 演示** | AI 配置界面演示按钮（extract_title 等） | `connectivity_handlers.py:89` |
| D2 | **web_search 增强** | 仅服务于 A4/B1（zhipu/minimax/qwen） | `web_search_config.py`（93 行） |

## 2. 逐项必要性评估

### A1 AI 标题清洗 —— 建议：移除

- **价值**：仅当文件名混乱（年份可疑/低匹配）时有边际收益；正则 `FilenameCleaner` 已覆盖绝大多数场景。
- **移除后行为**：低匹配直接进 NEEDS_CONFIRM → 用户在任务卡手动 TMDB 检索（`scrape-search` 纯 TMDB，不依赖 AI）确认。
- **成本**：3 处触发调用点 + fast_model 独立配置 + extract_title 提示词场景；调试困难（AI 清洗结果不可预测）。
- **判断**：自动重搜一次的收益 < 链路复杂度成本；人工兜底更可靠（公开发布场景）。

### A2 Tier2 AI 纠错 —— 建议：移除

- **价值**：模糊匹配时提升自动匹配率；但 certainty 低时仍进 NEEDS_CONFIRM，本质是「AI 帮忙重试一次」。
- **移除后行为**：匹配收敛为两级——TMDB 精确/模糊匹配（Tier1）→ 不确定即 NEEDS_CONFIRM 人工确认。match_engine 从 697 行 `_match_tiers_impl` 显著简化。
- **判断**：用户已表态 AI 刮削意义不大；Tier2 是 AI 参与匹配的最深点，移除后匹配行为更可预测、可解释（决策路径可视化也简化）。

### A3+B1 AI 维度判断（补全+整剧刮削）—— 建议：移除

这是用户点名评估的部分，代码实证结论：

- **维度来源现状**：TMDB genre（含 documentary）+ certification→restricted 规则映射（`dimension_manager.py:247 map_provider_to_dimension`）已覆盖主要维度；AI 补的是规则映射不出的边角数据。
- **AI 参与的真实场景**：TMDB 数据缺 certification（老片/冷门片）时的 restricted 判断、个别 genre 缺失。
- **风险**：AI 猜错维度（如把普通片判为 restricted）直接导致入库路径错误——错比缺更糟；人工确认界面已支持维度编辑。
- **判断**：**无不可替代性**。TMDB 权威数据 + 规则映射 + NEEDS_CONFIRM 人工编辑兜底，可靠性高于 AI 推断。B1 整剧刮削每次剧集维度缺失都触发一次 AI 调用，成本高收益低。

### A4 纯 AI 刮削 fallback —— 建议：移除

- provider-first 已是唯一主模式（代码注释明确「不 fallback 纯 AI」是主路径设计，A4 只是 A3 失败时的残留 fallback）。
- 移除后：A3 删除则 A4 自然消失；降级为 `_build_minimal_result` + NEEDS_CONFIRM。

### C1 清理器 AI —— 建议：保留（已拍板），但架构收敛

- **收敛**：不再复用 `LLMScraper`/`PromptResolver`/`scene_strategy`（5 场景策略矩阵对单场景是过度设计）；改用 `llm_client` + 清理器内置提示词（提示词常量进 `features/source_cleaning/`）。
- **配置**：`llm` 块收缩为 `api_key/base_url/model/timeout/max_retries`（+`source_cleaner_model` 可选独立模型）。

### D1 ai-demo —— 建议：移除

- 演示的是 extract_title 场景（随 A1 退役）；LLM 连通性测试 `/api/config/test-llm` 已覆盖需求。

### D2 web_search —— 建议：移除

- 仅服务于 A4/B1（均移除）；清理器明确不启用搜索。93 行代码 + 4 个 provider 配置项 + 前端开关全部退役。

## 3. 保留/移除总表

| 组件 | 行数/规模 | 处置 |
|------|-----------|------|
| `llm_client.py`（HTTP/重试/fallback/日志） | 332 | **保留**，迁 `infrastructure/llm/`，供清理器使用 |
| `source_cleaning/cleaner.py` AI 部分 | ~80 | **保留**，提示词内置化 |
| `llm_scraper.py` | 260 | 移除（A1/A3/A4 载体） |
| `llm_match_assist.py` | 232 | 移除（A2） |
| `prompt_resolver.py` | 110 | 移除（清理器提示词内置后无用） |
| `scene_strategy.py`（5×2 场景矩阵） | 29 | 移除 |
| `web_search_config.py` | 93 | 移除（D2） |
| `features/prompts/` | 204 | 收缩：保留默认清理提示词，并入 source_cleaning |
| `metadata_scrape_flow.py` AI 分支 | ~200 | 移除（flow 简化为 TMDB 主干） |
| `_match_tiers_impl.py` Tier2 | ~100 | 移除（两级匹配） |
| `steps/scrape.py` 整剧刮削段 | ~30 | 移除（B1） |
| `ai-demo` 端点+前端 | — | 移除（D1） |
| 配置面 | llm 块 14 项→5 项；删 web_search/scene_strategy/prompts 文件引用 | 收缩 |
| 前端 | AI 配置三区域→「LLM 连接+清理器提示词」两块；模拟器自动简化 | 收缩 |
| 测试 | test_ai_*/test_prompt_*/test_tier2_*/test_llm_web_search 等 ~12 文件 | 按新契约重写或删除 |

**净效果估算**：后端净删 ~1,300 行 AI 代码 + 前端 AI 配置区收缩 + 配置块 20→16；LLM 调用只剩清理器一个消费者；刮削行为 100% 可解释（TMDB 数据 + 规则 + 人工确认，无 AI 黑盒）。

## 4. 移除后的用户可见变化（如实告知）

1. 文件名混乱/冷门片的自动匹配率下降 → 更多任务进「需要确认」（手动检索 10 秒/个，公开发布场景可接受）。
2. 老片/冷门片的 restricted/documentary 可能缺省 → 人工确认时编辑（错率降为 0）。
3. AI 配置页大幅简化（少两个区域）。

## 5. 维度兜底设计（用户 2026-08-22 拍板：A+B 组合）

AI 维度补全移除后，「TMDB 映射不到」的维度按两层实现：

### 第一层：限制级 9 国分级规则增强（纯规则，无 AI）

现状缺陷：`_map_restricted_level` 定义了 9 国优先级但只消费 US/GB 两国数据。增强：

1. 放开国家循环到全部 9 国（US>GB>DE>FR>CN>JP>KR>AU>CA）
2. `CERTIFICATION_TO_LEVEL` 扩充各国分级符号：DE（FSK 0/6/12/16/18）、FR（-10/-12/-16/-18）、JP（G/PG12/R-15+/R-18+）、KR（All/12/15/19）、CN（普遍/辅导/限制）等
3. source_reliability 按「国家优先级」递减标记，供前端展示置信来源

### 第二层：默认值 + 人工确认兜底（A+B 组合）

- **B**：维度表增加 `default_value` 字段（可配置）。映射为空时若配置了默认值 → 直接采用（标记 `source=default`）。
- **A**：未配置默认值的维度留空 → `completeness` 判定不完整 → 任务进 NEEDS_CONFIRM，人工在确认界面下拉选择（界面已支持维度编辑）。
- 维度留空时路径规则走 `fallback_dir`（未分类目录）——现有安全行为保持不变，绝不像 AI 一样猜测。

### 维度表 source_type 枚举收敛

`ai`/`ai+provider` 退役 → 收敛为 `provider`（TMDB 映射）/`file`（文件名解析）二类；`ai_prompt`/`trust_ai_assist`/`trust_ai_search` 字段随 AI 移除退役（DB migration 平滑清理）。

## 6. 待确认

以上评估与 ADR-0010 方向一致并细化了 7 个场景的逐项处置；§5 兜底方案已由用户拍板（A+B 组合 + 9 国规则增强）。
