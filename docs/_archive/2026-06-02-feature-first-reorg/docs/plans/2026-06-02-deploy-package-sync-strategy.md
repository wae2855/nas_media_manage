---
title: "docs: deploy package sync strategy"
type: plan
date: 2026-06-02
status: completed
confidence: high
---

# Deploy Package Sync Strategy

One-line summary: make root source the only code source of truth and treat `deploy/nas-media-importer/` as generated package workspace.

## Problem Statement

The root package has migrated implementation into `media_importer/domains/`, but `deploy/nas-media-importer/app/server/media_importer/` still contains an older tracked copy.

This creates two risks:

- AI and maintainers may read the deploy copy as current architecture.
- A manual release process may ship stale code if it bypasses `deploy/build_fpk.sh`.

## Evidence

- `deploy/build_fpk.sh` removes `deploy/nas-media-importer/`, recreates the fnOS package skeleton, then copies root `media_importer/` into `app/server/`.
- The tracked deploy copy currently has fewer Python files than root source and lacks the new domain directories.
- Existing docs already say `deploy/` is not the default development source, but they did not state the generation strategy precisely.

## Target End State

- `media_importer/` is the only source tree for application code changes.
- `deploy/build_fpk.sh` is the only supported way to refresh the fnOS package workspace.
- Release workflow requires a generated package build or an explicit decision to skip packaging.
- AI navigation clearly marks deploy package files as generated, not current architecture evidence.

## Scope

- Write ADR and docs that define the strategy.
- Update release/deployment guidance.
- Update roadmap/feasibility docs to mark the strategy decision complete.

## Non-Goals

- Do not run fnOS packaging in this step.
- Do not remove tracked generated deploy files in this step.
- Do not edit application code inside `deploy/nas-media-importer/app/server/media_importer/`.

## Implementation Tasks

- [x] Record the strategy in `docs/decisions/0003-deploy-package-generation-strategy.md`.
- [x] Update `docs/architecture/deployment-fnos.md`.
- [x] Update `docs/workflows/release.md`.
- [x] Add deploy directory guidance in `deploy/README.md`.
- [x] Update AI navigation and AGENTS rules.
- [x] Update active migration roadmap status.
- [x] Dedicated follow-up: decide whether to remove generated package workspace and `.fpk` from git.

## Generated Artifact Decision

Decision: keep the tracked `deploy/nas-media-importer/` package workspace and `.fpk` in git for this architecture refactor cycle.

Reason:

- Removing them would create a large release-artifact cleanup diff unrelated to AI-ready architecture boundaries.
- `deploy/build_fpk.sh` already regenerates the package workspace from root source for releases.
- `deploy/README.md`, AGENTS, AI map and ADR-0003 now mark the package workspace as generated and not a source of architecture truth.

Future cleanup rule:

- If generated package files should be removed from git, create a separate cleanup plan and review `.gitignore`, release workflow, and build outputs together.

## Acceptance Criteria

- AI can identify root source as the current implementation source without reading deploy package code.
- Release workflow names `deploy/build_fpk.sh` as the supported sync/build path.
- The domain migration roadmap no longer has an ambiguous deploy sync blocker.

## Risks

| Risk | Mitigation |
|------|------------|
| Generated deploy files remain tracked and searchable. | Mark them as generated in `deploy/README.md`, AGENTS, and AI map. |
| Build script requires `fnpack` download if missing. | Do not make packaging part of normal refactor validation; reserve for release workflow. |
| Removing generated deploy files later is noisy. | Track it as a dedicated cleanup task with separate review. |
