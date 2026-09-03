# ADR-0023: Release Version Ledger and Monotonic Build Gate

Date: 2026-09-02
Status: Accepted
Requirement: REQ-20260902-172713

## Context

根 `VERSION` 已用于 manifest、包内运行时与页面展示，但历史流程只验证单个包内部一致性。仓库没有保存上一次候选包和真机验收版本，因而不同源码可以沿用同一版本再次打包。Git tag 也不能单独表达尚未提交、尚待 fnOS 验收的本地候选包。

## Decision

1. 根 `VERSION` 继续作为当前开发/构建版本唯一事实源，并必须纳入版本控制。
2. `deploy/release-ledger.json` 作为候选与真机验收台账，记录版本、源码输入指纹、产物 SHA-256、构建时间和验收状态。
3. 构建前执行单调门禁：新版本必须高于台账中的最高候选版本；只有版本与源码指纹都相同才允许确定性重建。低版本或同版本不同源码一律失败。
4. 构建成功只登记 `candidate`，不得自动标记为正常发布。fnOS 验收通过后必须显式执行验收登记命令；查询命令同时显示当前版本、最近候选和最近正常版本。
5. 版本可以跳号，不要求连续；SemVer 比较只要求严格递增。

## Consequences

- 忘记升版会在耗时下载 wheel 和生成 FPK 前失败。
- 本地打包和真机正常版本有可审计区别。
- 同一输入可重复生成同版本包，源码变化则必须升版。
- 台账和版本文件需要与发布代码一起提交；验收记录也应在确认后同步回仓库。

## Alternatives

- 只在文档中要求人工检查：无法形成执行门禁。
- 把本地构建自动视为正常发布：混淆 LOCAL_BUILD 与 FNOS_UAT。
- 只使用 Git tag：无法覆盖提交前候选包和真机验收状态。

## Links

- [Release workflow](../workflows/release.md)
- [fnOS deployment](../architecture/deployment-fnos.md)
- [Implementation plan（已归档）](../_archive/2026-09-02-source-cleanup-and-release-version-governance/2026-09-02-fix-source-cleanup-and-release-version-governance-plan.md)
