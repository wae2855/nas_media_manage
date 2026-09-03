# Architecture Decision Records

ADR 用来记录重要架构决策：为什么这样做、替代方案是什么、后续约束是什么。

## Template

```markdown
# ADR-0000: Title

Date:
Status: Proposed | Accepted | Superseded | Deprecated

## Context

## Decision

## Consequences

## Alternatives

## Links
```

## Initial Decision Backlog

| ADR | Status | Topic |
|-----|--------|-------|
| [0001](0001-ai-ready-documentation-system.md) | Accepted | AI-ready documentation system |
| [0002](0002-domain-directory-migration-strategy.md) | Superseded | Conservative domain directory migration strategy |
| [0003](0003-deploy-package-generation-strategy.md) | Accepted | Deploy package generation strategy |
| [0004](0004-feature-first-architecture-restructure.md) | Accepted | Feature-first architecture restructure |
| [0005](0005-three-tier-matching.md) | Accepted | Three-tier matching |
| [0007](0007-information-responsibility-split.md) | Accepted | Scrape information responsibility split |
| [0009](0009-confirm-workflow-preview-vs-import-split.md) | 已实施 | Confirm workflow preview vs import split |
| [0008](0008-scraper-feature-first-migration.md) | Accepted | Scraper feature-first migration |
| [0010](0010-remove-ai-scraping.md) | Accepted | Remove AI scraping, TMDB-first two-tier matching |
| [0011](0011-fnos-install-runtime-config-ownership.md) | Accepted | fnOS install/runtime config ownership |
| [0012](0012-storage-role-topology.md) | Accepted | Storage role topology and directory boundaries |
| [0013](0013-verified-transfer-recovery.md) | Accepted | Verified transfer, recycle and recovery |
| [0014](0014-source-unit-lifecycle.md) | Accepted | Three-mode source policy and source unit lifecycle |
| [0015](0015-library-root-relative-rules.md) | Accepted | Validated library root and relative import rules |
| [0016](0016-multiple-library-roots.md) | Accepted | Multiple target library roots |
| [0017](0017-fnos-first-run-directory-authorization.md) | Accepted | fnOS first-run directory authorization |
| [0018](0018-target-library-additive-conflict-boundary.md) | Accepted | Target library additive-only writes and per-conflict confirmation |
| [0019](0019-source-disposal-with-guarded-permanent-delete.md) | Accepted | Source-only local recycle or guarded permanent deletion |
| [0020](0020-provider-capabilities-and-editable-dimension-mappings.md) | Accepted | Provider capabilities and user-editable dimension mappings |
| [0021](0021-task-exit-and-direct-library-staging.md) | Accepted | Cooperative task exit, explicit source disposition, and direct target staging |
| [0022](0022-remove-central-staging-and-whole-task-restart.md) | Accepted | Remove central staging and restart interrupted work from the source |
| [0023](0023-release-version-ledger-and-monotonic-build-gate.md) | Accepted | Release version ledger, candidate/UAT separation, and monotonic package gate |
| [0024](0024-layered-release-name-recognition.md) | Accepted | Layered release-name parsing, Chinese adaptation, and Provider alias verification |

## Numbering Note

编号 0006 从未使用（历史缺口，保持空号不改，编号只增不重排）。原 `0007-confirm-workflow-preview-vs-import-split.md` 与 0007 重号，2026-08-22 改号为 0009。
