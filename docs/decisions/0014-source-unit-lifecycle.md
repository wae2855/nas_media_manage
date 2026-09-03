# ADR-0014: 三态来源处理与来源单元生命周期

Date: 2026-08-28
Status: Accepted
Requirement: REQ-20260828-151346

## Context

现有配置用 `cleanup_source_after_done` 和 `source_cleaner.enabled` 两个独立布尔值表达源视频和垃圾清理。它不能呈现清晰从属关系，也只能在单任务成功后移动视频及少量伴生文件。用户期望当来源根下的“阿甘正传”文件夹全部入库成功后，将整个文件夹移入本地回收站；多影片或多集文件夹任一任务未成功时必须整体保留。

## Decision

1. 引入 `source_policy.mode`，取值为 `preserve_all`、`preserve_media`、`recycle_source_unit`。
2. `preserve_all` 不运行任何源目录清理；`preserve_media` 运行规则/可选 LLM 垃圾清理但保留媒体；`recycle_source_unit` 在单元全部成功后整体回收。
3. 每个顶层来源文件夹形成独立来源单元；来源根下全部直接文件形成一个根散文件单元。来源根自身永远不进入单元。
4. scanner 创建任务时写入服务端生成的 `source_unit_id`。单元记录成员快照、状态和等待原因。
5. 只有单元内全部媒体任务为成功入库、没有待确认/失败/运行/未稳定媒体，且快照未变化，才进入 `READY_TO_RECYCLE`。
6. 清理前重新验证来源挂载身份、单元边界、成员快照、回收容量和活跃任务。任一变化进入等待或阻塞，不部分清理。
7. 整体回收复用 ADR-0013 的 verified transfer 与 recycle ledger。入库状态和清理状态分离，失败只重试清理。
8. 旧配置迁移：两个能力都关闭或缺失 → `preserve_all`；保留视频且 cleaner 开启 → `preserve_media`；入库后清理开启 → `recycle_source_unit`。
9. LLM 只参与 `preserve_media` 的垃圾分类。`recycle_source_unit` 整体回收，不运行单文件垃圾分类；其高级策略只控制单元边界和安全等待条件。
10. 来源内容的最终处置由 ADR-0019 扩展为默认本地回收或用户明确确认的受控永久删除；来源单元边界和全部成功门禁保持不变。

## Consequences

- 用户选择与权限需求形成一一对应关系，UI 可以真实表达父子层级。
- 需要来源单元表/字段、聚合查询和旧任务兼容；实现复杂度高于逐文件清理。
- 文件夹中一个失败任务会延迟整个单元释放空间，这是避免部分破坏的有意取舍。

## Alternatives

- 保留两个独立布尔值：组合含义不清晰，无法表达整体文件夹完成条件，否决。
- 每个成功任务立即回收自己的文件：会拆散下载包并遗漏非同名伴生内容，否决。
- 成功部分回收、失败部分保留：用户难以恢复原始包，且竞态复杂，否决。

## Links

- [Brainstorm](../brainstorms/2026-08-28-configuration-dependency-and-readiness-brainstorm.md)
- [ADR-0013](0013-verified-transfer-recovery.md)
- [Plan](../plans/2026-08-28-feat-configuration-dependency-and-readiness-plan.md)
- [ADR-0019](0019-source-disposal-with-guarded-permanent-delete.md)
