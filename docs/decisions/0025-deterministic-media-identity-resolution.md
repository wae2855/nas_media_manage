# ADR-0025: Deterministic media identity resolution

Date: 2026-09-03
Status: Accepted

## Context

ADR-0024 已把通用发布名解析交给 GuessIt，并规定解析结果不能直接作为作品身份。但当前实现没有保留 GuessIt 输出的 Provider ID，也没有读取媒体旁的 NFO；最终仍需标题搜索。与此同时，外部 ID 查询属于 Provider 能力，NFO 属于受边界约束的本地 I/O，二者若直接写进通用匹配器会破坏 feature/provider 边界。

## Decision

采用确定性身份优先、多证据评分兜底的解析管线：

1. `ReleaseIdentity` 只负责发布名结构，保留 `tmdb_id`、`imdb_id`、`tvdb_id`、`alternative_title`、`date`、`part`、`cd/disc` 和 `episode_title` 中实际稳定的输出，不发起 I/O；辅助字段只参与结构与解释，不升级成确定性身份。
2. 独立 NFO 身份读取器在视频相邻和作品根的受控候选中读取小型 XML，仅提取 TMDB/IMDb/TVDB ID；NFO 标题和年份只用于冲突校验，不扩散为模糊查询词。
3. `MetadataProvider` 提供可选的 `get_by_provider_id` 和 `lookup_external_id`。具体 Provider 负责把其原生 ID 或外部 ID 解析为标准 `SearchItem`；匹配器不包含 TMDB 特有端点或字段。
4. 证据优先级固定为：文件名显式 ID、NFO ID、历史绑定、文件结构证据、目录证据、官方别名、模糊标题。
5. 确定性 ID 命中后仍校验明确媒体类型和年份；严重冲突进入 `NEEDS_CONFIRM`。查询失败可降级到标题流程，但必须留痕且不得崩溃。
6. 标题使用统一 `TitleNormalizer`：严格模式执行 NFKC、casefold、撇号/破折号/标点/空白统一；宽松模式额外折叠重音和非语义标点，只做保守的 `&`/`and` 等价，不做音译或 NLP。
7. 文本候选按标题、年份、类型、季集、来源收敛等特征评分；热度只在业务证据同分时排序。第一、第二候选使用证据形态和 TitleMatcher 既有模糊边界共同判断差距，不采用脱离上下文的单一全局 magic number；差距不足且没有强证据时必须人工确认。

历史绑定只有在现有任务上下文实际提供时参与；本次不新增绑定数据库或扫描片库。

## Consequences

- 已存在的确定性 ID 不再退化为标题猜测，识别更快且更可解释。
- NFO I/O 被限制在身份证据模块，发布名解析保持纯函数，Provider 适配保持可扩展。
- 匹配轨迹会增加身份来源、Provider、解析后 ID、冲突和候选差距信息。
- 新 Provider 可以选择不实现 ID 能力；默认实现返回无结果，保持现有第三方适配器兼容。
- 标题模糊流程仍存在，但不会依靠热度或唯一返回结果越过人工确认边界。

## Rejected alternatives

- 在 MatchEngine 中直接调用 TMDB `/find`：拒绝，泄漏 Provider 细节。
- 把 NFO 读取塞进 ReleaseIdentity：拒绝，混合纯解析和文件系统 I/O。
- 引入音译、模型或大规模影视词库：拒绝，难以稳定验证并违背无 LLM 身份判定边界。
- 用一个全局相似度阈值自动通过：拒绝，不同证据组合风险不同。

## Links

- [方案](../proposals/2026-09-03-media-identity-resolution-v2.md)
- [实施记录（已归档）](../_archive/2026-09-03-media-identity-resolution-v2/2026-09-03-refactor-media-identity-resolution-v2-plan.md)
- [ADR-0024](0024-layered-release-name-recognition.md)
- [刮削匹配规范](../standards/scrape-matching.md)
