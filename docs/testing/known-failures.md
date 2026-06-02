# Known Failures and Deferred Deep Tests

当前阶段不继续修补旧 known failures。项目未上线，架构和文档先按 feature-first 重组；旧深层测试、旧 UI/E2E、旧 DB/scanner 混合大测试已移入 archive，后续按新前端和新业务契约重写。

## Archived Test Details

Historical failure-heavy tests were moved to:

- `docs/_archive/2026-06-02-feature-first-reorg/tests/`

Archived tests are not current product contracts. If a scenario is still valuable, migrate the scenario into a new focused test under `tests/` and update `docs/testing/test-inventory.md`.

## Current Policy

- `pytest tests/` must remain the default stable regression entry.
- Environment-dependent UI suites stay gated through `tests/conftest.py`.
- New failures in current tests are not covered by this file and must be investigated.
- After frontend redesign, create a new UI/E2E plan before reintroducing deep browser tests.

## Re-entry Conditions

Revisit archived known failures only after:

- feature-first code/docs are stable;
- frontend redesign has a concrete plan or implementation;
- API contracts needed by the new frontend are documented;
- the scenario can be expressed as a deterministic unit, integration, or UI test.
