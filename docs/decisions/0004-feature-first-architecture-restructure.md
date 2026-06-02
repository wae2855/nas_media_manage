# ADR-0004: Feature-first Architecture Restructure

Date: 2026-06-02
Status: Accepted

## Context

ADR-0002 chose a conservative domain migration strategy because the project was treated like a running system with existing import paths, tests, deployment copies, and compatibility risk.

The project direction has changed:

- The product is still in development and has not gone online.
- There is no production data compatibility requirement.
- Historical import paths, patch paths, and legacy tests do not need to constrain the new architecture.
- The primary goal is AI-friendly retrieval, feature-first business boundaries, and low-cost future extension.
- Documentation must match the code structure instead of preserving old technical-layer history.

## Decision

Adopt an aggressive feature-first restructure.

The preferred code organization is feature-oriented:

- import flow
- scraping
- configuration
- tasks
- source cleaning
- recycle
- providers
- prompts
- notification/monitoring

Each feature should make its own boundaries explicit:

- application/use-case orchestration
- domain rules and models
- infrastructure dependencies such as SQLite, filesystem, provider clients, and LLM calls
- API route/handler ownership
- configuration keys
- related tests and documentation

Old compatibility layers are not a hard requirement. They may be deleted or archived when they reduce clarity. Historical code, documents, one-off tests, generated artifacts, and replaced plans should move to a single archive area after inventory.

## Consequences

- AI can search by business feature rather than old technical-layer package names.
- Documentation and code can converge around the same feature map.
- Tests should be rewritten around the new architecture instead of preserving obsolete contracts.
- More files may move in a short period, but the project is not yet constrained by production compatibility.
- ADR-0002 is superseded for future architecture work. It remains historical context only.

## Rules

- Current documentation must not cite archived files as current facts.
- Active `docs/plans/` should contain only current or pending work.
- Archived content must be clearly marked as historical and not a source of truth.
- Default regression must remain runnable after each committed phase.
- File deletion/overwrite behavior still follows recycle safety rules.

## Links

- `docs/plans/2026-06-02-refactor-domain-first-code-and-docs-plan.md`
- `docs/decisions/0002-domain-directory-migration-strategy.md`
