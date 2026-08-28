# Scrape Matching Standard（两级匹配）

---
title: scrape-matching-standard
type: standard
date: 2026-08-22
status: accepted
supersedes: 三级匹配（Tier 2 AI 辅助已按 ADR-0010 移除）
---

## 匹配模型（ADR-0010 后）

```text
输入文件 → FilenameCleaner 正则清洗（标题/年份/季集/CJK）
  → Tier 1：TMDB 标题匹配（TitleMatcher L1-L7 离散等级）
      ├─ L1/L2/L3/L5（匹配良好）→ AUTO_PASS 自动入库
      └─ CJK 搜索低匹配 → 英文标题回退再搜一轮（仍 Tier 1）
  → Tier 2：用户确认（NEEDS_CONFIRM）
      └─ 任务卡人工：手动 TMDB 检索（scrape-search）/ 编辑元数据 / 确认入库
```

- 匹配等级判定只依赖 `MatchResult.level`（TitleMatcher 离散等级），无置信度公式。
- Tier 2 AI 上下文匹配（原 tier2_correct）、AI 标题清洗（ai_clean）、纯 AI 刮削 fallback、整剧 AI 维度刮削已移除（ADR-0010）。
- `CONTEXT_PASS` 匹配等级已退役；现存等级：`AUTO_PASS` / `NEEDS_CONFIRM` / `FAILED`。

## 维度来源（显式来源标记）

| 来源 | 含义 | 判定 |
|------|------|------|
| `file` | 文件名解析（如 resolution_tier） | file_dimensions |
| `provider:{type}` | TMDB 数据规则映射（genre/certification/origin_country） | scrape_trace.provider_dimensions |
| `default` | 维度默认值（DB `dimensions.default_value`，ADR-0010 B 方案） | source=default, reliability=0.5 |
| `unknown` | 无显式来源 | 兜底 |

限制级映射：TMDB release_dates 按 9 国优先级（US>GB>DE>FR>CN>JP>KR>AU>CA）查 `CERTIFICATION_TO_LEVEL`（含美德法日韩分级符号）；无数据 → default_value 或留空进 NEEDS_CONFIRM（A 方案）。**不做任何猜测**。

## 硬规则

- 维度值为 None 且无默认值 → 不阻塞但 completeness 不完整 → 人工确认；路径规则匹配不到走 fallback_dir。
- AI 不参与刮削与维度判定（唯一 LLM 消费者是源目录清理器，见 ai-prompt-design.md）。
- 决策路径（trace）必须逐步可解释：清洗 → 搜索 → 等级 → 维度来源。

## 变更前置

修改匹配行为/维度映射前先更新本文件；关联 ADR：[0010](../decisions/0010-remove-ai-scraping.md)、[0005](../decisions/0005-three-tier-matching.md)（历史三级设计）。
