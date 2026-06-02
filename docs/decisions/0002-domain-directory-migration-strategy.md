# ADR-0002: Feature Directory Migration Strategy

Date: 2026-06-01
Status: Superseded

Superseded by [ADR-0004](0004-feature-first-architecture-restructure.md). This ADR is historical context only and must not guide new architecture work.

## Context

The project has completed several AI-readability refactors:

- documentation framework;
- `TaskContext`;
- `TaskLifecycle`;
- pipeline business services;
- `ConfigView`;
- API route table.

The roadmap contains a possible future structure with `features/` and `infrastructure/`. Moving directories now would touch many import paths, tests, mocks, docs, and the fnOS deploy copy under `deploy/nas-media-importer/app/server/media_importer/`.

## Decision

Do not perform a one-shot directory migration.

Use a staged compatibility strategy:

1. Keep current public imports stable.
2. Introduce `features/` only through proof slices.
3. Re-export new implementations from old paths during migration.
4. Move one feature at a time after tests and docs are ready.
5. Defer deployment package structure changes until root package migration proves stable.

## Consequences

- AI can already use the new service/facade boundaries without waiting for directory moves.
- Existing tests and patch paths remain stable.
- Migration can be reviewed and reverted per domain.
- There will be temporary duplication in import entry points, but not duplicated implementations.

## Alternatives

- Full domain/infrastructure move now: rejected because import and deploy blast radius is high.
- Never move directories: rejected because domain-first paths may become useful once boundaries stabilize.
- Move only docs, not code: rejected because docs would drift if they claim a feature structure not present in code.

## Links

- `docs/_archive/2026-06-02-feature-first-reorg/README.md`
- `docs/decisions/0004-feature-first-architecture-restructure.md`
