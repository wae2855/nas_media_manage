# ADR-0020: Provider 能力与用户可编辑维度映射

Date: 2026-09-01
Status: Accepted
Requirement: REQ-20260901-233114

## Context

Provider 返回的是类型、地区、语言、分级、成人标记等原始事实，产品需要把它们映射到用户自己的维度值。目前映射一部分存于 `provider_mappings`，另一部分写死在 Python 分支和前端说明中；更新 API 又拒绝保存 `provider_mappings`。结果是映射不可见、不可覆盖、不同入口可能漂移，并发生 `R → 17+ → 成人内容` 的语义错误。

系统还需要兼容后续 Provider，不能每新增一种数据源就复制整套维度页面和业务判断。

## Decision

1. Provider 适配器声明标准化能力，不决定产品分类。首期只允许 `scalar`、`set`、`country_value`、`media_type` 四种可验证数据形状。
2. 每个维度由稳定定义、稳定 value ID 值域和 Provider 映射三层组成。入库规则只引用稳定 ID，显示名可以修改；删除被映射、规则或活动任务引用的值必须阻止。
3. `dimensions.provider_mappings` 是用户当前映射唯一事实源，使用版本化 JSON 合同。YAML 不再保存第二份映射。
4. Provider 原始业务值到本地 value ID 的映射进入独立版本化预置数据；执行代码只保留字段标准化、有限 operator、确定性排序和验证。升级时，仍与旧产品默认完全一致的当前映射跟随新预置更新；任何用户自定义映射保持不动，用户也可明确触发“恢复产品预置”。
5. 映射 API 以内容哈希执行 compare-and-save，拒绝多设备静默覆盖。保存前验证 Provider/字段、数据形状、规则唯一性、目标值、优先级和未映配策略。
6. 映射执行返回原始证据、规则 ID、目标值和映射版本。自动刮削、手动候选应用和重新整理使用同一执行器；不得保存密钥或完整 Provider 响应。
7. 普通用户默认使用产品预置。维度主页只显示摘要，完整映射在专用弹层编辑；手机使用全屏纵向卡片，不显示横向映射表。
8. 保留 `restricted_level` 内部键以兼容规则，但产品名称改为“观看分级”，`17+` 显示为“限制观看”。新增独立可选维度 `content_sensitivity`，产品名称为“成人电影标记”，只表达 TMDB `adult=false/true` 的“否/是”；稳定内部值继续使用 `normal/adult`。
9. 年龄分级不能单独证明露骨或重度暴力血腥。成人电影标记也不表达全年龄、暴力、宗教等内容警示；R 不自动等于成人电影。
10. 映射修改只自动作用于新任务和仍待确认、尚未开始文件操作的任务。运行中及已完成任务保持历史事实；需要调整已入库影片时走关联重新整理任务。
11. 中国用户场景优先使用香港本地官方分级：TMDB `HK/I` 映射为 `0-6`，`HK/IIA`、`HK/IIB` 映射为 `13-16`，`HK/III` 映射为 `17+`；这仍是“观看分级”，不改变独立的 TMDB `adult` 成人电影标记。

## Consequences

- 用户能看到并人工决定每个 Provider 原始值落到哪个维度值。
- 新 Provider 只需实现能力描述和标准化值，不需重写维度 UI。
- 需要 v1 → v2 映射迁移、预置资产、通用执行器、映射 API、解释证据和双端编辑器。
- 旧 `restricted_level=17+` 规则不能自动迁移为成人电影标记，必须明确提示人工复核。
- TMDB 数据不足时人工确认率可能上升，但不会用不可解释猜测自动写入错误片库。

## Alternatives

- 继续代码硬编码：不可由用户覆盖，扩展 Provider 成本高，否决。
- 允许用户编辑任意表达式或脚本：安全性、可验证性和移动端体验不可接受，否决。
- 每个维度单独定义前端和保存合同：会继续产生重复与语义漂移，否决。
- 把 R 改成青少年向：消除“成人”误称但伪造年龄分级事实，否决。

## Links

- [Proposal](../proposals/2026-09-01-provider-dimension-mapping-and-media-candidate-filter.md)
- [Plan](../plans/2026-09-01-feat-provider-dimension-mapping-and-media-candidate-filter-plan.md)
- [ADR-0010](0010-remove-ai-scraping.md)
- [ADR-0014](0014-source-unit-lifecycle.md)
- [ADR-0018](0018-target-library-additive-conflict-boundary.md)
- [ADR-0019](0019-source-disposal-with-guarded-permanent-delete.md)
