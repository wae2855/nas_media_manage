# ADR-0002: Domain Directory Migration Strategy

Date: 2026-06-01
Status: Accepted

## Context

The project has completed several AI-readability refactors:

- documentation framework;
- `TaskContext`;
- `TaskLifecycle`;
- pipeline business services;
- `ConfigView`;
- API route table.

The roadmap contains a possible future structure with `domains/` and `infrastructure/`. Moving directories now would touch many import paths, tests, mocks, docs, and the fnOS deploy copy under `deploy/nas-media-importer/app/server/media_importer/`.

## Decision

Do not perform a one-shot directory migration.

Use a staged compatibility strategy:

1. Keep current public imports stable.
2. Introduce `domains/` only through proof slices.
3. Re-export new implementations from old paths during migration.
4. Move one domain at a time after tests and docs are ready.
5. Defer deployment package structure changes until root package migration proves stable.

## Consequences

- AI can already use the new service/facade boundaries without waiting for directory moves.
- Existing tests and patch paths remain stable.
- Migration can be reviewed and reverted per domain.
- There will be temporary duplication in import entry points, but not duplicated implementations.

## Alternatives

- Full domain/infrastructure move now: rejected because import and deploy blast radius is high.
- Never move directories: rejected because domain-first paths may become useful once boundaries stabilize.
- Move only docs, not code: rejected because docs would drift if they claim a domain structure not present in code.

## Links

- `docs/plans/2026-06-01-domain-directory-migration-feasibility.md`
- `docs/plans/2026-05-31-refactor-ai-ready-architecture-roadmap.md`
- `docs/plans/2026-05-31-refactor-business-boundaries-plan.md`
