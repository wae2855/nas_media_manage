# 2026-06-02 Feature-first Reorganization Archive

This archive batch contains historical documents, replaced wrappers, old scripts, local artifacts, and generated data moved out of active project paths during the feature-first architecture restructure.

## Contents

| Path | Contents |
|------|----------|
| `code/media_importer/pipeline/` | Old import-flow compatibility wrappers replaced by `media_importer/features/import_flow/`. |
| `config/media_importer/config/` | Package-local config copy replaced by root `config/` and `config.yaml.example`. |
| `docs/legacy-chinese/` | Historical Chinese architecture, proposal, standards, testing docs, and the old system overview. |
| `docs/modules/` | Old module-first documentation replaced by `docs/features/` and `docs/architecture/`. |
| `docs/plans/` | Completed, superseded, or replaced implementation plans. |
| `local-tooling/` | Local agent/tooling context moved out of product source paths when present locally. |
| `root/` | Root-level historical artifacts moved out of the active workspace when present locally. |
| `runtime-data/` | Local runtime data snapshots moved out of package paths when present locally. |
| `tests/` | Historical script-style or old-contract tests removed from the default test tree. |

## Rule

Do not treat these files as current facts. If useful historical content is needed, migrate the relevant idea into the active documentation tree and cite this archive batch only as traceability.
