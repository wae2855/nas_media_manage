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

## Numbering Note

编号 0006 从未使用（历史缺口，保持空号不改，编号只增不重排）。原 `0007-confirm-workflow-preview-vs-import-split.md` 与 0007 重号，2026-08-22 改号为 0009。
