# Testing Overview

## Layers

- Unit tests: module behavior.
- Integration tests: API, DB, filesystem workflows.
- UI tests: Playwright browser workflows.

## Current Commands

```bash
./scripts/bootstrap_python_env.sh
source .venv/bin/activate
python -m pytest tests/
python -m pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py
```

## Rule

大重构前先记录 baseline。测试结果必须区分已知失败和新增失败。

UI tests are split by service mode:

- external-service suites require a service already running on port 9855;
- `tests/test_frontend_recycle.py` starts its own test server.

## Codex Desktop Execution

- For quick local UI inspection on macOS, prefer the in-app `Browser` tool over launching Chromium from a sandboxed shell.
- Treat browser launch failures caused by macOS sandbox boundaries as environment blocked, not as a product regression.
- Use Playwright only when the task specifically needs browser automation coverage or a formal UI regression run.
- If the right-side tool area reports GitHub CLI as unavailable, use the GitHub plugin/connector path instead of depending on local `gh`.

See [ui-playwright.md](ui-playwright.md) before running UI tests.
