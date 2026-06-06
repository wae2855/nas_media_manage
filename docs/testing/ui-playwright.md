# UI Playwright Tests

## Requirements

- Python `playwright` module.
- Browser binaries installed.
- Local service running on port 9855 for tests that use `BASE_URL = "http://localhost:9855"` or `http://127.0.0.1:9855`.

Install browser binaries when the local environment does not have them:

```bash
python -m playwright install chromium
```

## Codex Desktop Notes

When running inside Codex Desktop on macOS, launching Chromium from a sandboxed shell, Node REPL, or ad hoc Playwright script can hit macOS permission boundaries such as Mach bootstrap or sandbox denial errors.

- Prefer the in-app Browser tool for local `localhost` / `127.0.0.1` inspection, screenshots, and quick UI checks.
- Use the repository's gated Playwright test commands only when you explicitly need browser automation coverage.
- If a Playwright command fails because of sandbox restrictions, record it as environment blocked rather than a product regression.
- If the right-side UI shows GitHub CLI as unavailable, use the GitHub plugin/connector path instead of depending on local `gh` being present.

## Service Modes

| Test group | Service dependency | Notes |
|------------|--------------------|-------|
| `tests/test_confidence_ui.py` | external service on `localhost:9855` | Does not start the backend. |
| `tests/test_confidence_v2_ui.py` | external service on `localhost:9855` | Does not start the backend. |
| `tests/test_confidence_config_ui.py` | external service on `localhost:9855` | Does not start the backend. |
| `tests/test_scrape_ui.py` | external service on `localhost:9855` | Uses live API/UI assumptions. |
| `tests/test_frontend_recycle.py` | self-started test server | Starts `media_importer.api.handler.start_server` on an ephemeral port. |

## Start External Service

```bash
PYTHONPATH="${PWD}" python -m media_importer.media_importer -c config/config.yaml serve -p 9855 --host 127.0.0.1
```

Use this only when `config/config.yaml` is valid for the local machine. UI tests may read or write configuration through the API.

## Command Reference

```bash
# 默认稳定回归，不收集外部 UI 和自启动服务测试
python -m pytest tests/

# 自启动服务集成测试
python -m pytest tests/test_integration_recycle.py --run-service-integration

# 自启动 UI 测试
python -m pytest tests/test_frontend_recycle.py --run-ui

# 外部服务 UI 测试，需先启动 9855 服务
python -m pytest tests/test_confidence_ui.py tests/test_confidence_v2_ui.py tests/test_confidence_config_ui.py --run-external-ui
python -m pytest tests/test_scrape_ui.py --run-external-ui

# 旧 live E2E 和大 UI 套件已归档，前端重做后重新规划
```

Legacy commands, kept for reference:

```bash
python -m pytest tests/test_frontend_recycle.py
python -m pytest tests/test_confidence_ui.py tests/test_confidence_v2_ui.py tests/test_confidence_config_ui.py
python -m pytest tests/test_scrape_ui.py
```

## Regression Rule

- For backend/domain refactors, prefer non-UI tests first.
- For UI or API contract changes, run `tests/test_frontend_recycle.py` if recycle UI is affected.
- Run external-service UI suites only after starting the service and confirming port 9855 is free.
- Use `python -m pytest tests/` from the project `.venv` as the default stable regression command.
- Use explicit flags for gated suites: `--run-ui`, `--run-external-ui`, `--run-service-integration`, `--run-live-e2e`.
- If Playwright/browser binaries are missing, record that as environment blocked rather than a product regression.
