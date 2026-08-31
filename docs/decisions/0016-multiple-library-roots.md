# ADR-0016: 稳定 ID 的多片库根

Date: 2026-08-30
Status: Accepted
Requirement: REQ-20260830-180954

## Context

用户的影片可能分布在多个硬盘或挂载目录。ADR-0015 有意限制为单一片库根，并规定未来多根必须使用显式 root ID，不能恢复任意绝对路径。

## Decision

1. 规范配置使用 `library_roots[]`，每个根包含稳定唯一的 `id/name/path/enabled`。
2. 每条 `path_rules[]` 保存 `library_root_id` 和相对模板；兜底目录保存独立 `fallback_library_root_id`。
3. 旧 `library_root` 自动迁移为 ID `default`，旧规则和兜底目录绑定该根。
4. 保存时校验根 ID、规范路径唯一性、引用完整性和相对模板；运行时按绑定根再次做 containment。
5. 所有启用根都进入存储身份、权限、容量和健康检查。某根离线只阻止依赖该根的执行；自动运行是否可用继续由总体 readiness 判定。
6. 被规则或兜底引用的根不得直接删除；用户必须先迁移引用。

## Consequences

- 支持跨卷片库，同时保留明确授权边界和路径安全。
- 规则编辑多一个“目标片库”选择，但默认根可让普通用户无需逐条调整。
- 配置、分类、就绪检查和 UI 都必须从单根切换为集合语义。

## Alternatives

- 统一上级目录：跨卷不存在共同可写父目录，否决。
- 每条规则保存绝对根：重复、易漂移且难授权，否决。
- 自动按空间选择根：结果不可预期且规则语义不稳定，暂不采用。

## Links

- [Brainstorm](../brainstorms/2026-08-30-fnos-first-run-multi-library-brainstorm.md)
- [ADR-0015](0015-library-root-relative-rules.md)
- [Plan（已归档）](../_archive/2026-08-30-fnos-first-run-multi-library/2026-08-30-feat-fnos-first-run-multi-library-plan.md)
