# Test Inventory

本文件用于区分当前测试、环境 gated 测试、待重写测试和归档候选测试。

## Classification

| Status | Meaning |
|--------|---------|
| `current` | 默认回归或 feature smoke 测试。 |
| `gated` | 需要显式 pytest flag 或外部服务。 |
| `rewrite_later` | 场景有价值，但应按新架构/新前端重写。 |
| `archive_candidate` | 历史脚本或旧结构测试，归档后不再参与当前测试。 |

## Current Stable Tests

| File | Status | Notes |
|------|--------|-------|
| `tests/test_api_routes.py` | current | API route table. |
| `tests/test_config_view.py` | current | Config facade defaults and consumers. |
| `tests/test_task_context_lifecycle.py` | current | Task context and lifecycle. |
| `tests/test_task_operations.py` | current | Task manager operations. |
| `tests/test_import_flow_services.py` | current | Import flow services. |
| `tests/test_confidence_engine.py` | current | Confidence calculations. |
| `tests/test_feature_entrypoints.py` | current | Verifies app/API/feature consumers import feature public APIs directly. |
| `tests/test_feature_*` | current | Feature entry smoke tests for import flow, recycle, and source cleaning. |
| `tests/test_recycle_safety.py` | current | Focused recycle safety smoke. |

## Gated Tests

| File | Status | Notes |
|------|--------|-------|
| `tests/test_confidence_config_ui.py` | gated | External service UI. |
| `tests/test_confidence_ui.py` | gated | External service UI. |
| `tests/test_confidence_v2_ui.py` | gated | External service UI. |
| `tests/test_scrape_ui.py` | gated | External service UI. |
| `tests/test_frontend_recycle.py` | gated | Self-started UI; keep until frontend rewrite. |
| `tests/test_integration_recycle.py` | gated | Self-started service integration. |

## Archive Candidates

| File | Reason |
|------|--------|
| `docs/_archive/2026-06-02-feature-first-reorg/tests/test_scrape_results.py` | Uses obsolete top-level imports and script-style execution. |
| `docs/_archive/2026-06-02-feature-first-reorg/tests/test_tmdb_config.py` | Executes Playwright at import time and requires external service. |
| `docs/_archive/2026-06-02-feature-first-reorg/tests/test_deep_e2e.py` | Large old source cleaner E2E suite; rewrite after frontend/feature stabilization. |
| `docs/_archive/2026-06-02-feature-first-reorg/tests/test_full_flow.py` | Large old pipeline suite tied to legacy patch paths. |
| `docs/_archive/2026-06-02-feature-first-reorg/tests/test_e2e_file_processing.py` | Live provider E2E requiring real config/network. |
| `docs/_archive/2026-06-02-feature-first-reorg/tests/test_config_page_full.py` | Old frontend config page suite; rewrite after frontend redesign. |
| `docs/_archive/2026-06-02-feature-first-reorg/tests/test_sqlite_refactor.py` | Mixed DB/scanner/pipeline legacy regression file. |
| `docs/_archive/2026-06-02-feature-first-reorg/tests/test_recycle_and_safety.py` | Oversized legacy recycle/safety suite replaced by focused feature tests. |

## Rewrite Later

| File | Reason |
|------|--------|
| Frontend UI/E2E suites | Rewrite after frontend redesign and new API dependency map. |

## Default Command

```bash
python3 -m pytest tests/
```

Default regression should remain usable during architecture work. Tests marked `rewrite_later` may still run if gated/skipped through `tests/conftest.py`, but they are not the final product contract.
