# Legacy Documentation Map

> These files are retained for traceability. They are not the current source of architectural truth.

## Rule

AI and maintainers should prefer the new documentation tree:

- `docs/architecture/`
- `docs/modules/`
- `docs/standards/`
- `docs/workflows/`
- `docs/decisions/`
- `docs/testing/`
- `docs/product/`

Read legacy docs only when the task explicitly asks to migrate old content, compare historical decisions, or verify whether an old note still has value.

Older plans may still reference legacy paths as historical evidence. A plan is current only if it is listed under `docs/INDEX.md` Active Plans or explicitly selected by the user.

## Legacy Areas

| Legacy path | Status | Current replacement |
|-------------|--------|---------------------|
| `docs/架构/` | Legacy architecture notes. Some paths predate `domains/` migration. | `docs/architecture/`, `docs/modules/` |
| `docs/方案/` | Legacy proposals and implemented方案 notes. | `docs/proposals/`, `docs/plans/`, `docs/decisions/` |
| `docs/规范/` | Legacy standards and reports. | `docs/standards/` |
| `docs/测试/` | Legacy test notes. | `docs/testing/` |
| `docs/系统架构总览.md` | Legacy architecture overview. | `docs/README.md`, `docs/architecture/overview.md`, `docs/INDEX.md` |

## Current Conflict Notes

- `docs/架构/流水线处理.md` still describes `media_importer/pipeline/steps.py` as the implementation entry. Current implementation lives under `media_importer/domains/import_flow/`.
- `docs/方案/代码解耦重构.md` still describes the earlier pipeline split shape. Current migration status is recorded in `docs/plans/2026-06-01-domain-directory-migration-feasibility.md`.
- `docs/系统架构总览.md` predates the AI-ready documentation structure and should not be used as the first entry point.

## Maintenance

Each documentation maintenance pass should choose one legacy area and either:

- migrate still-useful content into the new documentation tree;
- add a short legacy banner to the old file;
- move it into `_archive/` after review.
