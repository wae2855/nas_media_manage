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
  → 身份证据：文件显式 ID > 相邻 NFO ID > 作品目录 ID > 已存在历史绑定 > 文件标题 > 目录标题
  → 确定性 ID 查询：Provider 原生 ID 或外部 ID → 类型/明确年份校验
      ├─ 唯一且无冲突 → AUTO_PASS
      ├─ ID 指向多部作品或类型/年份冲突 → NEEDS_CONFIRM
      └─ ID 无结果/接口异常 → NEEDS_CONFIRM（禁止静默降级到标题匹配）
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
- GuessIt 只输出发布名结构；其中的 TMDB/IMDb/TVDB ID 是强身份线索，但必须经过 Provider 查询和类型/明确年份校验后才能自动通过。不得因普通解析结果或 Provider 唯一文本候选直接自动入库。
- GuessIt 的 `alternative_title` 保留为候选和解释字段，`date` 归一化为 `release_date` 并作为 TV 类型证据但不污染作品年份，`part`、`episode_title` 直接保留，实际 `cd` 输出统一为 `disc`；这些辅助字段本身不等于 Provider 身份。
- 中文适配层只处理中文数字季集、全角符号及强证据发布说明；禁止为具体影片增加代码白名单。
- `.me/.tv` 等字符串只有带协议、`www.` 或明确广告上下文时才作为域名，不能删除正常点分英文片名。
- 多集目录保留 episode 范围；单文件中的具体 episode 是任务主证据，不得被目录范围首集覆盖。
- Provider 官方别名合并 alternative titles 与 translations；只在年份/类型或文件与目录等独立证据成立时提升为 `AUTO_PASS`。英语标题允许在官方标题核验阶段忽略开头的 `A/An/The`，不把该规则用于普通模糊匹配。别名接口失败按无证据处理。
- NFO 读取属于独立本地证据模块，只允许读取视频同名、`movie.nfo`、`tvshow.nfo` 及来源根内有限祖先的合理同名 NFO；限制文件大小、拒绝符号链接，核心只采纳 `uniqueid`/legacy ID。`Extras/Trailers/Featurettes/Samples` 等附加内容目录形成 NFO identity inheritance boundary：只允许当前视频同 basename 的 NFO，不继承作品根 NFO。NFO scope 分为 `movie/series/episode/unknown`，episode ID 只留痕，不得作为 series ID 查询。NFO 标题和年份只作校验，不追加为模糊搜索噪声；NFO 无标题时用可信作品目录校验 ID，明显冲突必须人工确认。
- 标题统一使用严格/宽松两级归一化：严格级统一 Unicode、大小写、词内撇号、破折号、标点和空白；宽松级只对 Latin 基字符折叠重音，并做保守的 `&/and` 等价，禁止音译、NLP 猜测或改变日文等非 Latin 字符语义。
- 候选按 `provider_type + media_type + provider_id` 合并，并按标题、年份、媒体类型、季集和文件/目录收敛等身份证据排序；热度只在证据同分时打破平局。第一、第二候选按证据形态及现有模糊匹配边界判断是否过近，不设脱离上下文的单一阈值；差距不足且无强 ID、官方别名或文件/目录收敛时必须人工确认。
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

- 文件 basename 是主证据；全部独立标题候选必须先完成强匹配查询，同一作品才可自动通过，多个标题指向不同作品必须 `NEEDS_CONFIRM`；无关目录不得否决或降级唯一强文件身份。
- 目录 basename 只作可选辅助证据。来源根、通用下载目录、日期/哈希目录、`1080p/2160p/4K/UHD/BluRay/REMUX/WEB-DL/WEBRip/HDTV/Complete` 等技术目录和电影型多视频容器必须忽略。
- 根直属单文件不得使用来源根名称。`BDMV/STREAM/Season xx/Disc`、`downloads` 等结构或通用目录要连续跳过，并在来源根内有限向上寻找最近的有效标题目录；未知目录清洗后无可信标题也必须继续，不得在第一个未知目录停止。
- 目录证据不得与文件名原串拼成一次搜索；只有与文件候选收敛到同一 Provider 作品，或文件名本身为 `video/00001/SxxExx` 等弱身份时才可提高结论。
- 文件和目录分别精确指向不同作品、年份冲突或类型冲突时必须 `NEEDS_CONFIRM`。
- 维度值为 None 且无默认值 → 不阻塞但 completeness 不完整 → 人工确认；路径规则匹配不到走 fallback_dir。
- AI 不参与刮削与维度判定（唯一 LLM 消费者是源目录清理器，见 ai-prompt-design.md）。
- 决策路径（trace）必须逐步可解释：清洗 → 搜索 → 等级 → 维度来源。
- 解析器依赖必须固定版本；升级 GuessIt 必须作为匹配行为变更运行真实发布名语料回归。
- 互联网命名回归必须同时满足场景族和展开样本正确 `AUTO_PASS` 率 ≥90%，安全负例误放为 0；执行口径见 [internet-media-name-coverage.md](../testing/internet-media-name-coverage.md)。

## 变更前置

修改匹配行为/维度映射前先更新本文件；关联 ADR：[0025](../decisions/0025-deterministic-media-identity-resolution.md)、[0024](../decisions/0024-layered-release-name-recognition.md)、[0010](../decisions/0010-remove-ai-scraping.md)、[0005](../decisions/0005-three-tier-matching.md)（历史三级设计）。
