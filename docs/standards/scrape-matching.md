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
输入文件 → 中文发布说明薄层 → GuessIt 固定版本通用解析 → ReleaseIdentity 归一化
  → 身份证据：文件 basename（主）+ 通过门禁的目录 basename（辅）
  → Tier 1：分别查询 TMDB，按 Provider ID 合并证据
      ├─ 文件标题+年份/季集唯一精确匹配 → AUTO_PASS
      ├─ 文件标题+年份/类型精确命中 Provider 官方别名 → AUTO_PASS
      ├─ 文件与目录使用不同语言但收敛到同一作品 → AUTO_PASS
      ├─ 弱文件名由可信目录标题+年份/季集唯一补足 → AUTO_PASS
      └─ 年份/类型/可信标题冲突或证据不足 → Tier 2
  → Tier 2：用户确认（NEEDS_CONFIRM）
      └─ 任务卡人工：手动 TMDB 检索（scrape-search）/ 编辑元数据 / 确认入库
```

- 每个查询必须使用自己的标题执行 `TitleMatcher` 复核，禁止用英文主标题复核中文查询。
- GuessIt 只输出发布名结构，不是媒体身份事实源；不得因 GuessIt 结果或 Provider 唯一候选直接自动入库。
- 中文适配层只处理中文数字季集、全角符号及强证据发布说明；禁止为具体影片增加代码白名单。
- `.me/.tv` 等字符串只有带协议、`www.` 或明确广告上下文时才作为域名，不能删除正常点分英文片名。
- 多集目录保留 episode 范围；单文件中的具体 episode 是任务主证据，不得被目录范围首集覆盖。
- Provider 官方别名只在文件主证据、媒体类型一致、年份精确一致且别名归一化后完全相等时提升为 AUTO_PASS；接口失败按无证据处理。
- 候选按 `provider_type + media_type + provider_id` 合并；热度只用于人工候选排序，不得覆盖身份冲突。
- Tier 2 AI 上下文匹配（原 tier2_correct）、AI 标题清洗（ai_clean）、纯 AI 刮削 fallback、整剧 AI 维度刮削已移除（ADR-0010）。
- `CONTEXT_PASS` 匹配等级已退役；现存等级：`AUTO_PASS` / `NEEDS_CONFIRM` / `FAILED`。

## 维度来源（显式来源标记）

| 来源 | 含义 | 判定 |
|------|------|------|
| `file` | 文件名解析（如 resolution_tier） | file_dimensions |
| `provider:{type}` | TMDB 数据规则映射（genre/certification/origin_country） | scrape_trace.provider_dimensions |
| `default` | 维度默认值（DB `dimensions.default_value`，ADR-0010 B 方案） | source=default, reliability=0.5 |
| `unknown` | 无显式来源 | 兜底 |

观看分级映射：TMDB release_dates 按 10 个国家/地区优先级（HK>US>GB>DE>FR>CN>JP>KR>AU>CA）匹配版本化 Provider 规则；香港 `I/IIA/IIB/III` 分别映射为 `0-6/13-16/13-16/17+`。无数据 → default_value 或留空进 NEEDS_CONFIRM（A 方案）。**不做任何猜测**。

## 硬规则

- 文件 basename 是主证据；其标题与年份/季集唯一精确匹配后立即通过，无关目录不得否决或降级。
- 目录 basename 只作可选辅助证据。来源根、通用下载目录、日期/哈希目录、技术结构目录和电影型多视频容器必须忽略。
- 根直属单文件不得使用来源根名称。`BDMV/STREAM/Season xx` 等结构目录只允许在来源根内有限向上寻找最近的有效标题目录。
- 目录证据不得与文件名原串拼成一次搜索；只有与文件候选收敛到同一 Provider 作品，或文件名本身为 `video/00001/SxxExx` 等弱身份时才可提高结论。
- 文件和目录分别精确指向不同作品、年份冲突或类型冲突时必须 `NEEDS_CONFIRM`。
- 维度值为 None 且无默认值 → 不阻塞但 completeness 不完整 → 人工确认；路径规则匹配不到走 fallback_dir。
- AI 不参与刮削与维度判定（唯一 LLM 消费者是源目录清理器，见 ai-prompt-design.md）。
- 决策路径（trace）必须逐步可解释：清洗 → 搜索 → 等级 → 维度来源。
- 解析器依赖必须固定版本；升级 GuessIt 必须作为匹配行为变更运行真实发布名语料回归。

## 变更前置

修改匹配行为/维度映射前先更新本文件；关联 ADR：[0024](../decisions/0024-layered-release-name-recognition.md)、[0010](../decisions/0010-remove-ai-scraping.md)、[0005](../decisions/0005-three-tier-matching.md)（历史三级设计）。
