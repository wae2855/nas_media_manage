# ADR-0015: 已校验片库根与相对入库规则

Date: 2026-08-28
Status: Accepted
Requirement: REQ-20260828-151346

## Context

当前每条 `path_rules[].template` 和 `fallback_dir` 可保存任意绝对路径。存储检查只能从这些路径反推公共目标，不能保证新规则仍位于用户在 fnOS 授权并确认的目标内，也无法用 UI 简洁表达“只配置片库下的子目录”。

## Decision

1. 配置新增唯一 `library_root`，必须是已存在且通过存储身份、写权限和容量检查的目录。
2. `path_rules[].template` 与 `fallback_dir` 规范值改为相对模板，不允许绝对路径、`..` 或空静态前缀逃逸。
3. 配置保存时将模板静态部分与 `library_root` 拼接并执行 `realpath/commonpath` 校验；分类得到最终目标后再次校验。
4. UI 固定显示不可编辑的片库根前缀，只让用户编辑子目录模板。
5. 旧配置若所有目标都位于同一非卷级公共根，自动提取 `library_root` 并转换相对模板；无法安全归一时进入 BLOCKED，保留原值等待用户处理。
6. 本轮不支持多片库根；该能力若需要，必须新增显式 root ID，而不是恢复任意绝对路径。

## Consequences

- 所有目标路径都能由存储检查覆盖，越界配置在保存和运行时双重失败关闭。
- 旧的跨盘规则不能自动继续，需要用户选择单一片库根。
- 相对模板更适合 fnOS 安装目录继承，也降低首次配置理解成本。

## Alternatives

- 保留绝对路径并增加提示：旧客户端和 API 仍能绕过，否决。
- 每条规则绑定独立绝对根：支持多盘但重新引入大量路径决策，违背本轮简化目标。
- 只在前端限制：无法形成安全边界，否决。

## Links

- [Brainstorm](../brainstorms/2026-08-28-configuration-dependency-and-readiness-brainstorm.md)
- [ADR-0012](0012-storage-role-topology.md)
- [Plan](../plans/2026-08-28-feat-configuration-dependency-and-readiness-plan.md)
- [ADR-0016](0016-multiple-library-roots.md)（按本决策第 6 条扩展为稳定 root ID 的多片库）
