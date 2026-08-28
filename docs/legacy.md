# Legacy Documentation Map

> These files are retained for traceability. They are not the current source of architectural truth.

## Rule

AI and maintainers should prefer the new documentation tree:

- `docs/architecture/`
- `docs/features/`
- `docs/standards/`
- `docs/workflows/`
- `docs/decisions/`
- `docs/testing/`
- `docs/product/`

Read legacy docs only when the task explicitly asks to migrate old content, compare historical decisions, or verify whether an old note still has value.

Older plans may still reference legacy paths as historical evidence. A plan is current only if it is listed under `docs/ai-map.md` §5 Active Plans or explicitly selected by the user.

## Legacy Areas

| Legacy path | Archived under | Current replacement |
|-------------|----------------|---------------------|
| `docs/架构/` | `docs/_archive/2026-06-02-feature-first-reorg/docs/legacy-chinese/架构/` | `docs/architecture/`, `docs/features/` |
| `docs/方案/` | `docs/_archive/2026-06-02-feature-first-reorg/docs/legacy-chinese/方案/` | `docs/proposals/`, `docs/plans/`, `docs/decisions/` |
| `docs/规范/` | `docs/_archive/2026-06-02-feature-first-reorg/docs/legacy-chinese/规范/` | `docs/standards/` |
| `docs/测试/` | `docs/_archive/2026-06-02-feature-first-reorg/docs/legacy-chinese/测试/` | `docs/testing/` |
| `docs/系统架构总览.md` | `docs/_archive/2026-06-02-feature-first-reorg/docs/legacy-chinese/系统架构总览.md` | `docs/README.md`, `docs/architecture/overview.md`, `docs/INDEX.md` |
| `docs/modules/` | `docs/_archive/2026-06-02-feature-first-reorg/docs/modules/` | `docs/features/`, `docs/architecture/`, `docs/INDEX.md` |
| `media_importer/pipeline/` | `docs/_archive/2026-06-02-feature-first-reorg/code/media_importer/pipeline/` | `media_importer/features/import_flow/` |

## Current Conflict Notes

- Archived legacy docs may describe old `pipeline/`, `domains/`, or technical-layer-first layouts.
- Current implementation facts live under `media_importer/features/` and `docs/features/`.
- Old modules docs and old pipeline wrappers are traceability only.
- Replaced plans live in `docs/_archive/2026-06-02-feature-first-reorg/docs/plans/`.

## Maintenance

Each documentation maintenance pass should either migrate still-useful ideas into the active docs or leave the archived file untouched. Do not link archived files as current facts.
