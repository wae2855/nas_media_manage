# ADR-0001: AI-ready Documentation System

Date: 2026-05-31
Status: Accepted

## Context

The previous documentation was useful but scattered across architecture, plans, proposals, and standards without a clear navigation model. The project is entering a large refactor, so AI agents need a stable way to find modules, rules, tests, and change impact.

## Decision

Create a documentation system with:

- `docs/README.md`
- `docs/ai-map.md`
- `docs/ai-map.md`
- `docs/product/`
- `docs/architecture/`
- `docs/modules/`
- `docs/standards/`
- `docs/workflows/`
- `docs/decisions/`
- `docs/testing/`
- `docs/_archive/`

Use English paths for tooling stability while keeping Chinese content in document bodies.

## Consequences

- AI gets a stable entry point.
- Code changes can be linked to required document updates.
- Existing Chinese docs remain backed up and can be migrated gradually.
- Detailed architecture facts will be filled after code refactors stabilize.

## Alternatives

- Keep current structure and only update AGENTS.md: rejected because it keeps navigation and ownership unclear.
- Fully rewrite all docs immediately: rejected because upcoming code refactors would cause large duplicate documentation churn.

## Links

- `docs/_archive/2026-06-02-feature-first-reorg/README.md`
