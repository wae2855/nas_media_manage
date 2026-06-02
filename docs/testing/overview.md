# Testing Overview

## Layers

- Unit tests: module behavior.
- Integration tests: API, DB, filesystem workflows.
- UI tests: Playwright browser workflows.

## Current Commands

```bash
pytest tests/
pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py
```

## Rule

大重构前先记录 baseline。测试结果必须区分已知失败和新增失败。

UI tests are split by service mode:

- external-service suites require a service already running on port 9855;
- `tests/test_frontend_recycle.py` starts its own test server.

See [ui-playwright.md](ui-playwright.md) before running UI tests.
