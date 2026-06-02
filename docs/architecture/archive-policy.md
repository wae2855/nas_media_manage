# Archive Policy

归档的目标是让 AI 和人只扫描当前事实来源，同时保留历史内容供短期追溯。

## Archive Locations

| Location | Content |
|----------|---------|
| `docs/_archive/` | Historical documents, old plans, old architecture notes, superseded docs. |
| `_archive/` | Non-document files, historical tests/scripts, obsolete generated artifacts, old source snapshots if needed. |

## What To Archive

- Superseded plans and proposals.
- Historical Chinese docs that no longer represent current facts.
- One-off test scripts.
- Tests that import obsolete top-level modules or require unavailable legacy setup.
- Generated artifacts checked into old workspaces.
- Source files replaced by the feature-first structure when they are no longer imported.

## What Not To Archive

- Current source entrypoints.
- Current feature implementation files.
- Dependency manifests.
- Runtime config examples still used by setup.
- Current standards, workflows, product docs, architecture docs, and ADRs.

## Reference Rules

- Current docs must not cite archived files as current facts.
- Current docs may cite an archive README only to explain history.
- Superseded ADRs must clearly say they are superseded.
- Active plans must not depend on archived plans for instructions.

## Process

1. Add the file or directory to an inventory document.
2. Mark the target as `archive_candidate`.
3. Move it to the correct archive location.
4. Remove or update references from current docs.
5. Run default regression if source or tests changed.
6. Record the move in completed items after user acceptance.
