# ADR-0003: Deploy Package Generation Strategy

Date: 2026-06-02
Status: Accepted

## Context

The repository contains root application source and a fnOS package workspace:

- root source: `media_importer/`, `hermes/`, `config.yaml.example`, `requirements.txt`;
- package workspace: `deploy/nas-media-importer/`;
- build entry: `deploy/build_fpk.sh`.

The package workspace currently contains a tracked copy of `app/server/media_importer/`. After the domain migration, that copy can be stale and may not contain new root directories such as `media_importer/domains/`.

`deploy/build_fpk.sh` already rebuilds `deploy/nas-media-importer/` during packaging:

1. remove the package workspace;
2. run `fnpack create`;
3. copy root `media_importer/`, `hermes/`, `config.yaml.example`, and `requirements.txt`;
4. build the `.fpk`.

## Decision

Use root source as the only development source of truth.

`deploy/nas-media-importer/` is treated as a generated package workspace, not as a place to edit application code.

Release builds must use `deploy/build_fpk.sh` to regenerate the package workspace from root source. Developers and AI agents must not manually patch `deploy/nas-media-importer/app/server/media_importer/` to mirror root source.

Keep the tracked package workspace for now to avoid a disruptive cleanup in the middle of the architecture refactor. Removing generated package files from git is a separate cleanup task.

## Consequences

- Application changes happen once, in root source.
- The stale deploy copy no longer blocks domain migration, because release builds regenerate it.
- AI search must ignore `deploy/nas-media-importer/app/server/media_importer/` as architecture evidence.
- The repository still has generated package files until a dedicated cleanup removes or ignores them.

## Alternatives

- Manually sync root source into `deploy/nas-media-importer/` after each refactor: rejected because it doubles edit surface and is easy to forget.
- Treat deploy copy as a second source tree: rejected because it breaks AI navigation and increases drift.
- Delete all generated deploy package files immediately: deferred because it changes many tracked release artifacts and should be reviewed separately.

## Links

- `deploy/build_fpk.sh`
- `docs/architecture/deployment-fnos.md`
- `docs/workflows/release.md`
- `docs/plans/2026-06-02-deploy-package-sync-strategy.md`
