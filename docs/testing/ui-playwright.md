# UI Playwright Tests

## Requirements

- Python `playwright` module.
- Browser binaries installed.
- Local service running on port 9855 for tests that use `BASE_URL = "http://localhost:9855"` or `http://127.0.0.1:9855`.

Install browser binaries when the local environment does not have them:

```bash
python3 -m playwright install chromium
```

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
PYTHONPATH="${PWD}" python3 -m media_importer.media_importer -c config/config.yaml serve -p 9855 --host 127.0.0.1
```

Use this only when `config/config.yaml` is valid for the local machine. UI tests may read or write configuration through the API.

## Command Reference

```bash
# 默认稳定回归，不收集外部 UI 和自启动服务测试
pytest tests/

# 自启动服务集成测试
pytest tests/test_integration_recycle.py --run-service-integration

# 自启动 UI 测试
pytest tests/test_frontend_recycle.py --run-ui

# 外部服务 UI 测试，需先启动 9855 服务
pytest tests/test_confidence_ui.py tests/test_confidence_v2_ui.py tests/test_confidence_config_ui.py --run-external-ui
pytest tests/test_scrape_ui.py --run-external-ui

# 旧 live E2E 和大 UI 套件已归档，前端重做后重新规划
```

Legacy commands, kept for reference:

```bash
pytest tests/test_frontend_recycle.py
pytest tests/test_confidence_ui.py tests/test_confidence_v2_ui.py tests/test_confidence_config_ui.py
pytest tests/test_scrape_ui.py
```

## Regression Rule

- For backend/domain refactors, prefer non-UI tests first.
- For UI or API contract changes, run `tests/test_frontend_recycle.py` if recycle UI is affected.
- Run external-service UI suites only after starting the service and confirming port 9855 is free.
- Use `pytest tests/` as the default stable regression command.
- Use explicit flags for gated suites: `--run-ui`, `--run-external-ui`, `--run-service-integration`, `--run-live-e2e`.
- If Playwright/browser binaries are missing, record that as environment blocked rather than a product regression.
